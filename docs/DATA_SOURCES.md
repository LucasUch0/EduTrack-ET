# Origem, base legal e retenção dos dados (RF43, RNF14–RNF17)

## 1. Currículo

| Item | Detalhe |
|---|---|
| Documento | Programa de Disciplina, currículo CCO-2024/1, emitido pelo portal acadêmico em 08/10/2026 (`data/raw/programa_disciplinas_cco2024_1.pdf`), com código validador impresso em cada página |
| Conteúdo | 18 disciplinas do 3º ao 7º período: código, créditos, carga horária, período, ementa e bibliografia |
| Complemento | 14 disciplinas do 1º, 2º e 8º períodos informadas pelos autores a partir do histórico acadêmico (`data/raw/grade_cco2024_1.json`), com ementas de referência redigidas de forma conservadora (`data/raw/ementas_referencia.json`) e marcadas como tal em todo o sistema |
| Pendência | 7 das 39 disciplinas da grade não constam das fontes desta versão (RF10a). Basta anexar o Programa de Disciplina correspondente e rodar o pipeline |
| Divergência registrada | ALGORITMOS E TÉCNICAS DE PROGRAMAÇÃO aparece no 1º período do histórico informado e no 3º do programa oficial (código 24692); prevalece o documento oficial |
| Pré-requisitos | Inferidos pelos autores por dependência de conteúdo (`data/raw/prerequisitos.json`); o Programa de Disciplina não os informa. Devem ser validados com a coordenação |
| Base legal | Documento institucional público para a comunidade acadêmica; não contém dados pessoais |

## 2. Vagas de emprego

| Item | Detalhe |
|---|---|
| Fonte | Talent.com Brasil (br.talent.com), anúncios públicos, sem login |
| Verificação do robots.txt | 08/10/2026: as rotas usadas, `/jobs` (busca) e `/view` (anúncio), não estão entre as desautorizadas (`/search-jobs/*`, `/redirect*`, `/ajax/*`, `/convert*` e outras) |
| Período da coleta | 08/10/2026, das 19:22 às 19:42 (UTC) |
| Volume | 288 requisições HTTP com intervalo de 1,5 s; 761 anúncios listados em 54 termos de busca mais 19 termos amplos; 91 anúncios com título de TI tiveram o texto coletado |
| Procedimento | `scripts/coleta_navegador.js`, executado em uma aba do navegador no domínio do portal, porque o ambiente de construção não tinha acesso direto ao site. `edutrack/collect/scrape_talent.py` reproduz o mesmo procedimento em Python |
| Filtros | Manaus/AM (RN04); duplicatas por URL e por (título, empresa) (RF05); funções não técnicas pelo título (vendas, RH etc.); pelo menos 2 habilidades técnicas, ou 1 com título de TI. Resultado: 67 vagas (`data/processed/vagas.json`, motivos em `vagas_descartadas.json`) |
| Dados pessoais | E-mails, telefones e links são removidos na ingestão (RF41). Nomes próprios de recrutadores não são detectados automaticamente; nenhum foi encontrado na revisão desta amostra, e o texto completo só é usado para extrair habilidades |
| Base legal | Anúncios publicados por pessoas jurídicas para divulgação ampla. O tratamento considera a finalidade, a boa-fé e o interesse público que justificaram a publicação (LGPD, art. 7º, § 3º), observa finalidade e minimização (art. 6º, I e III) e não envolve dados de candidatos |

## 3. Estudantes

O sistema não coleta, não armazena e não transmite dados pessoais de estudantes (RF42, RN07). Não há login nem cadastro (seção 7.1 do documento de requisitos). A lista de disciplinas cursadas chega no corpo de uma requisição, é usada em memória e descartada; a resposta é marcada como `Cache-Control: no-store`. A página não usa cookies e não carrega fontes, scripts ou imagens de terceiros (a política de segurança de conteúdo bloqueia qualquer outra origem), de modo que nenhuma requisição sai do servidor da aplicação. Enquanto a aba está aberta, a seleção de disciplinas fica no armazenamento de sessão do navegador (`sessionStorage`), apagado quando a aba é fechada; o armazenamento local (`localStorage`) guarda apenas a preferência de tema e de movimento. A continuidade entre sessões é feita por um arquivo JSON que o próprio estudante salva e reabre (RF31a).

## 4. Retenção (RNF17)

| Conjunto | Prazo |
|---|---|
| Vagas brutas e processadas | até o encerramento do semestre letivo 2026.2, após a defesa; depois, mantidos apenas os agregados (contagens por habilidade) publicados no trabalho |
| PPC e ontologia | mantidos no repositório (documentos institucionais e produção dos autores) |
| Logs de execução | o serviço não grava logs em disco; o iniciador grava em `~/.edutrack-gnn/instalacao.log` apenas a saída da instalação de pacotes, sem dados de uso |
