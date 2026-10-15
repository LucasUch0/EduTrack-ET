// Parâmetros da interface (RNF25). PPC, coleta, perfis e métricas vêm do serviço (dados.js).

import { META } from './dados.js';

/** Grade: 8 de 8 períodos e as disciplinas identificadas frente às esperadas (RF10, RN06, RNF21). */
export const PPC = {
  codigo: META.ppc.codigo || 'CCO-2024/1',
  instituicao: META.ppc.instituicao || 'FAMETRO',
  periodosProcessados: META.ppc.periodos_processados || [],
  totalPeriodos: META.ppc.total_periodos || 8,
  disciplinasEsperadas: META.ppc.disciplinas_esperadas || 0,
  comProgramaOficial: META.ppc.com_programa_oficial || 0,
  comEmentaReferencia: META.ppc.com_ementa_referencia || 0
};

export const COLETA = {
  fonte: META.coleta.fonte || 'Talent.com Brasil',
  dominio: META.coleta.dominio || 'br.talent.com',
  filtro: META.coleta.filtro || 'Manaus/AM',
  data: META.coleta.data || '',
  listados: META.coleta.anuncios_listados || 0,
  coletadas: META.coleta.vagas_coletadas || 0,
  aceitas: META.coleta.vagas_aceitas || 0,
  requisicoes: META.coleta.requisicoes || 0,
  intervalo: META.coleta.intervalo_s || 0
};

/** k padrão (RN05) e valores de k avaliados (RF36). */
export const K_PADRAO = META.recomendacao.k_padrao || 5;
export const K_OPCOES = [1, 3, 5, 10];

/** Parcela das vagas a partir da qual uma lacuna tem prioridade alta ou média. */
export const PRIORIDADE = { alta: 0.2, media: 0.08 };

/** Proporção mínima de requisitos para a vaga contar como "ao seu alcance". */
export const ALCANCE_MINIMO = 0.6;

/** Modelos de afinidade oferecidos: "auto" usa o melhor da avaliação experimental. */
const nomes = META.modelo.nomes || {};
export const MODELO_PADRAO = META.modelo.padrao || 'tfidf';
// `t` é o rótulo da opção, `d` a explicação curta e `curto` o nome usado no meio de frases.
export const MODELOS = {
  auto: { t: 'Recomendado', d: `o que mais acertou nos testes · ${nomes[MODELO_PADRAO] || MODELO_PADRAO}`, curto: 'método recomendado' },
  gnn: { t: 'Rede neural de grafos', d: `experimental · ${nomes.gnn || 'GNN híbrida (GraphSAGE)'}`, curto: 'rede neural de grafos (experimental)' },
  tfidf: { t: 'Comparação de textos', d: nomes.tfidf || 'TF-IDF', curto: 'comparação de textos' }
};
/** Chave do modelo que o serviço usa de fato para cada opção. */
export const modeloEfetivo = (m) => (m === 'auto' ? MODELO_PADRAO : m);

/** Áreas de vaga que restringem a recomendação e o diagnóstico (RF31). */
export const PERFIS = Object.fromEntries(META.perfis.map((p) => [p.id, { t: p.t, vagas: p.vagas }]));

/** Precision@k e Recall@k da avaliação real (RF36, RF37). */
export const METRICAS = META.metricas;

export const STORAGE = {
  tema: 'edutrack-gnn-tema',
  movimento: 'edutrack-gnn-movimento',
  progresso: 'edutrack-gnn-progresso'
};

/** Identificação do arquivo de seleção exportado (RF31a). */
export const ARQUIVO_SELECAO = { formato: 'edutrack-selecao', versao: 2 };
