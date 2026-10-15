/*
 * Coleta de vagas usada para o conjunto de dados desta versão (08/10/2026).
 *
 * Executada no console de uma aba aberta em https://br.talent.com (mesma origem,
 * sem login), porque o ambiente de construção do projeto não tinha acesso direto
 * ao portal. Faz exatamente o que edutrack/collect/scrape_talent.py faz:
 *   - só rotas /jobs e /view, permitidas pelo robots.txt (verificado no mesmo dia);
 *   - 1,5 s entre requisições, sem cookies (credentials: "omit");
 *   - filtro de título de TI; JSON-LD JobPosting e, na falta dele, o bloco
 *     "Descrição da vaga" da página;
 *   - remoção de e-mails e telefones antes de guardar o texto.
 * Ao final, JSON.stringify(window.__edu_resultado) contém {meta, vagas}.
 */
(async () => {
  const TERMOS = ["desenvolvedor", "programador", "analista de sistemas", "analista de ti", "tecnologia da informação",
    "software", "engenheiro de software", "full stack", "front end", "back end", "java", "python", ".net", "mobile",
    "android", "web", "analista de dados", "cientista de dados", "engenheiro de dados", "dados", "business intelligence",
    "power bi", "banco de dados", "dba", "inteligência artificial", "machine learning", "suporte técnico", "suporte ti",
    "help desk", "service desk", "técnico de informática", "infraestrutura", "redes", "segurança da informação", "cloud",
    "devops", "qa", "testes", "automação", "automação industrial", "sistemas embarcados", "firmware", "iot", "sap", "erp",
    "totvs", "estágio ti", "estágio desenvolvimento", "estágio tecnologia", "projetos de ti", "governança de ti",
    "computação", "informática", "sistemas"];
  // segunda rodada com termos amplos (mais páginas), usada para ampliar a amostra
  const AMPLOS = [["analista", 10], ["técnico", 8], ["engenheiro", 5], ["estágio", 8], ["especialista", 4],
    ["coordenador", 3], ["consultor", 3], ["assistente", 4], ["tecnologia", 5], ["ti", 5], ["desenvolvimento", 4],
    ["projetos", 3], ["sistemas de informação", 2], ["jovem aprendiz", 3], ["supervisor", 2], ["gerente", 3],
    ["trainee", 2], ["instrutor", 2], ["professor", 2]];
  const PLANO = [...TERMOS.map((t) => [t, 3]), ...AMPLOS];
  const ESPERA = 1500;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const norm = (s) => (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const TI = /(desenvolv|program|software|sistema|\bti\b|t\.i\.|tecnologia|dados|\bdata\b|suporte|\brede|infraestrutura|devops|cloud|nuvem|seguranca da informacao|ciberseg|cyber|full ?stack|front|back.?end|mobile|android|\bios\b|\bweb\b|java|python|\.net|c#|\bsap\b|\berp\b|totvs|protheus|\bbi\b|power ?bi|analytics|\bqa\b|teste|automac|robotic|\bplc\b|\bclp\b|embarcad|firmware|hardware|help ?desk|service ?desk|\bn[123]\b|nivel [123]|\bdba\b|banco de dados|inteligencia artificial|machine learning|\bia\b|\bml\b|\bux\b|\bui\b|scrum|product owner|governanca de ti|telecom|\bsre\b|computac|informatica|iot|arquitet|cientista|engenharia de dados|tecnico de campo|helpdesk|\bnoc\b|\bsoc\b|ciencia de dados|digital|tech|fibra|servidor|eletronic|testador)/;
  const limpar = (t) => (t || "").replace(/[\w.+-]+@[\w-]+(\.[\w-]+)+/g, "[email removido]")
    .replace(/(\+?55[\s.-]?)?\(?\b\d{2}\)?[\s.-]?9?\d{4}[\s.-]?\d{4}\b/g, "[telefone removido]")
    .replace(/https?:\/\/\S+|www\.\S+/g, "[link removido]")
    .replace(/[ \t ]+/g, " ").replace(/\n\s*\n+/g, "\n").trim();
  const textoHtml = (html) => new DOMParser().parseFromString(
    (html || "").replace(/<(br|\/p|\/li|\/h[1-6]|\/div|\/ul|\/ol)[^>]*>/gi, "$&\n"), "text/html").body.textContent;
  const S = { inicio: new Date().toISOString(), reqs: 0, ids: {}, vagas: {}, falhas: [], buscas: [] };
  const obter = async (url) => {
    S.reqs++;
    try { const r = await fetch(url, { credentials: "omit" }); await sleep(ESPERA); return r.ok ? r.text() : null; }
    catch (e) { S.falhas.push([url, String(e)]); await sleep(ESPERA); return null; }
  };
  for (const [termo, maxP] of PLANO) {
    for (let p = 1; p <= maxP; p++) {
      const html = await obter("/jobs?k=" + encodeURIComponent(termo).replace(/%20/g, "+") + "&l=Manaus%2C+AM" + (p > 1 ? "&p=" + p : ""));
      if (!html) break;
      const doc = new DOMParser().parseFromString(html, "text/html");
      const cards = [...doc.querySelectorAll('[data-testid^="jobcard-container-"]')];
      S.buscas.push([termo, p, cards.length]);
      for (const c of cards) {
        const id = c.getAttribute("data-testid").replace("jobcard-container-", "");
        const t = (c.querySelector('h2, h3, [class*="title" i]')?.textContent || "").trim();
        (S.ids[id] ||= { titulo: t, termos: [] }).termos.push(termo);
      }
      if (!cards.length || !doc.querySelector(`a[href*="&p=${p + 1}"]`)) break;
    }
  }
  for (const [id, info] of Object.entries(S.ids)) {
    if (!TI.test(norm(info.titulo))) continue;
    const html = await obter("/view?id=" + id);
    if (!html) continue;
    const doc = new DOMParser().parseFromString(html, "text/html");
    let jp = null;
    for (const s of doc.querySelectorAll('script[type="application/ld+json"]')) {
      try { const o = JSON.parse(s.textContent); for (const g of (o["@graph"] || [o])) if (g["@type"] === "JobPosting") jp = g; } catch (e) { /* ignora */ }
    }
    const base = { id, url: "https://br.talent.com/view?id=" + id, termos_busca: info.termos, data_coleta: new Date().toISOString() };
    if (jp) {
      const end = jp.jobLocation?.address || {};
      S.vagas[id] = { ...base, titulo: jp.title || info.titulo, empresa: jp.hiringOrganization?.name || "", cidade: end.addressLocality || "",
        regiao: end.addressRegion || "", data_publicacao: jp.datePosted || "", tipo_contrato: jp.employmentType || "",
        categoria_ocupacional: jp.occupationalCategory || "", industria: jp.industry || "", descricao: limpar(textoHtml(jp.description)), extracao: "json-ld" };
      continue;
    }
    const rotulo = [...doc.querySelectorAll("span, div, p, h2, h3")].find((e) => e.children.length === 0 && e.textContent.trim() === "Descrição da vaga");
    const corpo = rotulo && (rotulo.nextElementSibling || rotulo.parentElement?.nextElementSibling);
    if (!corpo) { S.falhas.push([id, "sem descrição"]); continue; }
    const h1 = doc.querySelector("h1");
    const cab = h1?.parentElement?.parentElement ? [...h1.parentElement.parentElement.querySelectorAll("span, div, p")]
      .filter((e) => e.children.length === 0).map((e) => e.textContent.trim()).filter(Boolean) : [];
    const k = cab.indexOf("•");
    const local = k > 0 ? cab[k + 1] || "" : "";
    S.vagas[id] = { ...base, titulo: h1?.textContent.trim() || info.titulo, empresa: k > 0 ? cab[k - 1] : "", cidade: local.split(",")[0].trim(),
      regiao: local, data_publicacao: "", data_publicacao_relativa: cab.find((t) => t.startsWith("Há ")) || "", tipo_contrato: "",
      categoria_ocupacional: "", industria: "", descricao: limpar(textoHtml(corpo.innerHTML)), extracao: "dom" };
  }
  window.__edu_resultado = {
    meta: { fonte: "br.talent.com", rota: "/jobs e /view (permitidas pelo robots.txt)", localidade: "Manaus, AM",
      inicio_coleta: S.inicio, fim_coleta: new Date().toISOString(), requisicoes_http: S.reqs, intervalo_entre_requisicoes_s: ESPERA / 1000,
      ids_listados: Object.keys(S.ids).length, vagas_coletadas: Object.keys(S.vagas).length, buscas: S.buscas, falhas: S.falhas.length },
    vagas: Object.values(S.vagas).sort((a, b) => a.id.localeCompare(b.id)),
  };
  console.log("coleta concluída:", window.__edu_resultado.meta);
})();
