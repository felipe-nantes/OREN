# Gate de revisão visual dos painéis OpenSwissHCC

Data do registro: 2026-07-14.

Este documento continua o diário de qualificação registrado em
`docs/24_MEDSIGLIP_E_OPEN_SWISS_QUALIFICATION.md`.

## Objetivo

Separar a aprovação humana dos caches imutáveis de alinhamento e painel. A
revisão não deve regenerar imagens nem transformar uma flag gravada durante a
renderização em evidência de inspeção posterior.

## Implementação

Foram adicionados:

- `dtwin/benchmark/openswisshcc_review.py`;
- `tools/review_openswisshcc_panels.py`;
- `tests/test_openswisshcc_review.py`.

O comando de revisão exige três confirmações explícitas:

1. ausência de PHI visível;
2. alinhamento multifásico aceitável ou, nos fallbacks declarados, qualidade da
   fase venosa única;
3. enquadramento hepático visualmente aceitável.

O artefato registra o identificador do revisor, horário UTC, conjunto exato de
casos, assinatura do candidato, nome, tamanho e SHA-256 de cada painel. Ele é
gravado atomicamente e não sobrescreve uma revisão já existente.

Antes da inferência, `verify_panel_review` recalcula os hashes e compara o
conjunto exato solicitado. Mudança nos bytes, no manifesto candidato, na
assinatura, nas confirmações ou nas salvaguardas invalida a aprovação.

## Estado atual

```text
casos de desenvolvimento: 88
painéis multifásicos prontos para revisão: 85
fallbacks venosos para falha do gate Dice: 3
total de painéis prontos para revisão: 88
painéis aprovados por humano: 0
inferências executadas nesta etapa: 0
```

A implementação da ferramenta não constitui aprovação. Os 88 painéis continuam
bloqueados até a inspeção visual real pelo usuário. O ground truth não é lido
pela ferramenta de revisão.

## Validação

A cadeia OpenSwissHCC focalizada cobre:

- aprovação separada e vinculada ao hash;
- rejeição de confirmação visual incompleta;
- invalidação após alteração dos bytes do painel;
- invalidação após adulteração do manifesto de revisão;
- rejeição de conjunto de casos divergente;
- exclusão de staging e casos incompletos;
- proibição de sobrescrita de aprovação existente.

## Uso após a inspeção humana

Somente depois de revisar todos os painéis selecionados:

```powershell
.\.venv-win\Scripts\python.exe -B -m tools.review_openswisshcc_panels `
  --panels casos/qualification/openswisshcc_v1/prepared/development_candidate_v1 `
  --out casos/qualification/openswisshcc_v1/prepared/development_reviews_v1/approved_panels.json `
  --reviewer "IDENTIFICADOR_DO_REVISOR" `
  --all-ready `
  --confirm-no-visible-phi `
  --confirm-alignment `
  --confirm-liver-framing
```

Essas flags são uma declaração humana. O comando não deve ser executado por
automação ou antes da inspeção efetiva.
