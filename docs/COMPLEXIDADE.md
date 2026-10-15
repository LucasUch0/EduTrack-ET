# Complexidade das rotinas de normalização e de montagem do grafo (RNF04)

Notação: *n* = caracteres de um texto; *S* = formas de busca do dicionário exato (1.193 nesta versão: nomes e sinônimos das 76 habilidades, sem repetição); *ℓ* = comprimento do maior
sinônimo; *c* = termos candidatos de um texto; *B* = sinônimos no bloco de comparação da camada aproximada;
*D*, *H*, *J* = disciplinas, habilidades e vagas; *k_j* = habilidades da vaga *j*; *E* = arestas; *T* = palavras do corpus;
*F* = vocabulário do TF-IDF; *r* = dimensão da SVD.

## Normalização (`edutrack/normalize/normalize_skills.py`)

| Etapa | Custo | Justificativa |
|---|---|---|
| Índices (uma vez) | O(Σ\|s\|) | uma passada sobre os sinônimos para o dicionário exato, a forma compacta e os blocos |
| Camada exata | O(n·ℓ) típico; O(n·Σ\|s\|) no pior caso | uma expressão regular com os *S* sinônimos, do mais longo ao mais curto; o `re` do Python tenta as alternativas em cada posição, mas falha cedo na primeira letra |
| Candidatos | O(n) | segmentação por separadores e tokens técnicos |
| Camada aproximada | O(c·B·ℓ²) | cada candidato só é comparado aos sinônimos do mesmo bloco (mesmo número de palavras e mesmo prefixo de 4 letras): em média 1,8 e no máximo 17 sinônimos, contra 1.193 sem bloco; `SequenceMatcher` é quadrático no comprimento |
| Corpus inteiro | O(Σ_docs (n·ℓ + c·B·ℓ²)) | linear no tamanho do corpus, porque *ℓ* e *B* não crescem com ele |

Medição (`python` 3.13, 2 núcleos): 2,62 / 2,42 / 2,49 / 2,74 µs por caractere com 1x, 2x, 4x e 8x o corpus de vagas
(0,19 a 1,54 milhão de caracteres). O tempo por caractere é constante, ou seja, o crescimento é linear.

## Montagem do grafo (`edutrack/graph/hetero.py`, `construir`)

| Etapa | Custo | Justificativa |
|---|---|---|
| Nós e índices | O(D + H + J) | dicionários de id para posição |
| Arestas ensina, exige, pré-requisito | O(E) | uma passada sobre as listas de origem |
| Coocorrência | O(Σ_j k_j²) | todos os pares de habilidades de cada vaga; *k_j* ≤ 22 nesta versão |
| Atributos textuais | O(T + (D+H+J)·F·r) | TF-IDF linear nas palavras; SVD truncada randomizada |
| Validação (RF20) | O(V + E) | graus por `np.add.at` e conferência de intervalos |

Medição: com 1x, 2x e 4x as vagas, 175 / 242 / 376 nós e 1.272 / 2.410 / 3.444 arestas, a montagem levou 0,18 s e
0,24 s nas duas maiores (a primeira chamada, 1,28 s, inclui o carregamento do scikit-learn). O pico de memória da
construção foi de 165 MB (RNF03: até 2 GB).

## Demais rotinas, para referência

* Treino da GraphSAGE: O(épocas · L · (E·h + V·h²)), com *L* = 2 camadas e *h* = 32; cerca de 1,2 s por sorteio.
* Trilha (gulosa): O(k · |candidatas| · H) por consulta; p95 de 10 ms na API.
