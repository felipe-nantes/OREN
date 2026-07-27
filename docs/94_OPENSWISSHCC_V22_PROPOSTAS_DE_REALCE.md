# OpenSwissHCC v22 — propostas determinísticas de realce

## Objetivo

Substituir a dependência do localizador venoso, cujo recall retrospectivo por
caso foi 56,76%, por uma varredura multifásica de todo o fígado automático.
Labels e máscaras públicas permanecem fora da geração.

## Geração cega

O algoritmo `whole-liver-joint-enhancement-proposals-v1` calcula relações
arterial/venosa/tardia normalizadas no fígado e gera componentes conexos nos
limiares fixos 2, 3 e 4. Componentes menores que oito voxels são removidos.

Foram processados 84 casos registrados; três fallbacks foram declarados
indisponíveis. O tempo total foi 84,7 s e os casos individuais ficaram em poucos
segundos. Nenhuma inferência foi executada.

## Auditoria retrospectiva de localização

Nos 37 casos positivos com máscaras venosas públicas de desenvolvimento:

| Regra | Recall por caso | Recall por lesão |
|---|---:|---:|
| limiar 2, todos os componentes | 97,30% | 97,30% |
| limiar 3, todos os componentes | 97,30% | 97,30% |
| limiar 4, todos os componentes | 91,89% | 93,24% |
| limiar 3, top 3 por volume | 75,68% | 60,81% |
| limiar 3, top 5 por volume | 83,78% | 67,57% |
| limiar 3, top 10 por volume | 94,59% | 86,49% |

O limiar 3 com top 5 foi escolhido para o próximo piloto por superar 75% de
recall por caso e respeitar o limite prático de candidatos. A seleção é
determinística e não utiliza ground truth durante a geração.

### Artefato formal reproduzível

Os cálculos exploratórios foram substituídos por uma auditoria formal isolada
de toda rota de inferência. O avaliador validou os 87 IDs congelados, os 84
manifestos disponíveis, hashes e tamanhos de todos os NIfTIs, geometrias das 74
máscaras venosas públicas e a separação temporal entre geração cega e abertura
do ground truth. O caso tecnicamente excluído
`anon-openswiss-cb2c5c63fc28b8ee`, ainda presente no arquivo público de labels,
foi registrado como extra e ignorado; ele não foi reinserido na coorte.

Saída autoritativa:

`casos/qualification/openswisshcc_v1/audits/dev_v22_enhancement_localizer_full87_v1`

| Arquivo | SHA-256 |
|---|---|
| `audit.json` | `a07e966048c8111c818dc2dbab473cf40a8307ff99ed986119cad3f948e07bf5` |
| `case_metrics.csv` | `489924a19c5099c845e4be785f5cbf6282f23cd7c1a0e7c59b8e3679add1f67e` |
| `report.md` | `3dc0baaa8ab27554e15d1b40d476b05d2565a71fd7d352e6ee0c65c556756310` |

Essa auditoria não calcula especificidade ou acurácia: presença de proposta é
localização, não classificação. Ela também declara explicitamente que nenhuma
máscara foi usada na inferência ou enviada ao MedGemma e que o holdout não foi
aberto.

## Classificação escalar

As features núcleo/contexto recalculadas sobre `t3/top5` não discriminaram as
classes: melhor AUC 0,6222, sensibilidade 58,97% e especificidade 66,67% no
melhor ponto equilibrado. Portanto, nenhum limiar ou calibrador foi aprovado.

Esse resultado não invalida a representação visual: a localização cobre 83,78%
dos casos e o escalar agrega candidatos distintos, perdendo morfologia e
continuidade. O próximo teste será o MedGemma 4B como classificador visual de
cada stack, após revisão humana técnica.

## Galeria piloto

A primeira galeria,
`development_review_gallery_v22_enhancement_t3_top5_pilot10_v1`, foi invalidada
antes do congelamento: apesar do nome `top5`, o seletor legado interrompia a
renderização quando três componentes cobriam 75% do volume candidato. Seus 30
stacks correspondiam de fato a `top3`, cuja cobertura retrospectiva por caso é
75,68%. Ela não deve ser revisada, assinada ou enviada ao MedGemma.

A galeria autoritativa é
`development_review_gallery_v22_enhancement_t3_exact_top5_pilot10_v2`. Ela
contém 10 casos e 48 stacks: oito casos possuem cinco componentes e dois
possuem apenas quatro. Em todos os casos, todos os componentes disponíveis até
o limite cinco foram renderizados, com cobertura declarada de 100% do conjunto
selecionado. A assinatura da galeria é
`bab2d74b9b6efd119ee8ba52ca4560c1ea31e0ea02210a313c2f826f667d97cb`.

Os stacks contêm T1 dinâmica, T2, DWI e ADC e não contêm contorno, PHI, labels
ou máscara pública de lesão.

O revisor deve verificar:

1. candidato dentro do fígado e crop não cortado;
2. continuidade entre início, centro e fim;
3. correspondência anatômica entre sequências;
4. contraste suficiente;
5. ausência de PHI, overlays e pixels corrompidos.

Aprovação visual não significa concordância diagnóstica. O 4B só pode ser
executado depois da aprovação técnica explícita.

### Preflight antes da revisão

O preflight fail-closed validou os 48 stacks, hashes, manifestos do localizador
determinístico, seleção exact-top5 e vínculo com a auditoria retrospectiva. Seu
status é `passed_pending_explicit_human_review`; portanto ele não autoriza nem
executa inferência.

Artefato:

`casos/qualification/openswisshcc_v1/prepared/development_preflights_v22/enhancement_t3_exact_top5_pilot10_v2.json`

SHA-256:

`686503929568153b369a8d1b54e007505b3fa72c5501892c9db049fbc8040c48`

O orçamento temporal conservador do exact-top5 está documentado em
`docs/95_OPENSWISSHCC_V22_ORCAMENTO_TEMPORAL_TOP5.md`. A projeção pelo pior
tempo histórico chega a 180,1377 segundos e, portanto, não substitui a medição
real do piloto após a revisão humana.

## Segurança metodológica

- o holdout v21 consumido não foi usado para escolher limiar ou componente;
- máscaras do holdout permanecem fechadas;
- as máscaras de desenvolvimento foram abertas somente na auditoria
  retrospectiva, depois das propostas cegas;
- os bundles v1 com proveniência incorreta foram preservados como inválidos e
  não usados na avaliação final;
- a versão v2 declara corretamente máscaras determinísticas, não derivadas de
  modelo de lesão;
- nenhum ganho de acurácia é declarado antes de validação independente.
