# OpenSwissHCC v9 — exclusão técnica cega

Data: 2026-07-15

## Caso sinalizado

- índice na galeria: 72;
- case_id: `anon-openswiss-cb2c5c63fc28b8ee`;
- painéis: 19;
- cobertura TRACE: 100%;
- planos ausentes ou duplicados: zero;
- tiles fora do FOV: zero;
- ground truth consultado: não.

A revisão humana observou qualidade muito prejudicada, embora o fígado ainda seja visualizável. A inspeção técnica confirmou degradação de sinal em múltiplas sequências, sem evidência de falha de cobertura ou do gerador.

## Regra preparada

Foi implementado um manifesto assinado de qualidade que aceita somente:

- `approved_primary`;
- `technical_quality_exclusion`;
- reason codes técnicos predefinidos.

Campos clínicos, diagnóstico, label e texto livre não são aceitos. Qualquer modificação posterior em painel ou manifesto invalida a assinatura.

Para o caso 72, o reason code recomendado é:

`severe_multisequence_quality_degradation`

## Uso metodológico recomendado

Após confirmação explícita do revisor:

1. manter 87 casos na análise primária;
2. preservar o caso 72 numa análise secundária de estresse;
3. registrar que a exclusão ocorreu antes da inferência e sem acesso ao label;
4. reportar denominadores e distribuição de classes efetivamente observados somente após a inferência;
5. não usar a exclusão para ajustar limiar ou escolher resultado.

## Estado

Nenhuma exclusão foi aplicada até o momento. O caso permanece na coorte original de 88 casos.

Suíte completa: 470 testes aprovados.
