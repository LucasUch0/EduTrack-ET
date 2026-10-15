# Relatório de testes — EduTrack-GNN 1.1.0 (09/10/2026)

**Resultado:** dos 86 itens do Documento de Requisitos v1.1 (46 RF, 32 RNF e 8 RN), 76 atendem, 8 atendem com ressalva e 2 ainda não atendem: RNF19 (amostra rotulada da camada aproximada) e RNF24 (repositório Git). A bateria encontrou 15 problemas; todos foram corrigidos e retestados.

## Como foi testado

| Frente | Ferramenta | O que cobre |
|---|---|---|
| Testes automáticos | `python -m unittest discover -s tests -t .` | 93 testes: 92 passam e 1 é falha esperada e marcada (energia da coleta, RF44); `tests/test_requisitos.py` tem os testes por requisito, com o ID no nome |
| Coleta | servidor HTTP falso em 127.0.0.1 | robots.txt, intervalo, User-Agent, teto, falhas de rede, remoção de dados pessoais |
| Recomendação | 400 seleções aleatórias de disciplinas × 6 perfis × k de 1 a 10 × 2 modelos | pré-requisitos (RN03), nada repetido ou já cursado, aderência coerente |
| Diagnóstico e aderência | cálculo independente a partir de `vagas.json` | RF28, RF30, RF32–RF35 conferidos número a número |
| Interface | `scripts/auditoria_interface.py` (Chromium) | 8 abas × 2 temas + diálogo: nome acessível pela árvore de acessibilidade do navegador, contraste de todo texto visível, teclado, reflow, zoom, espaçamento, movimento |
| Reprodutibilidade | pipeline refeito do zero numa cópia limpa, com outra semente de hash | métricas e matrizes de afinidade comparadas com as versionadas |

O axe-core não pôde ser instalado neste ambiente (o registro npm é bloqueado). Por isso a auditoria usa a árvore de acessibilidade do próprio Chromium e verificações próprias. Como conferência cruzada, rode o Lighthouse (aba Lighthouse do DevTools do Chrome, categoria Acessibilidade) com a aplicação aberta.

## Problemas encontrados e corrigidos

| # | Requisito | Problema | Correção |
|---|---|---|---|
| 1 | RF02, RNF20 | Sem acesso ao robots.txt, o coletor quebrava com erro de conexão | Coleta abortada com registro, sem quebrar (postura conservadora: sem robots.txt conferido, nada é coletado) |
| 2 | RNF20 | Um PDF corrompido derrubava a extração do PPC | O erro é registrado e o pipeline segue com a grade declarada |
| 3 | RF20 | Índice de aresta inválido derrubava a validação em vez de ser relatado | A validação relata quantas arestas estão fora do intervalo |
| 4 | RF06 | O log da coleta não trazia a contagem de vagas descartadas | Log e metadados com `descartadas` |
| 5 | RF41 | Um link (site da empresa) estava no arquivo bruto de vagas; o coletor em JavaScript não removia links | Link removido do arquivo bruto; coletor corrigido; os dados processados já estavam limpos e não mudaram |
| 6 | RF40, RNF26 | O perfil de uma vaga com empate dependia da ordem de um conjunto, que muda a cada execução do Python | Desempate pela ordem fixa dos perfis; saídas idênticas com 3 sementes de hash |
| 7 | RNF10, WCAG 2.1.2 / 2.4.3 | Ao abrir um diálogo pelo teclado, o foco não entrava nele | Diálogo abre visível de imediato; foco entra, fica preso e volta ao botão de origem |
| 8 | RNF09, WCAG 2.5.3 | O nome acessível do botão "Dados reais" não continha o texto visível | Nome começa pelo texto visível |
| 9 | RNF12, WCAG 1.4.3 | Linha do aviso da trilha com contraste 3,96:1 no tema claro | Opacidade removida (passa de 4,5:1) |
| 10 | WCAG 1.3.1 | A página inicial pulava de h1 para h3 | Títulos dos passos viraram h2, com o mesmo visual |
| 11 | WCAG 1.4.10 | Rolagem lateral em 320 px em Mercado, Conexões e Trilha | Barras e cartões se ajustam; rótulos de leitor de tela contidos na tabela |
| 12 | WCAG 2.4.7 | O anel de foco dos botões aparecia com atraso (transição) | A transição não inclui mais o contorno |
| 13 | RN08, RNF31 | A documentação da API expunha `/docs/oauth2-redirect` | Rota removida (não há autenticação) |
| 14 | RNF07 | Não havia cache de etapas do pipeline | Impressão digital SHA-256 das entradas de cada etapa; 2ª execução em 0,16 s contra 105 s (−99,8%) |
| 15 | RNF04, RNF25 | Faltava a análise de complexidade; duas constantes de escala estavam no código | `docs/COMPLEXIDADE.md` e seção 3.9 do artigo; constantes movidas para `config.yaml` (grafo idêntico) |

