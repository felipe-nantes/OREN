# OpenSwissHCC holdout — gate humano e executor cego v21

## Estado

As imagens dos sujeitos públicos 045–088 foram preparadas em modo label-blind e os 44 painéis técnicos foram gerados. Esta etapa acrescenta a proteção que separa a revisão visual da inferência.

Nenhum label, diagnóstico ou máscara pública de lesão foi aberto. O holdout permanece fechado.

## Gate humano assinado

O módulo `dtwin/benchmark/openswisshcc_holdout_review.py` valida, antes de aceitar uma aprovação:

- exatamente 44 casos anônimos e únicos;
- 43 painéis multifásicos RGB;
- um único fallback venoso em escala de cinza, congelado no item 28;
- assinatura do manifesto da coorte e da galeria;
- hash do HTML revisado;
- hash da imagem de origem e da cópia exibida na galeria;
- manifesto individual de cada candidato;
- `eligible_for_inference=false` antes da aprovação;
- ausência declarada de PHI, label patológico e máscara de lesão.

A aprovação é total, técnica e explícita. Aprovação parcial não é aceita. O artefato é publicado atomicamente e não pode ser sobrescrito.

Comando a ser usado somente depois da aprovação humana explícita:

```powershell
.\.venv-win\Scripts\python.exe tools\review_openswisshcc_holdout_v21.py `
  --panels casos\qualification\openswisshcc_v1\prepared\holdout_uniform9_panels_v21 `
  --gallery casos\qualification\openswisshcc_v1\prepared\holdout_review_gallery_v21 `
  --review casos\qualification\openswisshcc_v1\prepared\holdout_uniform9_review_v21.json `
  --reviewer jm `
  --approve `
  --note "Galeria holdout v21 aprovada para inferência cega."
```

Até a aprovação, esse arquivo não deve existir. O preflight real foi executado sem ele e abortou corretamente antes de carregar qualquer modelo.

## Executor cego em estágios

O módulo `dtwin/benchmark/openswisshcc_holdout_signals.py` e a CLI `tools/run_openswisshcc_holdout_v21.py` implementam os estágios abaixo:

1. `preflight`: revalida revisão, imagens, auditoria, configs e calibrador, sem carregar modelos;
2. `localizer-manifest`: libera somente a fase venosa e a máscara automática do fígado;
3. `localizer`: executa `liver_lesions_mr`, sem máscara pública de lesão;
4. `medsiglip`: calcula apenas o sinal contínuo já congelado, sem decisão autônoma;
5. `medgemma`: usa o leitor multifásico em 43 casos e o fallback venoso no caso pré-declarado;
6. `assemble`: reúne exatamente os três sinais v11;
7. `score`: aplica o calibrador externo já congelado;
8. `freeze`: assina hashes, predições, regra, limiar e gate temporal antes de qualquer autorização para abrir labels.

## Avaliação same-domain preparada, mas não executada

Foi implementado também o estágio tardio em
`dtwin/benchmark/openswisshcc_holdout_evaluation.py`, acessível por
`tools/evaluate_openswisshcc_holdout_v21.py`.

Ele permanece inativo até que existam, nesta ordem:

1. aprovação humana assinada dos 44 painéis;
2. três sinais completos para os 44 casos;
3. 44 predições geradas pelo calibrador congelado;
4. freeze final assinado das predições e do protocolo;
5. autorização humana separada citando a assinatura exata desse freeze.

Somente então a ferramenta poderá ler o `participants.tsv` oficial e construir
um bundle protegido. Após a abertura tardia autorizada, o arquivo público oficial
demonstrou que a distribuição do holdout é de 24 casos positivos e 20 negativos.
Nenhuma máscara de lesão é necessária ou aceita nessa avaliação.

O relatório same-domain calculará:

- matriz de confusão TP/TN/FP/FN;
- sensibilidade, especificidade e acurácia;
- intervalos de confiança de 95% de Wilson;
- ROC-AUC do score contínuo congelado;
- média, mediana, p95 e máximo do tempo por caso;
- gate conjunto `sensibilidade >= 75%`, `especificidade >= 75%` e
  `tempo máximo <= 180 s`.

Os labels não foram abertos durante a implementação ou os testes. Os testes usam
apenas arquivos sintéticos temporários.

