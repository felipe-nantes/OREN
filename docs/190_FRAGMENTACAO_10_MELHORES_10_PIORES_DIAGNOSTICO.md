# 190 — Fragmentação na galeria de 10 melhores/10 piores: diagnóstico e resultado

## Origem

Depois de selecionar os 10 melhores e 10 piores casos LLD por integridade
hepática + continuidade vascular (fígado + veia porta/esplênica + veia cava
inferior + aorta como representante arterial — total_mr não tem rótulo de
artéria hepática), foi gerada uma galeria 3D dos 20 casos
(`tools/render_best_worst_gallery.py`). O resultado mostrava fígados
partidos em vários pedaços soltos e vasos desconectados nos piores casos —
reação do usuário: "está horroroso, quero um plano para corrigir".

## Achado central: o print superestimava a fragmentação real

A primeira versão do script de galeria montava a malha do fígado direto da
máscara venosa crua (`_mesh_from_mask` na `liver_mask_venous.nii.gz`),
pulando três mitigações que **já rodam em produção para todo caso real**
(`dtwin/stages.py:stage5_refine`):

1. **União de fases** (docs/189) — `_fonte_da_malha_do_orgao` prefere a
   máscara união (arterial+venosa+tardia) quando disponível.
2. **`_refine_mask`** — abertura + remoção de objetos < 300 voxels.
3. **`_isolar_orgao_para_visualizacao`** (guarda em
   `FRACAO_MINIMA_COMPONENTE_ORGAO = 0.90`, commit `b52c87e`) — isola o
   componente principal do fígado só quando ele já domina ≥90% da massa;
   caso contrário devolve a máscara intacta, de propósito (isolar apagaria
   anatomia real).

Os vasos não tinham mitigação equivalente (correto: árvores vasculares são
legitimamente multi-componente), mas a galeria original também pulou a
remoção de specks (`min_volume_voxels=20`) que já roda neles em produção.

## Fase 1 — medir pelo caminho real de produção

Script: `tools/build_production_liver_masks_for_selection.py`. Para os 20
casos selecionados, reproduz a sequência exata de `stage5_refine`: segmenta
arterial+tardia (nenhum overlap com os 19 casos de
`experiments/three_phase_union_v1/`, então 40 segmentações novas), constrói
a união, aplica `_refine_mask` + `_isolar_orgao_para_visualizacao`.

**Resultado (n=20, 0 erros):**

| situação | n |
|---|---|
| já era componente único | 9 |
| guarda isolou (0% → 100% corpo único) | 10 |
| guarda bloqueou (fragmentação genuína) | **1** |

19 de 20 casos viram fígado de corpo único pelo caminho real de produção.
Só `anon-lld-7ef3b5abe1ee4cd8` sobrou fragmentado (fração do maior
componente = 0,82 com união de 2 fases; ao reprocessar com as 3 fases o
resultado piorou para 0,50 — a fase tardia trouxe mais tecido, mas espalhado
em pedaços novos, não conectado ao principal). Volume bruto desse caso:
149–249 mL, bem abaixo da faixa adulta (900–2400 mL) — sintoma de
segmentação de origem ruim, não de pós-processamento insuficiente.

## Fase 2 — fígado: fechamento morfológico no caso restante (REPROVADO)

Script: `tools/test_morphological_closing_gate.py`. Gate pré-especificado:
fração do componente principal ≥0,90 **e** inflação de volume <3%.

| raio | fração | inflação | resultado |
|---|---|---|---|
| ~1–5 mm | 0,50–0,50 | 1,2%–2,1% | **reprovado em todos os raios** |

A fração fica travada perto de 0,50 independente do raio: não é uma fresta
pequena para fechar, é uma divisão real em massas de tamanho comparável.
Fechar isso exigiria um raio grande o bastante para arriscar fundir tecido
não relacionado — exatamente o que a guarda de 90% existe para evitar.
**Documentado como negativo, sem mudança em produção.**

## Fase 3 — vasos: fechamento morfológico (REPROVADO)

Script: `tools/test_vessel_closing_gate.py`, custo zero de GPU (reaproveita
as 30 máscaras de `experiments/vessel_continuity_shortlist_v1/masks/`). Gate
pré-especificado: ganho mediano de fração ≥0,05 **e** inflação mediana <5%
**e** inflação máxima por caso <15%.

| estrutura | fração base (mediana) | melhor raio testado | ganho | resultado |
|---|---|---|---|---|
| veia porta/esplênica | 0,8334 | 3 mm | +0,0010 | reprovado |
| veia cava inferior | 1,0000 | — | +0,0000 | reprovado (já sem espaço pra melhorar) |

Fechamento morfológico não move a agulha na continuidade vascular. A
fragmentação residual nos vasos é real — reflete limitação da segmentação
de origem (TotalSegmentator `total_mr`), não um artefato do renderizador.
**Documentado como negativo, sem mudança em produção.**

## Fase 4 — resultado final

`tools/render_best_worst_gallery.py` corrigido para usar
`mask_organ_clean_producao.nii.gz` (saída da Fase 1) em vez da venosa crua, e
remoção de specks nos vasos antes de mesh. Galeria re-renderizada:
`experiments/best_worst_gallery_v1/10_melhores_10_piores_producao.png`.

Comparação visual direta com o print original confirma a Fase 1: quase
todos os fígados aparecem agora como corpo único; só o caso
`anon-lld-7ef3b5abe1ee4cd8` (06 do grupo "10 piores") continua visivelmente
partido — de forma correta e esperada, porque é o único onde a guarda
bloqueou o isolamento.

## Conclusão

Nenhuma mudança de código entrou em produção nesta rodada — as três
mitigações que já existiam (`_fonte_da_malha_do_orgao`, `_refine_mask`,
`_isolar_orgao_para_visualizacao`) já resolvem 19/20 casos extremos. As duas
tentativas de correção adicional (fechamento morfológico no fígado
guarda-bloqueado e nos vasos) foram testadas com gate pré-especificado e
reprovaram — a fragmentação residual, tanto no único caso de fígado quanto
nos vasos em geral, reflete uma segmentação de origem ruim, não um defeito
de pós-processamento. Consistente com a disciplina do projeto (reparo
topológico cancelado, união de 4 fases reprovada): quando a medição diz que
não há correção segura, o certo é mostrar a máscara honesta, não escondê-la.

## Arquivos

- `tools/build_production_liver_masks_for_selection.py` — Fase 1.
- `tools/test_morphological_closing_gate.py` — Fase 2.
- `tools/test_vessel_closing_gate.py` — Fase 3.
- `tools/render_best_worst_gallery.py` — galeria corrigida (Fase 4).
- `experiments/best_worst_gallery_v1/fase1_diagnostico_producao.json` —
  diagnóstico por caso.
- `experiments/vessel_closing_gate_v1/results.json` — medição bruta da
  Fase 3.