## Requisitos funcionais

| Requisito | Resultado | Evidência |
|---|---|---|
| RF01 | Atende | Buscas com `l=Manaus, AM` e os termos de `config.yaml` |
| RF02 | Atende | robots.txt lido antes de tudo; caminho proibido não é pedido; sem robots.txt, nada é coletado (corrigido) |
| RF03 | Atende | Intervalo medido ≥ o configurado entre todas as requisições; User-Agent descritivo em todas |
| RF04 | Atende | Cada vaga traz título, descrição, cidade, data de coleta e URL, em JSON |
| RF05 | Atende | Duplicatas por URL e por (título, empresa) descartadas |
| RF06 | Atende | Log com coletadas, descartadas, falhas e requisições (corrigido) |
| RF07–RF09 | Atende | 18 disciplinas segmentadas por `DISCIPLINA:` com nome, código, carga, período, ementa e bibliografia; blocos espúrios descartados |
| RF10 | Atende com ressalva | Divergência sinalizada: 32 identificadas de 39 esperadas (o documento ainda cita 29) |
| RF10a | Atende | Disciplina fora da grade vira registro identificável (`fora_da_grade_declarada`) |
| RF11 | Atende | 76 habilidades com id único, categoria válida e sinônimos; nenhum sinônimo aponta para duas habilidades |
| RF12, RF13 | Atende | Duas camadas; limiar 0,87 em `config.yaml`; com 0,99 o termo que 0,87 aceita é rejeitado |
| RF14 | Atende | 3.463 decisões registradas; toda decisão aproximada tem escore ≥ 0,87 |
| RF15 | Atende | Quarentena ordenada por frequência |
| RF16 | Atende | Sinônimo novo no JSON da ontologia resolve sem mudar código |
| RF17 | Atende com ressalva | Grafo heterogêneo com Disciplina, Skill e Vaga em NumPy, não em `HeteroData` do PyTorch Geometric (desvio documentado) |
| RF18, RF19 | Atende | 4 tipos de aresta não vazios; atributos de período, carga, categoria e texto |
| RF20 | Atende | Detecta índice fora do intervalo, tipo vazio e nós isolados (corrigido) |
| RF21, RF22 | Atende | Grafo salvo e recarregado idêntico; subgrafo centrado em disciplina ou habilidade |
| RF23, RF25 | Atende | GraphSAGE treinado; pesos, hiperparâmetros e afinidades persistidos e finitos |
| RF24 | Atende | Partições disjuntas e completas; o grafo de treino só contém arestas de treino; 3 negativas por positiva |
| RF26 | Atende | Disciplinas ordenadas por escore (sem Estágio, TCC e Optativa) |
| RF27 | Atende | Habilidades derivadas das disciplinas; nenhuma consulta interfere na seguinte |
| RF28, RF30 | Atende | Lacunas e aderência antes/depois iguais ao cálculo independente, em todos os perfis |
| RF29 | Atende | Em 400 seleções aleatórias: pré-requisitos sempre cursados ou antes na trilha, nada repetido, nada já cursado, até k itens |
| RF31 | Atende | Perfil restringe as vagas consideradas |
| RF31a | Atende | Exportar, limpar e importar a seleção no navegador restaura as 9 disciplinas |
| RF32–RF34 | Atende | Lacunas, ensinadas sem demanda e ordem por frequência iguais ao cálculo independente |
| RF35 | Atende | CSV com as mesmas lacunas, na mesma ordem, do JSON |
| RF36, RF39 | Atende | P@k e R@k para k = 1, 3, 5 e 10; tabela comparativa com 6 modelos × 2 cenários |
| RF37, RF38 | Atende | TF-IDF nas mesmas partições; tempos de treino e inferência registrados (40 medições) |
| RF40 | Atende | Mesma semente, mesmos escores; pipeline refeito do zero reproduz exatamente métricas e afinidades (corrigido) |
| RF41 | Atende | Nenhum e-mail, telefone ou link nas vagas brutas e processadas (corrigido) |
| RF42 | Atende | O cálculo não grava arquivo; sem cookies; a seleção fica só na aba do navegador |
| RF43 | Atende | `docs/DATA_SOURCES.md` com origem, data e base legal de cada conjunto |
| RF44 | Atende com ressalva | Energia e CO₂ de preparação, avaliação e treino registrados; a da coleta desta versão não, porque ela rodou no navegador (o módulo Python registra) |

