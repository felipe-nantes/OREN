# TOP_10_POST_AUDIT_TASKS — ranking das próximas tasks

Mix honesto conforme a evidência: 3 tasks científicas de MEDIÇÃO + 7 de
robustez/refactor/governança. Não forçamos 10 hipóteses de OOF — só 5
hipóteses têm evidência (OOF_IMPROVEMENT_REGISTER), e destas apenas as
medições entram no top 10 imediato. Scoring: POST_AUDIT_PLAN §4.

---

**RANK 1 · DS-PROBE-01** (= H-01)
- TASK: probes comparativas de origem entre variantes de embedding congeladas (localizar onde o sinal de domínio entra)
- CATEGORY: EXPERIMENTAL_OPPORTUNITY (medição)
- EVIDENCE: SR-007; docs/131:21,85; docs/134:53; variantes congeladas em hybrid_v1/
- WHY_NOW: decide todo o eixo domain-shift; probes globais saturadas; zero risco
- EXPECTED_INFORMATION_GAIN: HIGH
- POSSIBLE_OOF_IMPACT: nenhum direto (informa intervenções futuras)
- SCIENTIFIC_RISK: NONE (só leitura) · IMPLEMENTATION_RISK: LOW · COMPUTE_COST: LOW-MEDIUM (CPU)
- MODEL: Fable 5 · EFFORT: UltraCode · HUMAN_GATE: none (medição)
- EXPECTED_OUTPUT: mapa de separabilidade por variante/estágio + entrada no ledger + recomendação da próxima hipótese

**RANK 2 · GOV-01** (W-030/SR-006)
- TASK: campo de proveniência do estimando + teste negativo contra promoção da métrica de seleção + decisão do regime anti-consumo do outer
- CATEGORY: SCIENTIFIC_CHANGE (aditivo) / governança
- EVIDENCE: SR-006; docs/123; gap ~79-80 vs 75,91/76,11
- WHY_NOW: protege a validade de TODO o ciclo antes do primeiro experimento interventivo
- EXPECTED_INFORMATION_GAIN: HIGH · POSSIBLE_OOF_IMPACT: nenhum (protege a leitura)
- SCIENTIFIC_RISK: LOW · IMPLEMENTATION_RISK: LOW · COMPUTE_COST: LOW
- MODEL: Fable 5 · EFFORT: UltraCode · HUMAN_GATE: HG-07/HG-08 (proposta + decisão de regime)
- EXPECTED_OUTPUT: campo aditivo + teste negativo + regime decidido e registrado

**RANK 3 · FAIL-01** (= H-02)
- TASK: decompor as 16 falhas técnicas por causa raiz + upper bound analítico de recuperação
- CATEGORY: EXPERIMENTAL_OPPORTUNITY (medição)
- EVIDENCE: SCI-004; reconciliação 451/16 (PH06); campos do item 14
- WHY_NOW: upper bound decide se robustez de ingest vale mais que modelo
- EXPECTED_INFORMATION_GAIN: HIGH · POSSIBLE_OOF_IMPACT: indireto (orienta)
- SCIENTIFIC_RISK: NONE · IMPLEMENTATION_RISK: LOW (risco: artefato ausente — passo 1 é inventário) · COMPUTE_COST: LOW
- MODEL: Fable 5 · EFFORT: UltraCode · HUMAN_GATE: none (medição)
- EXPECTED_OUTPUT: taxonomia + upper bound + ledger; proposta gated se houver causa dominante

**RANK 4 · ROB-04/CI-01** (W-013)
- TASK: gates mecânicos na CI (ruff defeito, mypy módulos zerados, coverage floor)
- CATEGORY: ROBUSTNESS_FIX
- EVIDENCE: TD-004; conquistas PH07-08 desprotegidas
- WHY_NOW: protege o ciclo inteiro contra regressão mecânica silenciosa
- EXPECTED_INFORMATION_GAIN: MEDIUM · POSSIBLE_OOF_IMPACT: nenhum
- SCIENTIFIC_RISK: NONE · IMPLEMENTATION_RISK: LOW · COMPUTE_COST: LOW
- MODEL: Fable 5 · EFFORT: MEDIUM · HUMAN_GATE: none
- EXPECTED_OUTPUT: workflow atualizado + prova de detecção

**RANK 5 · ROB-01** (W-010)
- TASK: triagem dos 65 blind-excepts com CAN_CHANGE_SCIENTIFIC_RESULT por sítio
- CATEGORY: ROBUSTNESS_FIX
- EVIDENCE: estatística ruff PH08; risco de fail-open real
- WHY_NOW: maior silent_failure_risk do backlog de robustez
- EXPECTED_INFORMATION_GAIN: HIGH · POSSIBLE_OOF_IMPACT: possível (se algum sítio engole erro em rota científica)
- SCIENTIFIC_RISK: MEDIUM (por isso triagem gated) · IMPLEMENTATION_RISK: MEDIUM · COMPUTE_COST: LOW
- MODEL: Fable 5 · EFFORT: HIGH · HUMAN_GATE: por sítio
- EXPECTED_OUTPUT: ledger de sítios classificados + fixes NO aplicados + propostas gated

