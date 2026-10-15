"""Camada de serviço FastAPI do EduTrack-GNN.

Execução:  uvicorn edutrack.api.main:app --port 8000
Página principal: http://127.0.0.1:8000/   ·   Documentação interativa: http://127.0.0.1:8000/docs

Princípios (RNF31, RN07, RN08): a API só lê artefatos pré-processados; não há
autenticação, cadastro, banco de dados de usuários nem rota que grave dados. A
seleção de disciplinas chega no corpo da requisição, é usada em memória e
descartada. O modo Estudante e o modo Coordenação são apenas visões da mesma
página, sem identificação de quem acessa.
"""
from __future__ import annotations

import json
import mimetypes
import time
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from edutrack.core.texto import titulo_pt
from edutrack.config import RAIZ, artefatos, caminho, carregar_config, processados
from edutrack.graph.hetero import HeteroGrafo
from edutrack.recommend.engine import NOMES_PERFIS, Base, ErroEntrada

from . import interface
from .schemas import Modelo, Perfil, TrilhaEntrada, TrilhaSaida

WEB = Path(__file__).resolve().parent.parent / "web"
VERSAO = carregar_config()["versao"]

# No Windows, o módulo mimetypes lê o registro, que às vezes associa .js a text/plain; com o
# cabeçalho nosniff o navegador recusaria os módulos da página. Os tipos são fixados aqui.
for _tipo, _ext in (("text/javascript", ".js"), ("text/css", ".css"), ("text/html", ".html"),
                    ("image/svg+xml", ".svg"), ("font/woff", ".woff"), ("application/json", ".json"),
                    ("text/plain", ".txt")):
    mimetypes.add_type(_tipo, _ext)

