# Fase 1 — Presets de composição do visualizador 3D

Data: 2026-08-10
Estado: implementada e validada em caso multifásico real já processado

## Objetivo

Permitir que a revisão 3D use composições visuais reproduzíveis, sem alterar a segmentação, as máscaras, a classificação ou a inferência. Cada preset atua exclusivamente sobre visibilidade, opacidade e câmera das malhas já autorizadas pelo `viewer_manifest.json`.

## Presets implementados

- **Superfície:** mostra somente a forma externa do fígado.
- **Anatomia interna:** torna o fígado translúcido e destaca veia porta/esplênica, veia cava inferior e vesícula biliar.
- **Triagem:** prioriza fígado translúcido, região candidata e região usada pela classificação, mantendo referências anatômicas.
- **Segmentos:** preparado para os segmentos de Couinaud I–VIII e referências vasculares. O botão fica desabilitado quando o exame não contém malhas segmentares; nenhuma estrutura é simulada.

Qualquer mudança manual em visibilidade, isolamento ou opacidade remove o preset ativo e registra a cena como **Personalizada**. Um novo clique em um preset restaura sua composição determinística.

## Rastreabilidade

O estado enviado na revisão humana passou a incluir:

```json
{
  "active_preset": "custom | surface | anatomy | triage | segments"
}
```

O backend valida essa enumeração e rejeita valores arbitrários. O comportamento anterior permanece compatível por meio do padrão `custom`.

## Validação realizada

Caso real: `296732bff897` (`anon-2fa8a821b90e`), com fígado, região candidata, região classificada, vesícula, veia porta/esplênica e veia cava inferior.

- sintaxe JavaScript validada;
- 80 testes de webapp e contrato dos presets aprovados;
- 21 testes de finalização, região candidata e CLI aprovados;
- total desta rodada: **101 testes aprovados**;
- renderização verificada no navegador local sem alertas;
- preset de Segmentos corretamente indisponível neste caso, pois o manifesto não contém máscaras de Couinaud;
- alteração manual corretamente muda o estado para `custom`;
- nenhum preset realiza chamada de rede ou nova inferência.

## Capturas técnicas

- `experiments/segmentation_shadow_smoke_liverhccseg_v2/viewer_preset_surface_job_296732bff897.png`
- `experiments/segmentation_shadow_smoke_liverhccseg_v2/viewer_preset_anatomy_job_296732bff897.png`
- `experiments/segmentation_shadow_smoke_liverhccseg_v2/viewer_preset_triage_job_296732bff897.png`

## Limite atual e próximo passo

O suporte de interface e manifesto para Couinaud já existe, mas este exame não produziu as máscaras de `liver_segments_mr`. O próximo passo isolado é diagnosticar a execução dessa tarefa e validar suas oito máscaras antes de habilitar o preset Segmentos em um caso real. Esse diagnóstico não deve interferir no caminho aprimorado já aprovado para fígado e grandes vasos.