**RANK 6 · REP-01/ROB-05** (W-016)
- TASK: sonda de tolerâncias GPU na RTX 4060 (fecha BLK-GPU-TOLERANCES)
- CATEGORY: REPRODUCIBILITY
- EVIDENCE: decisão 9 (GPU EM ABERTO); sondas PH06 reutilizáveis
- WHY_NOW: único blocker formal fechável nesta máquina
- EXPECTED_INFORMATION_GAIN: HIGH · POSSIBLE_OOF_IMPACT: nenhum
- SCIENTIFIC_RISK: NONE (medição) · IMPLEMENTATION_RISK: MEDIUM (determinismo CUDA) · COMPUTE_COST: MEDIUM (GPU)
- MODEL: Fable 5 · EFFORT: HIGH · HUMAN_GATE: ratificação da tolerância (estende item 9)
- EXPECTED_OUTPUT: deltas por op + proposta de tolerância + blocker fechado

**RANK 7 · MEAS-01** (= H-03 + H-04, mesma sessão de análise)
- TASK: estabilidade do mecanismo de seleção (inner-only) + decomposição por coorte/reponderação sobre scores congelados
- CATEGORY: STATISTICAL (medição)
- EVIDENCE: SR-006, SR-007, LODO existente
- WHY_NOW: calibra o quanto do resultado é mecanismo vs sinal, antes de qualquer experimento
- EXPECTED_INFORMATION_GAIN: HIGH · POSSIBLE_OOF_IMPACT: nenhum direto
- SCIENTIFIC_RISK: LOW (interpretativo; esquemas a priori) · IMPLEMENTATION_RISK: LOW · COMPUTE_COST: LOW
- MODEL: Fable 5 · EFFORT: UltraCode · HUMAN_GATE: none (medição); leitura única do outer registrada
- EXPECTED_OUTPUT: dispersões + índice de dependência de composição + ledger

**RANK 8 · REF-01** (W-003)
- TASK: consolidação dos 56 helpers atomic
- CATEGORY: PURE_REFACTOR
- EVIDENCE: TD-007; auditoria AST PH04
- WHY_NOW: oracle forte já existe; fecha a última dimensão do TD-007
- EXPECTED_INFORMATION_GAIN: LOW · POSSIBLE_OOF_IMPACT: nenhum
- SCIENTIFIC_RISK: NONE (oracle bit a bit) · IMPLEMENTATION_RISK: LOW · COMPUTE_COST: LOW
- MODEL: Fable 5 · EFFORT: MEDIUM · HUMAN_GATE: none
- EXPECTED_OUTPUT: helper canônico + migração por lotes com hash idêntico

**RANK 9 · TEST-01** (W-011 + W-012 + ROB-02/03)
- TASK: gating ambiental do teste de GPU + perfil Hypothesis para suíte
- CATEGORY: ROBUSTNESS_FIX
- EVIDENCE: 1 falha ambiental em TODOS os portões da auditoria; flake único registrado
- WHY_NOW: sinal da suíte 100% verde viabiliza gates estritos de CI (RANK 4)
- EXPECTED_INFORMATION_GAIN: LOW · POSSIBLE_OOF_IMPACT: nenhum
- SCIENTIFIC_RISK: NONE · IMPLEMENTATION_RISK: LOW · COMPUTE_COST: LOW
- MODEL: Fable 5 · EFFORT: LOW · HUMAN_GATE: none
- EXPECTED_OUTPUT: suíte determinística sem falso-vermelho ambiental

**RANK 10 · PROV-01** (W-034 + W-033)
- TASK: mapa E016..E154 → {doc, comando, artefato, commit} + lacunas de ledger
- CATEGORY: REPRODUCIBILITY
- EVIDENCE: TD-012; SR-002/004/005
- WHY_NOW: base para qualquer defesa externa do manuscrito; alimenta W-042
- EXPECTED_INFORMATION_GAIN: MEDIUM · POSSIBLE_OOF_IMPACT: nenhum
- SCIENTIFIC_RISK: LOW · IMPLEMENTATION_RISK: LOW (grande, mas mecânico) · COMPUTE_COST: LOW
- MODEL: Fable 5 · EFFORT: MEDIUM · HUMAN_GATE: HG-01 para decisões de escopo
- EXPECTED_OUTPUT: PROVENANCE_MAP.yaml com cobertura declarada
