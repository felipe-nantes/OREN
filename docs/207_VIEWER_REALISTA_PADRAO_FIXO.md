# Visualizador 3D — composição realista como padrão fixo

> Evolução posterior: o identificador selecionável `realistic` foi removido da interface e seu acabamento tornou-se o padrão visual permanente. Consulte `docs/210_PADRAO_VISUAL_SOLIDO_E_TRANSPARENCIA_CONTROLADA.md`.

Data: 2026-08-10
Estado: concluído

## Decisão

O preset `realistic` tornou-se a composição inicial oficial do visualizador 3D. Todo modelo com uma malha hepática válida passa a abrir automaticamente com:

- tecido hepático vermelho-acastanhado;
- veia porta/esplênica em tom vascular azul-esverdeado;
- veia cava inferior em azul profundo;
- vesícula em verde-oliva;
- candidato automático em ocre, quando presente;
- região classificada disponível sob demanda.

Os demais presets permanecem disponíveis para auditoria e comparação.

## Contrato

Novos `viewer_manifest.json` registram:

```json
{
  "viewer_features": {
    "default_visual_preset": "realistic"
  }
}
```

Manifestos antigos também recebem o novo padrão pelo fallback interno autorizado do visualizador. Se não existir malha hepática, o sistema mantém a composição original e registra `custom`, sem fabricar estrutura.

## Validação

- abertura direta sem clique validada no caso real `c2424a1dd2e1`;
- botão ativo automaticamente: `Tecido realista`;
- 102 testes aprovados;
- estado inicial persistido na revisão humana como `active_preset=realistic`;
- nenhuma alteração em segmentação, classificação ou inferência;
- captura: `experiments/segmentation_shadow_smoke_liverhccseg_v2/viewer_realistic_default_job_c2424a1dd2e1.png`.

## Próxima fase

Diagnosticar e validar a geração real das máscaras `liver_segments_mr` para habilitar os segmentos de Couinaud I–VIII sem interferir no fluxo shadow já aprovado.