Os componentes de GPU continuam separados. TotalSegmentator, MedSigLIP e MedGemma não precisam ficar residentes simultaneamente na GPU de 8 GB.

## Sinais congelados

O executor preserva exatamente:

```text
MedGemma: P(INCONCLUSIVA) - P(NEGATIVA)
MedSigLIP: -P(positivo no tile sagital)
Localizador: log1p(volume candidato em mm³)
```

Calibrador permitido:

```text
SHA-256: 1760664acc28e48180ff3d68ea5de6c591aa185500bc2bb53313695ba8589971
assinatura: cdc1fc1f30765ae7dde9eceaf02e6254cdbbe41830d9c20cf156128b04450181
```

Qualquer outro calibrador é rejeitado.

## Proteções metodológicas

- Nenhum modelo é criado antes da revisão assinada passar.
- Falha em qualquer caso invalida o estágio inteiro.
- Diretórios parciais não são publicados.
- Resultados existentes não são sobrescritos.
- Os hashes dos 44 painéis são revalidados em cada preflight.
- O protocolo final só pode ser congelado com 44 predições completas.
- Labels e máscaras de lesão permanecem fechados durante todos os estágios.
- A futura abertura de labels exigirá autorização separada após o freeze.

## Validação realizada

Foram adicionados testes dedicados para o gate, executor, freeze e avaliador. Eles cobrem:

- exigência de aprovação explícita;
- assinatura e verificação completa da revisão;
- adulteração de painel, HTML e assinatura;
- fallback fora do item 28;
- preflight label-blind;
- ausência de modelo sem aprovação;
- manifesto venoso mínimo do localizador;
- roteamento de 43 painéis multifásicos e um fallback;
- falha intermediária sem publicação parcial;
- freeze final com labels fechados;
- rejeição de lote de scores adulterado.
- bloqueio dos labels sem autorização explícita;
- vínculo dos labels à assinatura do freeze;
- distribuição protegida 19/25;
- métricas same-domain e ROC-AUC;
- falha do gate temporal acima de 180 segundos;
- rejeição de labels adulterados e de assinatura divergente.

Resultado focal:

```text
20 testes focais aprovados
863 testes totais aprovados, 0 falhas
```

O preflight contra os artefatos reais também foi executado antes da aprovação e produziu o bloqueio esperado:

```text
[ABORTADO] Artefato holdout ausente: ...holdout_uniform9_review_v21.json
```

Isso comprova que a inferência ainda não foi liberada acidentalmente.

## Próximo gate humano

O revisor deve avaliar apenas qualidade técnica: fígado reconhecível, crop, orientações, registro RGB, contorno, ausência de PHI e ausência de marcação de lesão. O item 28 deve permanecer em escala de cinza por ser o fallback técnico pré-declarado.

Somente após a frase explícita de aprovação o artefato de revisão poderá ser criado e a inferência cega iniciada.

## Runbook operacional após a aprovação da galeria

Os comandos abaixo são uma sequência. Um estágio só deve começar depois que o
anterior terminar e seus hashes forem validados. Os três modelos permanecem em
processos separados.

Variáveis de conveniência no PowerShell:

```powershell
$P = "casos/qualification/openswisshcc_v1/prepared"
$PANELS = "$P/holdout_uniform9_panels_v21"
$GALLERY = "$P/holdout_review_gallery_v21"
$REVIEW = "$P/holdout_uniform9_review_v21.json"
$PREPARED = "$P/holdout_blind_v1"
$AUDIT = "casos/qualification/openswisshcc_v1/audits/holdout_blind_v1_audit.json"
$CAL = "$P/public_independent_freezes_v21/v11_external_calibrator.json"
$LOCALIZER_INPUTS = "$P/holdout_v21_localizer_inputs.jsonl"
$LOCALIZER = "$P/holdout_v21_localizer"
$MEDSIGLIP = "$P/holdout_v21_medsiglip"
$MEDGEMMA = "$P/holdout_v21_medgemma"
$RAW = "$P/holdout_v21_raw_signals"
$SCORES = "$P/holdout_v21_scores"
$FREEZE = "$P/holdout_v21_prediction_freeze.json"

$COMMON = @(
  "--panels", $PANELS,
  "--gallery", $GALLERY,
  "--review", $REVIEW,
  "--prepared", $PREPARED,
  "--prepared-audit", $AUDIT,
  "--multiphase-config", "configs/medgemma_local_4b_multiphase_uniform9_choice_v21.yaml",
  "--fallback-config", "configs/medgemma_local_4b_venous_uniform9_choice_v21.yaml",
  "--medsiglip-config", "configs/medsiglip_liver_zero_shot.yaml",
  "--calibrator", $CAL
)
```

