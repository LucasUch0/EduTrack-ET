# EduTrack-GNN

Compara o que o curso de Ciência da Computação da FAMETRO ensina (PPC CCO-2024/1) com o que as vagas de tecnologia de Manaus pedem, mostra ao estudante o que falta e recomenda uma trilha de disciplinas. Usa um grafo de conhecimento (disciplinas, competências e vagas) e compara uma rede neural de grafos (GraphSAGE) com TF-IDF.

TCC de Ciência da Computação, Centro Universitário FAMETRO, 2026.
Autores: Lucas Uchoa Rebouças e Alexandre Marinho Barroso. Orientação: Profa. MBA Luana Leal.

## Como rodar

**Windows:** instale o Python 3.10 ou mais novo (marcando "Add python.exe to PATH") e dê dois cliques em `iniciar.bat`.
**Linux/macOS:** `./iniciar.sh`

O script cria o ambiente, instala as dependências na primeira vez e abre o navegador. Manualmente:

```
python -m pip install -r requirements.txt
python -m uvicorn edutrack.api.main:app --port 8000
```

Abra http://127.0.0.1:8000. A documentação da API fica em `/docs`. O grafo e o modelo já treinados acompanham o projeto: nada precisa ser treinado para usar.

**Hospedagem:** o `render.yaml` publica a aplicação no Render (New → Blueprint).

## O que a aplicação faz

1. **Suas disciplinas:** o estudante marca o que já concluiu.
2. **O que falta:** sua cobertura do mercado e as competências que faltam, por prioridade.
3. **Sua trilha:** as disciplinas que mais aumentam a cobertura, na ordem em que dá para cursá-las.

Também há **Mercado** (as vagas e as competências mais pedidas), **Coordenação** (lacunas do curso para o NDE) e **Sobre** (método, avaliação, origem dos dados e limitações).

## Resultados (coleta de 08/10/2026)

- 32 de 39 disciplinas do PPC e 67 vagas de TI de Manaus.
- Avaliação em 20 sementes: o TF-IDF acertou mais que a GNN (Recall@5 de 0,70 contra 0,51), então a aplicação usa o TF-IDF por padrão. A GNN supera as referências simples e sugere disciplinas de apoio para competências que nenhuma ementa cita.
- O curso cobre 51% da demanda das vagas.

## Reproduzir o pipeline

```
python -m pip install -r requirements-pipeline.txt
python scripts/run_pipeline.py              # PPC → normalização → avaliação → modelo final (~2,5 min)
python -m unittest discover -s tests -t .   # 93 testes, um por requisito
```

Parâmetros em `config.yaml`. Detalhes dos testes em `docs/RELATORIO_TESTES.md`.

## Estrutura

| Pasta | Conteúdo |
|---|---|
| `edutrack/` | coleta, extração do PPC, normalização, grafo, modelo, recomendação, API e página web |
| `data/` | dados brutos (PPC, vagas), dados processados e vocabulário de competências |
| `artifacts/` | grafo, modelo treinado e métricas |
| `scripts/` | pipeline, auditoria de acessibilidade, figuras |
| `tests/` | testes automatizados |
| `docs/` | origem dos dados, relatório de testes, validação |

## Privacidade

Sem login, cadastro ou banco de dados. As disciplinas marcadas ficam só na aba do navegador e são descartadas pelo servidor depois do cálculo. Os anúncios de vaga tiveram e-mails e telefones removidos na coleta. Veja `docs/DATA_SOURCES.md`.
