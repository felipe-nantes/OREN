# OpenSwissHCC v16 — scorer focal e revisão assinada

## Estado em 16 de julho de 2026

O scorer focal v16 foi implementado e validado somente com respostas simuladas.
Nenhuma chamada real ao MedGemma foi executada nesta etapa. Labels de
desenvolvimento e holdout permaneceram fechados.

Suíte completa após esta entrega: **621 testes aprovados**, sem regressões.

## Contrato de inferência

O scorer reutiliza o endpoint local `/score-volume` e o método
`first_token_restricted_softmax_v1`. Não há mudança no servidor ou segunda cópia
do modelo.

Para cada candidato:

1. revalidar manifesto, SHA-256, bytes, PNG RGB 384 × 384 e salvaguardas;
2. construir deterministicamente o mapa dos frames por sequência;
3. enviar uma única requisição, sem retry;
4. persistir as probabilidades de `POSITIVA`, `NEGATIVA` e `INCONCLUSIVA`;
5. calcular `log((P(POSITIVA)+1e-8)/(P(NEGATIVA)+1e-8))`.

A pontuação do caso é o maior log-odds entre seus candidatos. Essa regra fornece
um score contínuo para a avaliação posterior e não usa labels durante a
inferência.

O prompt informa explicitamente que o ROI veio de um localizador automático e
que isso não constitui evidência de doença. Ele exige diferenciação entre lesão
focal, vaso tubular, variante anatômica, pseudolesão perfusional, volume parcial
e artefato.

## Tempo

O orçamento de 180 segundos é aplicado ao caso inteiro. Cada nova chamada
recebe apenas o tempo restante. Se qualquer candidato falhar ou o tempo acabar,
o caso não recebe resultado final parcial.

Os tempos inicialmente produzidos pelo scorer medem somente inferência sobre
stacks pré-computados. Eles não podem ser usados isoladamente para afirmar o
tempo total do ARGOS. O piloto crítico posterior deverá somar/reexecutar:

- registro;
- localizador;
- renderização dos stacks;
- todas as chamadas focais do caso.

## Revisão humana assinada

Foi criado o comando:

```powershell
.\.venv-win\Scripts\python.exe -B tools/review_openswisshcc_candidate_volume_v16.py `
  --bundle-root casos/qualification/openswisshcc_v1/prepared/development_review_gallery_v16_candidate_volume_pilot10_v2 `
  --out casos/qualification/openswisshcc_v1/prepared/development_reviews_v16/candidate_volume_pilot10_review.json `
  --reviewer jm `
  --approve `
  --confirm-roi-contains-liver `
  --confirm-adjacent-slice-continuity `
  --confirm-dynamic-t1-alignment `
  --confirm-morphology-sequence-correspondence `
  --confirm-contrast-adequate `
  --confirm-no-visible-phi-or-overlay `
  --confirm-fallback-is-usable
```

O comando só deve ser executado depois da declaração explícita do revisor. Ele:

- exige todas as sete confirmações para aprovação;
- exige justificativa objetiva para rejeição;
- vincula a revisão ao SHA-256 e à assinatura exata da galeria;
- recusa sobrescrita;
- registra que ground truth e holdout não foram abertos;
- assina canonicamente o conteúdo da revisão.

## Arquivos

- `dtwin/benchmark/openswisshcc_candidate_volume_score.py`
- `dtwin/benchmark/openswisshcc_candidate_volume_review.py`
- `tools/freeze_openswisshcc_candidate_volume_score_v16.py`
- `tools/run_openswisshcc_candidate_volume_score_v16.py`
- `tools/review_openswisshcc_candidate_volume_v16.py`
- `tests/test_openswisshcc_candidate_volume_score.py`
- `tests/test_openswisshcc_candidate_volume_review.py`

## Pendências antes da primeira chamada real

1. obter a aprovação humana explícita da galeria v16;
2. endurecer o reuso para validar novamente hashes e probabilidades candidatos;
3. vincular cada diretório de saída a um único protocolo/bundle;
4. executar novamente a suíte completa;
5. gerar o registro assinado da revisão;
6. congelar o protocolo;
7. executar os pilotos de tempo para casos com 1, 3 e 5 candidatos.

O holdout continuará fechado. A avaliação de acurácia só ocorrerá depois que o
batch cego dos 87 casos estiver completo e o gate temporal for comprovado.