Após criar a revisão assinada, executar o preflight sem modelos:

```powershell
& .\.venv-win\Scripts\python.exe tools/run_openswisshcc_holdout_v21.py preflight @COMMON
```

Criar a entrada mínima e rodar o localizador:

```powershell
& .\.venv-win\Scripts\python.exe tools/run_openswisshcc_holdout_v21.py localizer-manifest @COMMON --out $LOCALIZER_INPUTS
& .\.venv-win\Scripts\python.exe tools/run_openswisshcc_holdout_v21.py localizer @COMMON --manifest $LOCALIZER_INPUTS --out $LOCALIZER
```

Após o processo do localizador encerrar e liberar a GPU, rodar MedSigLIP:

```powershell
& .\.venv-win\Scripts\python.exe tools/run_openswisshcc_holdout_v21.py medsiglip @COMMON --out $MEDSIGLIP --device cuda
```

Após o processo MedSigLIP encerrar, iniciar o servidor MedGemma 4B já validado e
rodar o leitor cego:

```powershell
& .\.venv-win\Scripts\python.exe tools/run_openswisshcc_holdout_v21.py medgemma @COMMON --out $MEDGEMMA
```

Montar os sinais, aplicar o calibrador e congelar o protocolo:

```powershell
& .\.venv-win\Scripts\python.exe tools/run_openswisshcc_holdout_v21.py assemble @COMMON --medgemma $MEDGEMMA --medsiglip $MEDSIGLIP --localizer $LOCALIZER --out $RAW
& .\.venv-win\Scripts\python.exe tools/run_openswisshcc_holdout_v21.py score @COMMON --signals "$RAW/raw_signals.jsonl" --out $SCORES
& .\.venv-win\Scripts\python.exe tools/run_openswisshcc_holdout_v21.py freeze @COMMON --raw-signals $RAW --scores $SCORES --out $FREEZE
```

Nesse ponto deve-se registrar a `protocol_signature` exibida pelo último comando.
Os labels continuam fechados. A execução deve parar e solicitar uma nova
autorização humana que cite exatamente essa assinatura.

## Runbook após a futura autorização dos labels

Estes comandos não estão autorizados nesta etapa e não devem ser executados
antes do freeze e da autorização separada:

```powershell
$SIG = "ASSINATURA_EXATA_DO_FREEZE"
$LABELS = "$P/holdout_v21_protected_labels"
$EVAL = "casos/qualification/openswisshcc_v1/results/holdout_v21_evaluation"

& .\.venv-win\Scripts\python.exe tools/evaluate_openswisshcc_holdout_v21.py materialize-labels @COMMON `
  --raw-signals $RAW --scores $SCORES --freeze $FREEZE `
  --authorized-protocol-signature $SIG `
  --participants "casos/qualification/openswisshcc_v1/source_metadata/participants.tsv" `
  --protected-provenance "$PREPARED/protected_provenance/source_map.jsonl" `
  --out $LABELS --allow-protected-holdout-labels

& .\.venv-win\Scripts\python.exe tools/evaluate_openswisshcc_holdout_v21.py evaluate @COMMON `
  --raw-signals $RAW --scores $SCORES --freeze $FREEZE `
  --authorized-protocol-signature $SIG `
  --protected-label-bundle $LABELS --out $EVAL `
  --allow-protected-holdout-labels
