// Chamadas ao serviço de análise (FastAPI). Nada do que é enviado fica guardado no servidor (RF42, RN07).

export class ErroServico extends Error {
  constructor(mensagem, status) {
    super(mensagem);
    this.status = status;
  }
}

async function pedir(caminho, opcoes = {}, limiteMs = 15000) {
  const controle = new AbortController();
  const relogio = setTimeout(() => controle.abort(), limiteMs);
  const t0 = performance.now();
  try {
    const cabecalhos = { Accept: 'application/json' };
    if (opcoes.body) cabecalhos['Content-Type'] = 'application/json';
    const r = await fetch(caminho, { ...opcoes, headers: cabecalhos, signal: controle.signal, cache: 'no-store' });
    const ms = performance.now() - t0;
    let corpo = null;
    try { corpo = await r.json(); } catch { /* resposta sem JSON */ }
    if (!r.ok) {
      const det = corpo && corpo.detail;
      const msg = typeof det === 'string' ? det
        : (Array.isArray(det) ? det.map((d) => d.msg).join('; ') : `O serviço respondeu com o código ${r.status}.`);
      throw new ErroServico(msg, r.status);
    }
    const servidor = parseFloat(r.headers.get('X-Tempo-Resposta-ms'));
    return { dados: corpo, ms, msServidor: Number.isFinite(servidor) ? servidor : null };
  } catch (e) {
    if (e instanceof ErroServico) throw e;
    if (e.name === 'AbortError') throw new ErroServico('O serviço de análise demorou demais para responder.', 0);
    throw new ErroServico('Não foi possível falar com o serviço de análise. Confira se a janela do iniciar.bat continua aberta.', 0);
  } finally {
    clearTimeout(relogio);
  }
}

const qs = (params) => new URLSearchParams(params).toString();

/** RF27–RF31: trilha, aderência antes e depois, competências complementares. */
export const pedirTrilha = (cursadas, perfil, k, modelo) =>
  pedir('api/trilha', { method: 'POST', body: JSON.stringify({ cursadas, perfil, k, modelo }) });

/** RF32–RF34: diagnóstico curricular do curso. */
export const pedirDiagnostico = (perfil) => pedir(`api/diagnostico?${qs({ perfil })}`);

/** RF35: o mesmo diagnóstico em CSV, gerado pelo serviço. */
export const urlDiagnosticoCsv = (perfil) => `api/diagnostico.csv?${qs({ perfil })}`;
