# Validação pareada da organização automática de fases DICOM

Data: 2026-08-02. Uso exclusivo em pesquisa.

## Pergunta

Verificar se o envio de um estudo DICOM bruto, com resolução automática das
fases arterial, venosa e tardia, altera os painéis, a predição ou o tempo em
relação ao mesmo mapeamento de fases previamente aprovado por revisão humana.

## Protocolo

- Coorte pública TCGA-LIHC positiva: 12 casos solicitados.
- Um caso foi excluído tecnicamente antes da inferência por não possuir três
  fases pós-contraste identificáveis com segurança.
- Onze casos foram incluídos.
- A galeria label-blind foi aprovada antes da inferência.
- O fígado foi novamente segmentado em resolução completa (`fast=False`).
- Cada caso gerou painéis pelo caminho automático e pelo mapeamento explícito.
- A inferência foi reutilizada somente depois da igualdade SHA-256 de todos os
  painéis dos dois caminhos.
- Labels públicos foram abertos somente após a persistência das predições.
- Máscaras de lesão não foram lidas nem usadas.

Assinatura da galeria aprovada:

`2133103ae58997edad063769c818893e5d2b77a6a59384c30c7850d4d1e2f608`

## Resultado

| Medida | Resultado |
|---|---:|
| Casos concluídos | 11/11 (100%) |
| Painéis byte-idênticos | 11/11 (100%) |
| Casos abaixo de 180 s | 11/11 (100%) |
| Tempo mínimo | 40,12 s |
| Tempo mediano | 46,61 s |
| Tempo médio | 46,66 s |
| Tempo máximo | 55,99 s |
| Verdadeiros positivos | 5 |
| Falsos negativos | 6 |
| Sensibilidade | 45,45% |
| IC 95% de Wilson | 21,27%–71,99% |
| Especificidade | Não estimável neste braço positivo |

## Interpretação

A organização automática das fases não introduziu diferença de imagem: todos
os conjuntos de painéis foram idênticos aos produzidos pelo mapeamento aprovado.
Portanto, nesta coorte, a queda de sensibilidade não foi causada pelo envio de
DICOM bruto nem pelo resolvedor de fases. O gargalo observado está na
generalização do classificador visual congelado para os casos TCGA-LIHC.

O requisito operacional de até três minutos foi satisfeito nos 11 casos, mas o
requisito de sensibilidade mínima de 75% não foi satisfeito. Não é possível
afirmar cumprimento simultâneo de sensibilidade e especificidade sem uma coorte
negativa multifásica rotulada.

## Artefatos

- Galeria: `casos/qualification/tcga_positive_stress/raw_phase_review_v1/`
- Relatório: `casos/qualification/tcga_positive_stress/raw_phase_equivalence_v2/benchmark_report.json`
- Aprovação: `casos/qualification/tcga_positive_stress/raw_phase_equivalence_v2/review_approval.json`

