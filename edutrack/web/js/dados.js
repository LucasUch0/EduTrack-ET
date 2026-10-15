// Dados reais vindos do serviço de análise (GET /api/interface): PPC, ontologia, vagas,
// sugestões da GNN, métricas da avaliação e origem dos dados. Substitui o conjunto de exemplo.
// O await no topo do módulo faz as telas esperarem os dados antes de montar qualquer coisa.

export let ERRO_CARGA = null;
let P = {};

try {
  const resposta = await fetch('api/interface', { headers: { Accept: 'application/json' }, cache: 'no-store' });
  if (!resposta.ok) throw new Error(`O serviço respondeu com o código ${resposta.status}.`);
  P = await resposta.json();
} catch (erro) {
  ERRO_CARGA = erro;
}

export const META = {
  versao: P.versao || '',
  ppc: P.ppc || {},
  coleta: P.coleta || {},
  perfis: P.perfis || [{ id: 'todos', t: 'Todas as vagas', vagas: 0 }],
  modelo: P.modelo || { padrao: 'tfidf', nomes: {} },
  metricas: P.metricas || { cenarios: {} },
  normalizacao: P.normalizacao || {},
  recomendacao: P.recomendacao || {}
};

/** Nomes das áreas da ontologia; cada competência guarda o índice da sua área. */
export const CATEGORIAS = P.categorias || [];

/** Competências: forma canônica (n), área (cat), variações reconhecidas (syn) e vagas que pedem. */
export const habilidades = (P.habilidades || []).map((h) => ({ ...h, syn: h.syn.slice() }));

/** Disciplinas do PPC com as competências que as ementas ensinam (arestas "ensina" do grafo). */
export const disciplinas = P.disciplinas || [];

/** Pré-requisitos entre disciplinas (RN03). */
export const PREREQ = P.prereq || {};

/** Vagas de TI de Manaus aceitas pelo pipeline, com as competências exigidas. */
export const vagas = P.vagas || [];

/** Disciplina de apoio sugerida pela GNN para competências que nenhuma ementa ensina. */
export const sugestoes = P.sugestoes || {};
export const SUGESTOES_INFO = P.sugestoes_info || {};

/** Quarentena do pipeline: termos não resolvidos com frequência >= 2 (RF15). */
export const QUARENTENA = P.quarentena || [];
