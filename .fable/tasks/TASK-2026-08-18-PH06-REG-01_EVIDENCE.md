# EVIDENCE PACKAGE — TASK-2026-08-18-PH06-REG-01

```yaml
TASK_ID: TASK-2026-08-18-PH06-REG-01
DATE: 2026-08-18 (America/Sao_Paulo)
BASE_COMMIT: main em 637d9e1
TASK_DESCRIPTION: >
  PHASE_06 wave 1 — integridade do ledger congelado da Etapa C e
  reconciliacao 451/16, sem abrir conteudo de paciente (HG-11).
ROUTE: [CROSS_VALIDATION, METRICS_STATISTICS, AUDIT_PROVENANCE]
MODULES: [ML_CLASSIFIERS_SPLITS, BENCHMARK_METRICS_REPORTING, ARTIFACT_PROVENANCE]
FILES_ANALYZED:
  - configs/training/hybrid_v1_protocol.lock.json (assinatura verificada)
  - configs/training/hybrid_v1_protocol.yaml (hash verificado)
  - configs/training/hybrid_v1_nested_splits.json (hash + validade + contagens)
  - casos/qualification/hybrid_v1/medsiglip_multiclass_oof_evaluation_v1/evaluation.json (APENAS agregados numericos extraidos; nenhuma linha por caso, nenhum label)
FILES_CHANGED: []  # verificacao pura; nenhum artefato tocado
RISK_LEVEL: LOW (leitura)
PRIVACY: HG-11 respeitado — chaves de nivel-caso explicitamente omitidas na extracao
SCIENTIFIC_CONTRACTS_INVOLVED: [ARGOS-SCI-002, SCI-003, SCI-004, SCI-005, SCI-013 — verificados no artefato real, nenhum alterado]
BASELINE: suite 1706 passed
RESULTADOS:
  ledger_congelado:
    - "protocol_signature (sha256 canonico): OK"
    - "config_sha256 vs hybrid_v1_protocol.yaml: OK"
    - "splits_sha256 vs hybrid_v1_nested_splits.json: OK"
    - "validate_nested_splits: OK"
    - "universo dos splits = 467 = case_count = aggregate do lock: OK"
    - "labels agregados 220 POSITIVE / 247 NEGATIVE: OK"
    - "coortes 335 lld_mmri / 88 dev / 44 holdout: OK"
    - "outer/inner/seed = 5/4/20260724 (= ARGOS-SCI-003): OK"
    - "ACHADO: patient_group_count = 467 = case_count — no ledger congelado cada caso e seu proprio grupo (1 exame/paciente); o agrupamento por paciente e estrutural, nao exercitado por multiplos exames nesta coorte"
  reconciliacao_451_16:
    - "artefato canonico: medsiglip_multiclass_oof_evaluation_v1/evaluation.json"
    - "evaluation_signature (sha256 canonico): OK"
    - "training_protocol_signature == protocol_signature do lock: OK (cadeia lock->evaluation integra)"
    - "overall.case_count = 467; technical_failures = 16; computaveis = 451 — **BATE com o manuscrito (451/16)**"
    - "tp+tn+fp+fn = 167+188+59+53 = 467 — falhas DENTRO do denominador (ARGOS-SCI-004 confirmado no artefato real)"
    - "tp+fn = 220 (positivos), tn+fp = 247 (negativos) — SCI-002 confirmado na matriz de confusao real"
    - "sensibilidade 0.7591 / especificidade 0.7611 / passed_75_75 = True (ARGOS-SCI-005 no artefato real)"
BLOCKERS_ENCONTRADOS:
  - "As 3 fontes de labels protegidos do lock NAO existem nesta maquina (nem os diretorios-pai): verify_protocol completo e IMPOSSIVEL aqui. Os hashes congelados das fontes (406a74/9cd81b/2a3d27) so podem ser reverificados na maquina que as detem. Verificacao parcial (tudo exceto fontes) = 100% OK."
  - "Reexecucao COMPLETA do pipeline (retreino/re-inferencia) segue fora de alcance sem fontes+GPU; a reconciliacao feita e a do ledger e artefatos congelados, que era a pendencia registrada."
HUMAN_GATE: nenhum acionado; nenhuma divergencia encontrada (se houvesse, seria STOP)
DIFF_SUMMARY: nenhum arquivo do repo alterado; pack ganha task card + este evidence
FINAL_STATUS: DONE
```
