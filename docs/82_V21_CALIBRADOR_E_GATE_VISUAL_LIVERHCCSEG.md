# V21 — calibrador externo e gate visual LiverHccSeg

## Estado da etapa

Esta etapa transportou a regra v11 para uma coorte externa sem recalibrar pesos
ou limiar e sem abrir o holdout OpenSwissHCC.

O desenvolvimento v11 continua formalmente não qualificado: 74,36% de
sensibilidade LOOCV e 75,00% de especificidade. O resultado externo não pode
alterar retrospectivamente esse fato. Ele serve para medir generalização e
decidir, com evidência adicional, se o protocolo congelado merece a avaliação
única no holdout.

## Calibrador externo congelado

Artefato local:

```text
casos/qualification/openswisshcc_v1/prepared/
  public_independent_freezes_v21/v11_external_calibrator.json
```

Contrato:

```text
transformação: ECDF midrank dos 87 casos de desenvolvimento
pesos:
  MedGemma v4 uncertainty margin: 0,40
  MedSigLIP v5 inverse sagittal: 0,40
  localizador v10 log volume: 0,20
limiar: 0,5241379310344827
regra: POSITIVE se score >= limiar
assinatura: cdc1fc1f30765ae7dde9eceaf02e6254cdbbe41830d9c20cf156128b04450181
```

O freeze leu somente o bundle cego v11, o protocolo assinado e o
`evaluation.json` já existente. `development_labels.jsonl` não foi reaberto.

## Painéis reais

Os 14 casos LiverHccSeg preparados foram renderizados com:

- pré-contraste disponível na entrada, mas representação v11 formada por
  arterial/portal/tardia em RGB;
- R=arterial, G=portal/venosa, B=tardia;
- nove cortes axiais uniformes, uma vista coronal e uma sagital;
- crop e janela determinados apenas pela máscara hepática;
- nenhum arquivo, argumento ou overlay de máscara tumoral;
- PNG sem metadados e hashes individuais;
- `eligible_for_inference=false` até aprovação humana.

Artefatos:

```text
data/qualification/liverhccseg_v21_uniform9_panels/
data/qualification/liverhccseg_v21_uniform9_gallery/index.html
```

Assinaturas:

```text
coorte de painéis:
c60473f82cb5aecae88ee1e1b7916f9ab7697aca3235b7806e77d38da64c6b5d

galeria:
3bc6d6021f657dd247227cceaaeb6c223dbfe9f035b1e552288855a47dcc22e6

index.html SHA-256:
3bc1caecdaf2b3252ad46b13b82c10c693d45d74ff3e652d05a67c70084e847a
```

## O que revisar na galeria

Não avaliar diagnóstico ou procurar confirmar HCC. A revisão é exclusivamente
técnica:

1. o fígado está visível nos cortes centrais;
2. a orientação axial/coronal/sagital é plausível;
3. o crop não remove parte importante do fígado;
4. a fusão RGB é interpretável e não apresenta desalinhamento destrutivo;
5. o contorno branco acompanha o fígado sem esconder o parênquima;
6. não há texto ou PHI visível;
7. não há marcação explícita de tumor/lesão.

Uma lesão visualmente evidente não reprova o painel. O objetivo deste gate é
qualidade da representação, não conferência do label.

## Próximo passo após aprovação

Somente após aprovação explícita da galeria:

1. assinar a revisão e tornar exatamente estes hashes elegíveis;
2. executar, sem labels, os três sinais congelados;
3. aplicar o calibrador externo sem recalibrar;
4. congelar as 14 predições e os tempos;
5. abrir apenas o ground truth público LiverHccSeg para calcular sensibilidade
   externa e IC 95%;
6. manter o holdout OpenSwissHCC fechado.

### Gate assinado implementado

O registro da revisão usa:

```text
dtwin/benchmark/liverhccseg_v21_review.py
tools/review_liverhccseg_v21_panels.py
```

Ele revalida os hashes da coorte, galeria, `index.html` e dos 14 PNGs antes de
assinar. Aprovação parcial não é aceita. Alterar qualquer painel após a revisão
invalida o artefato. Um teste real sem `--approve` abortou com código 1 e não
criou arquivo de revisão, comprovando o comportamento fail-closed.

Comando a ser executado somente depois da declaração humana:

```powershell
.\.venv-win\Scripts\python.exe tools/review_liverhccseg_v21_panels.py `
  --panels data/qualification/liverhccseg_v21_uniform9_panels `
  --gallery data/qualification/liverhccseg_v21_uniform9_gallery `
  --review data/qualification/liverhccseg_v21_uniform9_review.json `
  --reviewer REVISOR `
  --approve
```

## Executor cego em estágios

O executor foi separado para respeitar a GPU CUDA de 8 GB:

```text
1. localizer-manifest — cria entrada neutra após o gate humano
2. localizer          — TotalSegmentator liver_lesions_mr
3. medsiglip          — score sagital v5, sem decisão
4. medgemma           — choice score v4 pelo gateway 4B
5. assemble           — monta os três sinais crus e soma os tempos
6. calibrator score   — aplica a ECDF/limiar congelados
```

TotalSegmentator, MedSigLIP e MedGemma não ficam residentes simultaneamente. O
assembler exige exatamente:

```text
P(INCONCLUSIVA) - P(NEGATIVA)
-P_MedSigLIP_positiva_na_vista_sagital
log1p(volume_candidato_mm3)
```

Cada componente persiste `final_decision=null`, `ground_truth_read=false` e o
hash da revisão. Somente o calibrador congelado emite a predição binária. O
tempo operacional por caso é a soma dos três componentes e precisa ser menor ou
igual a 180 segundos.

Arquivos:

```text
dtwin/benchmark/liverhccseg_v21_signals.py
tools/run_liverhccseg_v21_signals.py
tests/test_liverhccseg_v21_signals.py
```

Uma execução real de `localizer-manifest` sem o arquivo de aprovação terminou
com código 1 e não criou saída. Assim, o bloqueio acontece antes de carregar ou
chamar qualquer modelo.

## Avaliação protegida do braço positivo

O avaliador futuro foi implementado, mas não executado:

```text
dtwin/benchmark/public_independent_v21_evaluation.py
tools/evaluate_liverhccseg_v21_positive.py
tests/test_public_independent_v21_evaluation.py
```

Ele exige `--allow-protected-public-ground-truth` somente depois que as 14
predições estiverem completas e congeladas. O relatório contém TP, FN,
sensibilidade, IC95% Wilson e tempos médio/mediano/P95/máximo. Como o braço
LiverHccSeg contém apenas positivos, o avaliador define explicitamente:

```text
specificity: null
roc_auc: null
simultaneous_75_75_gate_evaluated: false
qualified: false
```

Assim, um resultado positivo favorável não será apresentado indevidamente como
prova simultânea de sensibilidade e especificidade. A avaliação final 75%/75%
continua reservada a uma coorte com as duas classes.

Durante o teste integrado foi corrigido um problema preventivamente: o JSONL de
sinais é serializado com chaves canonicamente ordenadas, enquanto o primeiro
validador exigia a ordem de inserção original. O contrato agora exige igualdade
exata do conjunto dos três sinais, independentemente da ordem textual, e ainda
rejeita campos extras ou ausentes.

## Validação de software

```text
testes focados de calibrador/painéis/preparação: 15 passed
suíte completa após a execução cega: 789 passed, 396 warnings conhecidos
```

Os avisos são depreciações já conhecidas de SimpleITK, scikit-image, VTK e
Starlette; não houve falha funcional.
