# OpenSwissHCC v9 — preflight de revisão e inferência

Data: 2026-07-14

## Gate assinado

Foi implementado um manifesto de aprovação humana específico para a coorte multissequência v9. A assinatura vincula:

- assinatura da coorte;
- SHA-256 do manifesto de cada caso;
- SHA-256 canônico do conjunto de painéis;
- índices dos planos TRACE;
- tiles fora do FOV;
- confirmações explícitas do revisor;
- isolamento de ground truth, máscara de lesão e inferência.

Qualquer alteração posterior em painel, bytes, manifesto ou coorte invalida a aprovação.

O comando somente deve ser executado depois da revisão visual:

```powershell
python -m tools.review_openswisshcc_multisequence `
  --panels casos/qualification/openswisshcc_v1/prepared/development_multisequence_cohort_v9 `
  --out casos/qualification/openswisshcc_v1/prepared/development_reviews_v9/multisequence_review.json `
  --reviewer "IDENTIFICADOR_DO_REVISOR" `
  --confirm-no-visible-phi `
  --confirm-all-panels `
  --confirm-cross-sequence-anatomy `
  --confirm-liver-framing-contrast `
  --confirm-out-of-fov-tiles
```

## Preflight real

- casos revalidados: 88;
- painéis revalidados: 2.149;
- tiles fora do FOV: 12, todos T2 BLADE;
- assinatura da coorte: `64782bda03f1d393df51a6d61032ce4b61d18a814393634273027537b4bc6589`;
- suíte completa: 460 testes aprovados.

## Projeção temporal, ainda não comprovada

O experimento v7 processou 561 painéis com média de 15,63 segundos por caso, aproximadamente 2,45 segundos por painel. Aplicando apenas como projeção:

- média v9 de 24,42 painéis: aproximadamente 60 segundos por caso;
- pior caso v9 com 37 painéis: aproximadamente 91 segundos.

Essa conta não prova o requisito de 180 segundos porque o conteúdo v9 possui quatro modalidades. O piloto deve medir tempo de parede por caso, incluindo validação, leitura de imagens, inferência e persistência. Timeout ou duração acima de 180 segundos reprova o caso e a configuração.

## Próximo passo

Após a assinatura humana, congelar prompt, modelo, hashes, agregação e limite de 180 segundos. Executar primeiro um piloto cego pequeno e balanceado. Somente abrir labels depois da persistência das respostas para calcular sensibilidade e especificidade.
