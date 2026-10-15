// Sobre: ficha técnica, avaliação do modelo, origem dos dados e limitações (RF10, RF39, RF43, RNF21).

import { CATEGORIAS, habilidades, disciplinas, vagas, META } from './dados.js';
import { COBERTURA } from './catalog.js';
import { PPC, COLETA, METRICAS, MODELO_PADRAO } from './config.js';
import { esc, dataCurta, num, pct, br } from './ui.js';

const el = (id) => document.getElementById(id);

const ORDEM_MODELOS = ['tfidf', 'gnn', 'gnn_pura', 'gnn_l0', 'coocorrencia', 'popularidade'];
const NOMES_TABELA = {
  tfidf: 'TF-IDF (linha de base textual)', gnn: 'GNN híbrida (GraphSAGE + texto)', gnn_pura: 'GNN pura (GraphSAGE)',
  gnn_l0: 'GNN sem troca de mensagens', coocorrencia: 'Coocorrência (heurística)', popularidade: 'Popularidade'
};

function tabelaAvaliacao() {
  const cen = (METRICAS.cenarios || {}).texto_mascarado || {};
  const linhas = ORDEM_MODELOS.filter((k) => cen[k]).map((k) => {
    const m = cen[k];
    const v = (c) => (m[c] ? num(m[c].media) : '—');
    return `<tr${k === MODELO_PADRAO ? ' class="destaque"' : ''}><td style="font-weight:600">${esc(NOMES_TABELA[k])}${k === MODELO_PADRAO ? ' <span class="tag tag-mint">padrão da aplicação</span>' : ''}</td>`
      + `<td class="mono">${v('P@1')}</td><td class="mono">${v('P@5')}</td><td class="mono">${v('R@5')}</td><td class="mono">${v('R@10')}</td><td class="mono">${v('AUC')}</td></tr>`;
  });
  el('avalHost').innerHTML = '<table class="tbl"><caption class="sr">Desempenho dos modelos no cenário de vínculos latentes, média de 20 sorteios</caption>'
    + '<thead><tr><th scope="col">Modelo</th><th scope="col">P@1</th><th scope="col">P@5</th><th scope="col">R@5</th><th scope="col">R@10</th><th scope="col">AUC</th></tr></thead>'
    + `<tbody>${linhas.join('')}</tbody></table>`;

  const t = cen.tfidf;
  const g = cen.gnn;
  const c = cen.coocorrencia;
  const p = METRICAS.wilcoxon_gnn_vs_tfidf_r5_latente;
  el('avalSub').textContent = `${METRICAS.arestas_ensina || ''} ligações disciplina–competência, divididas ${METRICAS.particao || '70/10/20'} em ${METRICAS.sorteios || 20} sorteios; trechos das ementas que denunciavam as ligações de teste apagados (vínculos latentes)`;
  const l0 = cen.gnn_l0;
  const n = METRICAS.arestas_ensina;
  const porDisc = n && disciplinas.length ? ` (cerca de ${num(n / disciplinas.length, 1)} por disciplina)` : '';
  let estrutura = '';
  if (l0 && g && l0['R@5'].media > g['R@5'].media) {
    estrutura = ` Já a variante sem troca de mensagens (${pct(l0['R@5'].media)}) foi melhor que a completa: com ${n || 'poucas'} ligações${porDisc}, a vizinhança de cada ponto é pequena demais para a agregação acrescentar informação, e o texto das ementas ainda carrega mais sinal que a estrutura do grafo.`;
  } else if (n) {
    estrutura = ` Com ${n} ligações${porDisc}, o texto das ementas ainda carrega mais sinal que a estrutura do grafo.`;
  }
  el('avalLeitura').innerHTML = (t && g && c)
    ? `<p>O TF-IDF reencontrou a disciplina certa entre as cinco primeiras em ${pct(t['R@5'].media)} dos casos, contra ${pct(g['R@5'].media)} da GNN híbrida${p != null ? ` (teste de Wilcoxon, ${p < 0.001 ? 'p &lt; 0,001' : `p = ${num(p, 3)}`})` : ''}. A GNN superou as referências que só usam a estrutura, como a coocorrência (${pct(c['R@5'].media)}): ela aprende algo além da contagem de ligações.${estrutura}</p>`
      + '<p>Por isso a aplicação ordena a trilha, por padrão, com o modelo que foi melhor na avaliação, e usa a GNN onde o texto não tem o que dizer: sugerir uma disciplina de apoio para competências que nenhuma ementa cita. A GNN pode ser escolhida em "Ajustes", na tela da trilha.</p>'
    : '<p>Métricas indisponíveis nesta execução.</p>';
}

/** Anúncios que o portal ainda listava na coleta, mas publicados há mais de um ano ou sem data exata. */
function idadeDosAnuncios() {
  const coleta = Date.parse(COLETA.data);
  const umAno = 365 * 864e5;
  const antigos = vagas.filter((v) => v.publicada && coleta - Date.parse(v.publicada) > umAno).length;
  const semData = vagas.filter((v) => !v.publicada && v.publicada_relativa && v.publicada_relativa.includes('+')).length;
  if (!antigos && !semData) return '';
  const partes = [];
  if (antigos) partes.push(`${antigos} ${antigos === 1 ? 'anúncio foi publicado' : 'anúncios foram publicados'} há mais de um ano`);
  if (semData) partes.push(`${semData} só ${semData === 1 ? 'informa' : 'informam'} “há mais de 30 dias”`);
  return `${partes.join(' e ')}; o portal ainda os listava na coleta, mas parte pode já ter sido encerrada.`;
}

