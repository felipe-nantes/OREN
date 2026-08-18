# PHASE 02 — Contracts

STATUS: DONE (2026-08-17 — GOV-01 + TASK-2026-08-17-PH02-CONTRACTS-01)

EXIT_RESULT (2026-08-17): contratos científicos ratificados e CONGELADOS com os 3 CONFLICTs resolvidos por decisão humana (`HUMAN_DECISIONS.md`; registro sem nenhum CONFLICT); 15 contratos não científicos validados contra código com evidência file:line e teste protetor (tabela em `CONTRACTS.md`: 11 VERIFIED, 3 VERIFIED_OBSERVED, 1 by-composition; nenhuma divergência); owner designado (Felipe Nantes). Pendências documentadas fora do escopo do repo: reconciliação 451/16 por ledger e correção editorial de "assinado" no manuscrito. Lacunas de teste anotadas como insumo das fases 03-04.

OBJECTIVE: separar comportamento observado, contratos e políticas por módulo.  
INPUTS: maps, manuscript, standards, configs, tests.  
TASKS: validate interfaces, inputs/outputs/side effects/failures; ratify scientific contracts; resolve or gate conflicts.  
OUTPUTS: contract IDs, source/location/status/test links.  
ENTRY_CRITERIA: cartography accepted.  
EXIT_CRITERIA: critical modules have explicit software/geometric/scientific contracts and owners.  
BLOCKERS: manuscript/code ambiguities; human ratification.  
EVIDENCE: `CONTRACTS.md`, `SCIENTIFIC_CONTRACTS.yaml`, module cards.  