## Requisitos não funcionais

| Requisito | Resultado | Evidência |
|---|---|---|
| RNF01 | Atende | Avaliação completa em 98 s numa CPU de 2 núcleos; treino final em 0,2 s; sem GPU |
| RNF02 | Atende | p95 de 10 ms em 30 requisições (limite: 3 s) |
| RNF03 | Atende | Pico de 165 MB na construção do grafo (limite: 2 GB) |
| RNF04 | Atende | `docs/COMPLEXIDADE.md` e seção 3.9 do artigo; normalização linear medida (2,4 a 2,7 µs/caractere de 1x a 8x o corpus) |
| RNF05 | Atende com ressalva | Coletor sem Selenium nem Playwright; o conjunto desta versão foi coletado por script numa aba comum do navegador, como documentado |
| RNF06 | Atende com ressalva | Medição automatizada pela metodologia Green Algorithms; falta a da coleta desta versão (ver RF44) |
| RNF07 | Atende | 2ª execução em 0,16 s contra 105 s da primeira (corrigido) |
| RNF08 | Atende | Teto de requisições respeitado e contador no log |
| RNF09 | Atende | 0 controles sem nome, 0 textos abaixo do contraste mínimo, 0 rótulos fora do nome, nas 8 abas e nos 2 temas |
| RNF10 | Atende | Do primeiro acesso à trilha só com teclado; foco visível em todos os elementos; diálogos prendem e devolvem o foco (corrigido) |
| RNF11 | Atende | Grafo com tabela equivalente; trilha em texto |
| RNF12 | Atende | Menor contraste de texto: 4,65:1; anel de foco: 5,07:1 (escuro) e 6,21:1 (claro) |
| RNF13 | Atende | Competência sem disciplina em losango; sugestão da GNN tracejada; prioridade escrita |
| RNF13a | Atende | Sem cadastro: Montar perfil, marcar, Analisar, Trilha, Gerar |
| RNF14–RNF17 | Atende | Base legal, robots.txt, retenção e minimização documentados; a entrada da API só tem disciplinas, perfil, k e modelo |
| RNF18 | Atende | Cobertura de 85,3% (meta: 85%) |
| RNF19 | **Não atende** | A camada aproximada decidiu só 8 termos; a amostra de 57 quase acertos (`docs/amostra_validacao_fuzzy.csv`) ainda precisa ser rotulada, e 200 pares não existem neste corpus |
| RNF20 | Atende | URL inválida e PDF corrompido registrados sem interromper (corrigido) |
| RNF21 | Atende | Declarado "8 de 8 períodos e 32 de 39 disciplinas" |
| RNF22, RNF23, RNF29 | Atende | Camadas separadas; dependências com versão exata (`==`) |
| RNF24 | **Não atende** | O projeto ainda não está num repositório Git; `.gitignore` incluído |
| RNF25 | Atende | Limiares, caminhos, sementes e escalas em `config.yaml` (corrigido) |
| RNF26 | Atende | Pipeline refeito numa cópia limpa: métricas e afinidades idênticas |
| RNF27 | Atende com ressalva | Linux (Python 3.13) de ponta a ponta; Windows depende do teste no computador dos autores; macOS não testado |
| RNF28 | Atende com ressalva | Sem serviço pago nem banco de dados; roda localmente em vez de no Streamlit Community Cloud (decisão documentada) |
| RNF30, RNF31 | Atende | Nenhum segredo no código; só `POST /api/trilha`, sem escrita |

