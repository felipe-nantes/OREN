# V23 retrospectiva multicohort — Fase 3

Data: 23 de julho de 2026  
Uso: pesquisa, com revisão humana obrigatória

## Objetivo

Completar, sem abrir labels ou máscaras públicas de lesão, a matriz de sinais
necessária para avaliar o v23 nos 132 casos OpenSwissHCC:

```text
80% v11
+
20% candidate_weighted_linearity
```

A Fase 3 não calculou scores, predições, limiares out-of-fold ou métricas. Ela
apenas reproduziu a mesma fonte determinística da feature geométrica v23 nos
casos consumidos do antigo holdout.

## Implementação

Foi criado:

- `dtwin/benchmark/v23_retrospective_multicohort_phase3.py`;
- `tools/prepare_v23_retrospective_multicohort_phase3.py`;
- `tests/test_v23_retrospective_multicohort_phase3.py`.

Para os 43 casos de holdout com alinhamento multifásico aprovado, a execução
reproduziu exatamente:

1. normalização robusta arterial, venosa e tardia na máscara hepática;
2. mapa determinístico de realce conjunto;
3. limiar predefinido `t3`;
4. seleção dos cinco maiores componentes conectados;
5. `candidate_weighted_linearity` em geometria física.

Os volumes candidatos foram persistidos e revalidados independentemente contra
as features registradas. Todos os arquivos de imagem efetivamente consumidos
foram novamente submetidos a SHA-256 antes do uso.

## Resultado técnico

| Item | Resultado |
|---|---:|
| Casos no protocolo | 132 |
| Entradas v23 exatas completas | 130 |
| Shapes development preservados | 87 |
| Shapes holdout gerados agora | 43 |
| Falhas técnicas explícitas | 2 |
| Labels lidos | 0 |
| Máscaras de lesão lidas | 0 |
| Predições calculadas | 0 |
| Métricas calculadas | 0 |

As duas falhas permaneceram no denominador e deverão contar como erro:

1. `anon-openswiss-cb2c5c63fc28b8ee`: exclusão técnica cega preexistente por
   degradação multissequência severa;
2. `anon-openswiss-70e5cfd52cd33c59`: alinhamento multifásico abaixo do gate
   congelado; o fallback venoso não foi convertido artificialmente em uma
   feature v23 multifásica.

Nenhum sinal foi fabricado para esses casos.

## Artefato congelado

Diretório:

```text
casos/qualification/openswisshcc_v1/prepared/retrospective_multicohort_phase3_v1
```

Assinatura da Fase 3:

```text
9463b2fdf65bb2e1e30af7b40cd9957cb5f7e46cdc03aa579bf52d9655af990f
```

Hashes principais:

```text
exact_v23_signals.jsonl
290d003436e85cb82a397c011a387e506161fde1de062b2779fec6020336a5f0

holdout_shape_features.jsonl
5a831bbdadcab1f09daaba0c2c69b0bac83444a75c391f72e9c3fd6fed1ed911

technical_failures.jsonl
4a4201b6d0a6d5a6b6258606b21659856dd05a584cdd8f37712519621398f8c4
```

## Próximo gate

A Fase 4 deverá usar exclusivamente essa matriz congelada para gerar predições
por paciente:

- LOOCV como estimador principal;
- ECDF e limiar ajustados somente no conjunto de treino de cada fold;
- 50×5-fold estratificado como robustez;
- as duas falhas técnicas contabilizadas como erro;
- IC 95%, matriz de confusão e ROC-AUC;
- nenhuma seleção baseada no melhor fold.

Somente após congelar todas as predições out-of-fold os labels protegidos serão
associados para calcular as métricas.