```

O argumento de autorização é deliberadamente obrigatório nas duas operações.
Sem ele, a ferramenta aborta antes de ler `participants.tsv` ou o bundle de labels.

## Registro da execução cega real (19–20 de julho de 2026)

### Revisão humana e liberação

O revisor `jm` aprovou os 44 painéis do holdout v21. O artefato de revisão
foi publicado com a assinatura:

```text
c2f57e8ea1cb17f152f727a9460986653e5a98e3f3fee1c27ea8a9bcbf4e2259
```

O conjunto aprovado contém 43 painéis multifásicos RGB e o fallback venoso
em escala de cinza previamente declarado no item 28. A aprovação não abriu
labels nem máscaras públicas de lesão.

### Execução dos três sinais

O localizador `liver_lesions_mr` terminou os 44 casos com runtime isolado do
TotalSegmentator. Foram observados candidatos em 42 casos e ausência de
candidato em dois. Esses valores são sinais cegos, não diagnósticos. O maior
tempo foi de 61,4465 segundos por caso.

O MedSigLIP terminou 44/44 casos, sem decisão autônoma, com:

```text
scores_sha256: 87f58779c2f541556e097cd81ad3869e0a111cf50da4403fd267dad0dff142fb
tempo máximo por caso: 9,214557 s
tempo total: 38,185557 s
```

O MedGemma foi confirmado no endpoint local como
`google/medgemma-1.5-4b-it`, quantizado em NF4 e executado em CUDA. O lote
terminou 44/44 chamadas HTTP, sendo 43 multifásicas e uma fallback venosa:

```text
scores_sha256: 17ca69258a7893f4f5da2088af659bfea65df8a1063a357e1ba4760460a2c757
tempo máximo por caso: 7,7581932 s
tempo médio por caso: 6,3736406 s
tempo total: 280,4722224 s
```

Após o lote, o servidor MedGemma foi encerrado e a GPU liberada.

### Incidentes operacionais e comportamento fail-closed

- A primeira execução do localizador foi interrompida externamente. O staging
  incompleto não foi publicado nem reutilizado.
- O arquivo global do TotalSegmentator estava corrompido. Foi criado um runtime
  isolado dentro do workspace, usando os pesos instalados somente para leitura;
  o arquivo global não foi alterado.
- A primeira tentativa do launcher MedSigLIP criou apenas staging vazio. A
  ausência de processo ativo foi confirmada antes da repetição direta.
- A primeira chamada do estágio `score` apontou por engano para
  `signals.jsonl`; a ferramenta abortou sem publicar scores. A chamada foi
  repetida com o arquivo autoritativo `raw_signals.jsonl`.

Nenhum desses incidentes gerou resultado parcial elegível ou alterou o
protocolo congelado.

### Fusão, tempo e freeze final

Os três sinais foram reunidos para os mesmos 44 IDs:

```text
raw_signals_sha256: 98876cf5491b72928ea7134881683f8e41a76b57b1ee1c30cfd752e430554365
maior soma temporal dos componentes: 78,4192502 s
gate temporal: aprovado (limite de 180 s)
```

O calibrador externo preservado foi aplicado sem labels:

```text
calibrator_sha256: 1760664acc28e48180ff3d68ea5de6c591aa185500bc2bb53313695ba8589971
calibrator_signature: cdc1fc1f30765ae7dde9eceaf02e6254cdbbe41830d9c20cf156128b04450181
scores_sha256: a6cf135f6c2942ac13a1128a1e0e692970dd58f7f041071d3c5accb0262ba524
predições cegas: 33 positivas e 11 negativas
```

Essa distribuição não é uma métrica. Sensibilidade, especificidade e
acurácia continuam desconhecidas enquanto os labels estiverem fechados.

O protocolo e as predições foram congelados com a assinatura final:

```text
7911331092e23fb6c9ea91b8b622a74a9cdfaaa34b52909ad25060ecf1b1b782
```

O freeze declara explicitamente:

```text
labels_read: false
lesion_masks_read: 0
holdout_ground_truth_opened: false
metrics_calculated: false
status: predictions_and_final_protocol_frozen_labels_closed
```

### Validação posterior à execução

Em 20 de julho de 2026 foram executados:

```text
38 testes focais do holdout: aprovados
867 testes totais do ARGOS: aprovados
falhas: 0
```

### Gate atual

A execução está parada no limite metodológico correto. O próximo passo
somente pode ocorrer após autorização humana separada que cite exatamente a
assinatura `7911331092e23fb6c9ea91b8b622a74a9cdfaaa34b52909ad25060ecf1b1b782`.
Essa autorização libera apenas os labels públicos dos 44 casos para avaliação;
as máscaras de lesão devem permanecer fechadas.

## Atualização posterior ao gate

A autorização vinculada à assinatura final foi recebida. Os labels públicos
foram abertos somente depois do freeze; as máscaras de lesão permaneceram
fechadas. A avaliação final e a decisão metodológica estão registradas em
`docs/91_OPENSWISSHCC_HOLDOUT_V21_RESULTADO.md`.