## Regras de negócio

| Regra | Resultado | Evidência |
|---|---|---|
| RN01 | Atende | Só habilidades da ontologia viram nós; termos em quarentena ficam fora |
| RN02 | Atende | Limiar 0,87 em `config.yaml` |
| RN03 | Atende | 400 seleções aleatórias sem nenhuma violação |
| RN04 | Atende | As 67 vagas são de Manaus |
| RN05 | Atende | k = 5 no serviço e na interface |
| RN06 | Atende com ressalva | As 32 disciplinas identificadas estão no grafo; sem habilidade, Sociologia e Optativa aparecem como nós isolados no relatório; 7 das 39 ainda não constam das fontes |
| RN07 | Atende | Uma nova sessão do navegador começa sem nenhuma disciplina marcada |
| RN08 | Atende | Nenhuma rota de login, conta ou token |

## Acessibilidade (WCAG 2.1 AA)

| Critério | Resultado |
|---|---|
| 1.1.1 Conteúdo não textual | Atende: ícones decorativos ocultos; grafo com nomes por nó e tabela equivalente |
| 1.3.1 Informações e relações | Atende: tabelas com cabeçalho; hierarquia de títulos sem saltos (corrigido) |
| 1.4.3 Contraste mínimo | Atende: nenhum texto ativo abaixo de 4,5:1 (corrigido); só abas bloqueadas, isentas por estarem desativadas |
| 1.4.4 Redimensionar texto | Atende: a 200% (683 px), sem perda de conteúdo nem rolagem lateral |
| 1.4.10 Reflow | Atende: 320 px sem rolagem lateral nas 8 abas (corrigido) |
| 1.4.11 Contraste não textual | Atende: anel de foco a 5,07:1 e 6,21:1 |
| 1.4.12 Espaçamento de texto | Atende: nenhum texto cortado com espaçamento ampliado |
| 2.1.1 e 2.1.2 Teclado, sem armadilha | Atende: percurso completo por teclado; Esc fecha diálogos (corrigido) |
| 2.4.1 Ignorar blocos | Atende: "Pular para o conteúdo" é o primeiro foco |
| 2.4.2, 3.1.1 | Atende: título da página e `lang="pt-BR"` |
| 2.4.3 e 2.4.7 Ordem e foco visível | Atende: ordem lógica; anel imediato em todos os elementos (corrigido) |
| 2.5.3 Rótulo no nome | Atende (corrigido) |
| 4.1.2 Nome, função, valor | Atende: 0 controles sem nome na árvore de acessibilidade do Chromium |
| 4.1.3 Mensagens de status | Atende: avisos e resultados em regiões `aria-live` |

## O que falta, e de quem depende

1. **Testar no Windows (RNF27):** abrir o zip novo com `iniciar.bat` no computador dos autores.
2. **Repositório Git (RNF24):** criar o repositório (por exemplo no GitHub) e versionar o projeto antes da defesa.
3. **Amostra rotulada (RNF19):** rotular os 57 pares de `docs/amostra_validacao_fuzzy.csv` e registrar a taxa de falsos positivos; a meta de 200 pares fica como limitação declarada.
4. **Atualizar o Documento de Requisitos para a v1.2** com os desvios deste relatório (29 → 39 disciplinas, NumPy no lugar do PyTorch Geometric, execução local no lugar do Streamlit Cloud), já listados em `docs/MUDANCAS_v1.2.md`.