app = FastAPI(
    title="EduTrack-GNN",
    version=VERSAO,
    description=(
        "Recomendação de trilhas formativas e diagnóstico de alinhamento entre o PPC de Ciência da Computação "
        "(currículo CCO-2024/1) e as vagas de tecnologia de Manaus, sobre um grafo de conhecimento heterogêneo. "
        "Sem autenticação e sem armazenamento de dados de estudantes."
    ),
    docs_url="/docs",
    redoc_url=None,
    swagger_ui_oauth2_redirect_url=None,  # não há autenticação (RN08)
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def cabecalhos(request: Request, call_next):
    t0 = time.perf_counter()
    resp = await call_next(request)
    resp.headers["X-Tempo-Resposta-ms"] = f"{(time.perf_counter() - t0) * 1000:.1f}"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    elif not request.url.path.startswith(("/docs", "/openapi.json")):
        # a página só fala com este servidor: nenhuma fonte, script ou imagem de terceiros (RF42)
        resp.headers["Content-Security-Policy"] = CSP
        # revalida a cada carga (ETag): uma versão nova da interface aparece sem limpar o cache
        resp.headers.setdefault("Cache-Control", "no-cache")
        if resp.headers.get("content-type", "").startswith("text/html"):
            # descarta módulos JS/CSS guardados por versões antigas (que não revalidavam) antes de carregá-los
            resp.headers["Clear-Site-Data"] = '"cache"'
    return resp


CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")


@lru_cache(maxsize=1)
def base() -> Base:
    return Base.carregar()


@lru_cache(maxsize=1)
def grafo() -> HeteroGrafo:
    return HeteroGrafo.carregar(artefatos() / "graph")


def _json(arquivo: Path) -> dict:
    return json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else {}


def _erro(exc: ErroEntrada):
    raise HTTPException(status_code=422, detail=str(exc))


# ------------------------------------------------------------------ API
@app.get("/api/saude", tags=["sistema"], summary="Verificação de funcionamento")
def saude():
    b = base()
    return {"status": "ok", "versao": VERSAO, "disciplinas": len(b.disciplinas), "habilidades": len(b.ids_s),
            "vagas": len(b.vagas), "modelo_padrao": b.meta_modelo.get("modelo_padrao")}


@app.get("/api/disciplinas", tags=["dados"], summary="Disciplinas do PPC com período, fonte da ementa e habilidades")
def disciplinas():
    b = base()
    cobertura = _json(processados() / "cobertura_ppc.json")
    return {
        "cobertura": {k: cobertura.get(k) for k in ("disciplinas_identificadas", "disciplinas_esperadas", "periodos_presentes",
                                                     "periodos_esperados", "com_programa_oficial", "com_ementa_referencia",
                                                     "declaracao_RNF21")},
        "disciplinas": [
            {"id": d["id"], "nome": titulo_pt(d["nome"]), "periodo": d["periodo"], "codigo": d["codigo"],
             "carga_horaria": d["carga_horaria"], "fonte_ementa": d["fonte_ementa"],
             "pre_requisitos": sorted(b.requisitos.get(d["id"], ())),
             "habilidades": [{"id": s, "nome": b.nome_skill(s)} for s in sorted(b.ensina.get(d["id"], ()))]}
            for d in sorted(b.disciplinas, key=lambda x: (x["periodo"], x["nome"]))
        ],
    }


@app.get("/api/habilidades", tags=["dados"], summary="Ontologia controlada de habilidades")
def habilidades():
    b = base()
    w = b.demanda()
    return {"categorias": b.ont.categorias, "habilidades": [
        {"id": h.id, "nome": h.nome, "categoria": h.categoria, "sinonimos": len(h.aliases) + len(h.aliases_cs),
         "ensinada_no_ppc": h.id in b.ensinadas, "demanda": round(w.get(h.id, 0.0), 4)}
        for h in b.ont.habilidades.values()]}


@app.get("/api/perfis", tags=["dados"], summary="Perfis de vaga para filtrar a recomendação (RF31)")
def perfis():
    b = base()
    return [{"id": "todos", "nome": "Todas as vagas de TI", "vagas": len(b.vagas)}] + [
        {"id": p, "nome": n, "vagas": sum(1 for v in b.vagas if v["perfil"] == p)} for p, n in NOMES_PERFIS.items()]


@app.get("/api/mercado", tags=["mercado"], summary="Habilidades mais demandadas pelas vagas de Manaus")
def mercado(perfil: Perfil = None, top: int = Query(15, ge=1, le=76)):
    try:
        return base().mercado(perfil, top)
    except ErroEntrada as e:
        _erro(e)


@app.post("/api/trilha", tags=["estudante"], response_model=TrilhaSaida,
          summary="Recomenda uma trilha de disciplinas e calcula a aderência antes e depois (RF27–RF31)")
def trilha(entrada: TrilhaEntrada):
    try:
        return base().trilha(entrada.cursadas, entrada.perfil, entrada.k, entrada.modelo)
    except ErroEntrada as e:
        _erro(e)


@app.get("/api/afinidade", tags=["estudante"], summary="Disciplinas ordenadas por afinidade com habilidades (RF26)")
def afinidade(habilidades: str = Query(..., description="Identificadores separados por vírgula", examples=["sql,cloud"]),
              modelo: Modelo = "auto", top: int = Query(10, ge=1, le=40)):
    try:
        return base().afinidade_disciplinas([h.strip() for h in habilidades.split(",") if h.strip()], modelo, top)
    except ErroEntrada as e:
        _erro(e)


@app.get("/api/diagnostico", tags=["coordenação"], summary="Lacunas curriculares e cobertura da demanda (RF32–RF34)")
def diagnostico(perfil: Perfil = None, modelo: Modelo = "auto"):
    try:
        return base().diagnostico(perfil, modelo)
    except ErroEntrada as e:
        _erro(e)


@app.get("/api/diagnostico.csv", tags=["coordenação"], summary="Diagnóstico em CSV para o NDE (RF35)")
def diagnostico_csv(perfil: Perfil = None, modelo: Modelo = "auto"):
    try:
        conteudo = base().diagnostico_csv(perfil, modelo)
    except ErroEntrada as e:
        _erro(e)
    nome = f"diagnostico_curricular_{perfil or 'todos'}.csv"
    return Response(conteudo, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


@app.get("/api/metricas", tags=["avaliação"], summary="Precision@k, Recall@k, AUC, tempos e energia (RF36–RF39, RF44)")
def metricas():
    m = artefatos() / "metrics"
    aval = _json(m / "avaliacao.json")
    aval.pop("por_semente", None)
    return {"avaliacao": aval, "energia_avaliacao": _json(m / "energia_avaliacao.json"),
            "energia_pipeline": _json(m / "energia_pipeline.json"), "modelo_final": base().meta_modelo,
            "normalizacao": _json(processados() / "resumo_normalizacao.json"),
            "validacao_grafo": _json(artefatos() / "graph" / "validacao.json")}


@app.get("/api/grafo/subgrafo", tags=["grafo"], summary="Vizinhança de uma disciplina ou habilidade (RF22)")
def subgrafo(tipo: str = Query(..., pattern="^(disciplina|skill)$"), id: str = Query(..., max_length=80)):
    g = grafo()
    if id not in g.idx(tipo):
        raise HTTPException(status_code=404, detail="nó não encontrado")
    return g.subgrafo(tipo, id)


@lru_cache(maxsize=1)
def _pacote() -> dict:
    return interface.montar_pacote(base())


@app.get("/api/interface", tags=["interface"],
         summary="Pacote de leitura para a página: disciplinas, ontologia, vagas, sugestões da GNN, métricas e origem dos dados")
def pacote_interface():
    return _pacote()


@app.get("/api/normalizar", tags=["normalização"],
         summary="Aplica as duas camadas da normalização a um termo isolado (RF12–RF14)")
def normalizar(termo: str = Query(..., min_length=1, max_length=120, description="Termo como apareceria no texto"),
               limiar: float = Query(None, ge=0.5, le=1.0, description="Limiar da camada aproximada (padrão de config.yaml)")):
    padrao = carregar_config()["normalizacao"]["limiar_fuzzy"]
    return interface.testar_termo(termo, padrao if limiar is None else limiar)


@app.get("/api/ontologia", tags=["normalização"],
         summary="Ontologia controlada como está em data/ontology/skills_ontology.json (RF11, RF16)")
def ontologia():
    return json.loads(caminho("ontologia").read_text(encoding="utf-8"))


@app.get("/api/normalizacao/auditoria", tags=["normalização"],
         summary="Trilha de auditoria da normalização feita pelo pipeline, paginada (RF14)")
def auditoria(pagina: int = Query(1, ge=1), tamanho: int = Query(10, ge=5, le=50),
              camada: str = Query("todas", pattern="^(todas|exata|aproximada|nao_resolvido)$"),
              origem: str = Query("todas", pattern="^(todas|ementa|vaga)$")):
    return interface.auditoria(pagina, tamanho, camada, origem)


@app.get("/api/sobre", tags=["sistema"], summary="Origem dos dados, cobertura e governança (RF43, RNF14–RNF17, RNF21)")
def sobre():
    vagas = _json(RAIZ / "data" / "raw" / "vagas_talent_manaus.json").get("meta", {})
    vagas.pop("buscas", None)
    return {
        "ppc": _json(processados() / "cobertura_ppc.json"),
        "coleta_vagas": vagas,
        "normalizacao": {k: v for k, v in _json(processados() / "resumo_normalizacao.json").items() if k != "quarentena_top20"},
        "governanca": {
            "dados_pessoais_de_estudantes": "não coletados, não armazenados, não transmitidos a terceiros (RF42)",
            "dados_de_vagas": "anúncios públicos; e-mails, telefones e links removidos na ingestão (RF41)",
            "base_legal": "anúncios públicos de pessoas jurídicas, tratados para a finalidade acadêmica que justificou sua "
                          "publicação (LGPD, art. 7º, § 3º), com finalidade e minimização (art. 6º, I e III); "
                          "não há tratamento de dados pessoais de usuários",
            "retencao": "dados de vagas mantidos até o fim do semestre letivo 2026.2 e então descartados (docs/DATA_SOURCES.md)",
            "autenticacao": "inexistente por decisão de projeto (documento de requisitos, seção 7.1)",
        },
    }


@app.exception_handler(Exception)
async def erro_interno(request: Request, exc: Exception):  # pragma: no cover
    return JSONResponse(status_code=500, content={"detail": "erro interno", "tipo": type(exc).__name__})



# ------------------------------------------------------------------ página principal
# Montada por último: as rotas da API e /docs têm precedência; o resto é o front-end (index.html, css/, js/, assets/, fonts/).
app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
