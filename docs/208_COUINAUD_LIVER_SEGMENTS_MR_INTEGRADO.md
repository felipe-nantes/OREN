# Segmentos de Couinaud I–VIII — integração `liver_segments_mr`

Data: 2026-08-10
Estado: integrado, validado em GPU e disponível no visualizador

## Causa da ausência anterior

O perfil já declarava `liver_segments_mr`, mas o estágio de segmentação propagava dois argumentos incompatíveis com essa tarefa dedicada no TotalSegmentator 2.15.0:

1. `fast=True`, embora `liver_segments_mr` exija resolução completa;
2. `roi_subset`, permitido apenas nas tarefas gerais `total` e `total_mr`.

Como anatomia interna é opcional, a falha era isolada corretamente e o fígado principal continuava funcional, porém nenhum segmento era publicado.

## Correções

- `liver_segments_mr` passa a executar com `fast: false`.
- `roi_subset` permanece somente em `total`/`total_mr`.
- O perfil exige `require_complete: true` para Couinaud.
- Os oito arquivos precisam ser não vazios e possuir a mesma geometria física do volume.
- Uma saída parcial remove todo o conjunto derivado: nunca habilita Couinaud incompleto.
- O visualizador exige explicitamente os papéis I–VIII antes de liberar o preset Segmentos.

## Validação real

Caso: `c2424a1dd2e1`
TotalSegmentator: 2.15.0
GPU: RTX 4060 Laptop 8 GB
Tempo da tarefa dedicada: 40,7 s

Volumes:

| Segmento | Volume |
|---|---:|
| I | 13,45 mL |
| II | 145,30 mL |
| III | 29,19 mL |
| IV | 111,83 mL |
| V | 201,36 mL |
| VI | 146,38 mL |
| VII | 78,92 mL |
| VIII | 187,52 mL |

Gate geométrico:

- oito máscaras presentes e não vazias;
- geometria idêntica ao volume de referência;
- sobreposição entre segmentos: 0 voxel;
- Dice da união dos segmentos contra fígado shadow: 0,92521;
- união dentro do fígado shadow: 97,01%;
- cobertura do fígado shadow pela união: 88,43%.

## Visualizador

- manifesto integrado contém 14 malhas e hashes válidos;
- padrão de abertura usa o acabamento orgânico sólido (atualizado em `docs/210_PADRAO_VISUAL_SOLIDO_E_TRANSPARENCIA_CONTROLADA.md`);
- preset Segmentos mostra somente Couinaud I–VIII e referências vasculares;
- candidato, região classificada e vesícula ficam fora desse preset para evitar competição visual;
- segmentos usam paleta reduzida e material orgânico, sem sugerir fronteiras anatômicas visíveis na RM.

Captura final:

`experiments/couinaud_diagnostic_c2424a1dd2e1_v3/viewer_couinaud_i_viii_job_c2424a1dd2e1_v3.png`

## Testes

- 124 testes relevantes aprovados;
- inclui regressão para `fast=False`, ausência de `roi_subset`, publicação atômica e bloqueio do preset com conjunto parcial.

## Próximo passo

Adicionar sincronização espacial entre a pilha de referência 2D e o modelo 3D, permitindo que a seleção de um plano axial/coronal/sagital posicione automaticamente um plano de corte correspondente no modelo.
