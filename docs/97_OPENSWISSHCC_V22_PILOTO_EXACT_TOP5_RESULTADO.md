# OpenSwissHCC v22 — resultado do piloto exact-top5

## Estado

O protocolo v22 foi executado somente nos dez casos de desenvolvimento previamente
congelados. O holdout OpenSwissHCC não foi reaberto e nenhuma máscara de lesão foi
usada na inferência ou enviada ao MedGemma.

Este piloto foi encerrado como **falha científica**, apesar de ter passado por todos
os gates técnicos e temporais. Ele não deve ser expandido para os 87 casos nem usado
para qualificar o sistema final.

## Proveniência congelada

- galeria: `development_review_gallery_v22_enhancement_t3_exact_top5_pilot10_v2`;
- assinatura da galeria: `bab2d74b9b6efd119ee8ba52ca4560c1ea31e0ea02210a313c2f826f667d97cb`;
- revisor: `jm`;
- assinatura da revisão: `69c4013221e1d45ef05ae993b96e5df9efaaf937193a3fef43d12ea5fcdac3ce`;
- protocolo de scoring: `353775c0bd01e7ab8c9fe4243e00243f96c9d8bda8bbbfeb32177eba21a45ad8`;
- protocolo de avaliação: `6de4e026336c6d5f092b3b67dd17068a10459a2c2300bf4843187796c9e799d8`;
- modelo: `google/medgemma-1.5-4b-it`, NF4, CUDA;
- casos: 10, sendo 4 positivos e 6 negativos;
- chamadas candidatas: 48, sem retry automático.

Os labels públicos de desenvolvimento foram abertos somente depois de `summary.json`
e `run_context.json` demonstrarem a conclusão das 48 predições cegas.

## Resultado primário predefinido

| Métrica | Resultado | Meta |
|---|---:|---:|
| Sensibilidade | 50,00% (2/4) | >=75% |
| Especificidade | 0,00% (0/6) | >=75% |
| Tempo máximo do scoring preparado | 80,2126 s | <=180 s |
| Inconclusivos | 1 | contam como erro |

Matriz de confusão:

```text
TP = 2
TN = 0
FP = 6
FN = 2
```

O gate conjunto `75/75/180` falhou. O piloto não qualifica o sistema final e também
não demonstra o tempo end-to-end desde DICOM bruto, pois mediu somente o scoring dos
candidatos pré-computados.

## Diagnóstico do ramo

A regra congelada marcou o caso como positivo quando qualquer candidato foi positivo.
Isso produziu ao menos uma chamada positiva ou inconclusiva em todos os seis negativos.
Ao mesmo tempo, dois dos quatro positivos tiveram todos os candidatos classificados
como negativos.

Como diagnóstico secundário, não elegível para substituir o endpoint primário, o score
contínuo máximo por candidato apresentou ROC-AUC de 0,0833 neste piloto. Os scores dos
negativos tenderam a ser maiores que os dos positivos. Portanto, ajuste pós-hoc de
limiar ou expansão para 87 casos não são justificáveis para esta representação.

Interpretação: as propostas determinísticas de realce localizaram regiões, mas o 4B
respondeu fortemente a realce benigno, vasos ou pseudolesões e não separou essas regiões
de lesões focais. O problema não foi timeout, integridade ou cobertura; foi discriminação
visual.

## Decisão

1. Não expandir o v22 exact-top5 para os 87 casos.
2. Não recalibrar o v22 no mesmo piloto.
3. Preservar os artefatos como resultado negativo auditável.
4. Retomar o ramo v11/v20 no desenvolvimento, que foi o mais próximo do objetivo:
   - v11 isolado, diagnóstico secundário LOOCV: sensibilidade 74,36% e especificidade 75,00%;
   - v20 primário LOOCV: sensibilidade 69,23% e especificidade 77,08%.
5. A próxima hipótese deve buscar resgatar falsos negativos do v11 sem aumentar falsos
   positivos, usando validação interna estritamente aninhada. O holdout v21 consumido
   não pode participar dessa seleção.

## Auditoria posterior de combinação com o v11

Foi feita uma análise exploratória somente em desenvolvimento, sem publicar protocolo
novo e sem tocar no holdout, para verificar se as 42 features determinísticas de realce
do v22 acrescentavam sinal ao v11. A seleção da feature, direção e peso foi feita dentro
de cada divisão interna; cada caso externo permaneceu fora dessa seleção.

Nos 84 casos que possuíam as features de realce, o resultado externo foi:

```text
TP = 25
TN = 36
FP = 9
FN = 14
sensibilidade = 64,10%
especificidade = 80,00%
```

Essa combinação piorou a sensibilidade e não deve ser transformada em v23. O resultado
reforça que intensidade dinâmica isolada não resolve o gargalo. O próximo ramo deve
testar evidência não redundante: morfologia compacta versus tubular/vascular e
confirmação determinística em T2, DWI e ADC, sempre com avaliação aninhada no
desenvolvimento antes de qualquer nova inferência 4B.

## Artefatos

- `casos/qualification/openswisshcc_v1/prepared/development_reviews_v22/enhancement_t3_exact_top5_pilot10_review_jm.json`
- `casos/qualification/openswisshcc_v1/prepared/development_protocols_v22/enhancement_t3_exact_top5_pilot10_score_4b_v1.json`
- `casos/qualification/openswisshcc_v1/scores/dev_v22_enhancement_t3_exact_top5_pilot10_4b_v1/`
- `casos/qualification/openswisshcc_v1/evaluations/dev_v22_enhancement_t3_exact_top5_pilot10_4b_v1/evaluation.json`
