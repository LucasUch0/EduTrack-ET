# Validação da camada aproximada da normalização (RNF19)

## Primeira versão: razão de caracteres pura

Aceitava um par quando `difflib.SequenceMatcher(...).ratio() >= 0,87`. Aplicada às 32 disciplinas e às 91 vagas, produziu 32 decisões aproximadas, das quais 13 eram falsas (40,6%). Exemplos:

| Termo | Sinônimo aceito | Razão |
|---|---|---|
| Formação | formatação (Suporte Técnico) | 0,889 |
| Supervisor | supervisório (Automação Industrial) | 0,909 |
| Elétrica | eletrônica (Sistemas Embarcados) | 0,889 |
| restore | firestore (NoSQL) | 0,875 |
| linguagem Rust | linguagem R (Análise de Dados) | 0,880 |
| validação de dados | visualização de dados (BI) | 0,872 |
| Programação de CNC | programação em C (C/C++) | 0,882 |

## Versão atual: alinhamento por termo

Um par só é aceito se (a) as formas compactas forem idênticas ("SpringBoot" = "Spring Boot") ou (b) os termos de conteúdo se alinharem um a um, diferindo apenas por flexão de gênero ou número, e a razão de caracteres da frase for >= 0,87. Siglas em linhas escritas inteiramente em maiúsculas deixaram de contar ("OP DE MÁQUINA IA" não é Inteligência Artificial).

Decisões aproximadas aceitas nesta versão, revisadas uma a uma:

| Termo | Habilidade | Escore | Revisão |
|---|---|---|---|
| Gerenciamento e arquivos | Sistemas Operacionais | 0,980 | correta (erro de digitação da ementa) |
| Diagramas de atividade | UML e Modelagem | 0,977 | correta |
| Planode Negócios | Empreendedorismo | 1,000 | correta (espaço perdido no PDF) |
| SpringBoot | Spring Boot | 1,000 | correta |
| Suporte de T.I | Suporte Técnico | 1,000 | correta |
| engenharia de prompts | IA Generativa | 0,976 | correta |
| power shell | Windows/Active Directory | 1,000 | correta |
| QlikSense | BI | 1,000 | correta |

Precisão observada: 8 de 8. A meta de 200 pares do RNF19 não pôde ser atingida porque a camada aproximada é acionada raramente: a camada exata, com 1.169 sinônimos, resolve quase tudo. Para estimar também os erros por omissão, `docs/amostra_validacao_fuzzy.csv` traz os 57 "quase acertos" (termos rejeitados com razão de caracteres >= 0,80) com a coluna `rotulo` em branco para os autores. Numa revisão preliminar, cerca de 8 deles eram correspondências válidas perdidas (por exemplo "testes de aceite" e "e não relacionais"), que podem entrar como sinônimos na ontologia sem mudar o código (RF16).
