// Script clássico (não módulo): roda mesmo quando o index.html é aberto direto do disco,
// caso em que o navegador bloqueia os módulos e o serviço de análise não está acessível.
if (location.protocol === 'file:') {
  document.addEventListener('DOMContentLoaded', () => {
    const aviso = document.getElementById('protocol-warning');
    if (aviso) aviso.hidden = false;
  });
}
