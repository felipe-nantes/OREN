# EVIDENCE — TASK-2026-08-18-PH06-REG-03 (exit review da PHASE_06)

## EXIT REVIEW — PHASE_06_SCIENTIFIC_REGRESSION

EXIT_CRITERIA do card: "relevant pipeline changes can be compared honestly
across cohorts/hardware."

| Item do card | Resultado | Onde |
|---|---|---|
| reproduce ledgers/OOF/confusions/CI | Ledger congelado íntegro (assinatura, config/splits hashes, universo 467); evaluation OOF canônica assinada e encadeada ao lock; matriz de confusão real reconcilia 467=220+247, **451/16**, gate 75/75 | wave 1 (REG-01) |
| isolate logic vs numerical tolerance | Medido em 2 backends reais: LOGIC idêntico, NUMERICAL delta ZERO (bitwise); tolerâncias RATIFICADAS pelo humano (HUMAN_DECISIONS bloco 3) | wave 2 (REG-02) |
| verify patient groups and failure denominators | patient_group_count=467 verificado (1 exame/paciente no ledger); falhas DENTRO do denominador confirmadas no artefato real (SCI-004) | wave 1 |
| versioned minimal regression datasets | sondas + JSONs dos 2 backends versionáveis em evidence/PH06/ | wave 2 |

BLOCKERS declarados (não ocultados):
1. As 3 fontes de labels protegidos NÃO existem nesta máquina — verify_protocol
   completo (re-hash das fontes) só é possível na máquina que as detém.
2. GPU/CUDA não sondada — tolerâncias GPU explicitamente EM ABERTO.
3. Reexecução completa do pipeline (retreino) fora de alcance sem fontes+GPU.

VEREDITO: EXIT_CRITERIA satisfeito no escopo alcançável nesta máquina, com a
comparação honesta entre hardwares estabelecida por medição e ratificada.
**PHASE_06 = DONE** (com os 3 blockers acima registrados para a máquina que
detém as fontes protegidas).