export function renderSobre() {
  const c = COBERTURA;
  const periodos = `${c.periodos} de ${c.totalPeriodos} períodos`;
  const discs = `${c.disciplinas} de ${c.esperadas} disciplinas`;
  const nz = META.normalizacao || {};

  el('aboutPpc').textContent = `PPC ${PPC.codigo} · ${periodos} · ${discs}`;
  el('aboutExtracao').textContent = `${c.oficiais} com programa oficial · ${c.referencia} com ementa de referência`;
  el('aboutVagas').textContent = `${COLETA.aceitas} vagas de TI de ${COLETA.filtro} · coleta de ${dataCurta(COLETA.data)}`;
  el('aboutSkills').textContent = `${habilidades.length} competências · ${CATEGORIAS.length} áreas · ${(nz.sinonimos || 0).toLocaleString('pt-BR')} sinônimos · limiar ${num(nz.limiar || 0.87)}`;
  el('aboutModelo').textContent = 'GraphSAGE heterogêneo em NumPy, comparado ao TF-IDF e a referências estruturais';
  const cob = nz.cobertura || {};
  el('comoCob').textContent = cob.cobertura
    ? `${br((100 * cob.cobertura).toFixed(1))}% dos termos técnicos das vagas foram reconhecidos (${cob.termos_resolvidos} de ${cob.termos_elegiveis}; meta de 85%).`
    : '';


  el('passo2').textContent = `O que ${COLETA.aceitas} vagas de tecnologia de Manaus pedem e você ainda não aprendeu.`;
  el('rodape').textContent = `EduTrack-GNN ${META.versao ? `v${META.versao} ` : ''}· TCC de Ciência da Computação · FAMETRO, 2026 · Dados: PPC ${PPC.codigo} e ${COLETA.fonte} (${dataCurta(COLETA.data)}).`;

  const origens = [
    ['Vagas de tecnologia', `${COLETA.fonte} (${COLETA.dominio}), filtro ${COLETA.filtro}; ${COLETA.listados} anúncios listados, ${COLETA.coletadas} coletados, ${COLETA.aceitas} aceitos; robots.txt verificado; ${COLETA.requisicoes} requisições com ${num(COLETA.intervalo, 1)} s de intervalo`, dataCurta(COLETA.data), 'Anúncios públicos de pessoas jurídicas, tratados para a finalidade acadêmica (LGPD, art. 7º, § 3º); e-mails, telefones e links removidos na ingestão'],
    ['Grade e ementas', `PPC ${PPC.codigo} da ${PPC.instituicao}: Programa de Disciplina oficial (${c.oficiais} disciplinas) e disciplinas informadas pelos autores a partir do histórico acadêmico (${c.referencia})`, '08/10/2026', 'Documento institucional; sem dados pessoais'],
    ['Vocabulário de competências', `Ontologia curada pelos autores (skills_ontology.json): ${habilidades.length} competências, ${(nz.sinonimos || 0).toLocaleString('pt-BR')} sinônimos`, 'Versão do pipeline', 'Sem dados pessoais'],
    ['Seleção do estudante', 'Disciplinas marcadas nesta página', 'Não é guardada', 'Não há tratamento de dado pessoal: sem cadastro, sem login, cálculo em memória e descarte']
  ];
  el('origemHost').innerHTML = '<table class="tbl"><caption class="sr">Origem dos dados</caption><thead><tr><th scope="col">Conjunto</th><th scope="col">Origem</th><th scope="col">Data</th><th scope="col">Base legal e tratamento</th></tr></thead><tbody>'
    + origens.map((o) => `<tr><td style="font-weight:600">${esc(o[0])}</td><td style="color:var(--ink-2)">${esc(o[1])}</td><td class="mono">${esc(o[2])}</td><td style="color:var(--ink-2)">${esc(o[3])}</td></tr>`).join('')
    + '</tbody></table>';

  el('limitesHost').innerHTML = [
    `${c.esperadas - c.disciplinas} das ${c.esperadas} disciplinas ainda não foram incorporadas e ${c.referencia} usam ementa de referência.`,
    `As vagas vêm de um único portal e de um único dia (${dataCurta(COLETA.data)}); a demanda é um retrato, não uma série histórica.`,
    idadeDosAnuncios(),
    'A ontologia e os pré-requisitos foram curados pelos autores e precisam de validação da coordenação.',
    'As ligações disciplina–competência saem do texto das ementas: uma ementa ≠ a turma real, e o que não está escrito não é contado.',
    'As disciplinas de apoio sugeridas pela GNN e a usabilidade da interface ainda não foram avaliadas com pessoas.',
    'O EduTrack dá uma sugestão estatística, não orientação profissional.'
  ].filter(Boolean).map((t) => `<p>${esc(t)}</p>`).join('');

  tabelaAvaliacao();
}
