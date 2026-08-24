# OPT_00 — WEAKNESS_INVENTORY

Objetivo: consolidar tudo o que a auditoria encontrou.

Entradas: WEAKNESS_REGISTER.yaml (35 itens semeados no planejamento),
EXPERIMENT_LEDGER.yaml (5 seeds com campos TO_ENUMERATE), SR/TD registers,
MANUSCRIPT_VS_CODE, evidence PH00-PH10.

Trabalho:
1. Completar os TO_ENUMERATE do ledger lendo docs/ e
   casos/qualification/hybrid_v1/ (métricas e decisões dos experimentos
   anteriores — ablações, fusões, variantes).
2. Ler os CONFLICTs 2-4 e o UNVERIFIED do MANUSCRIPT_VS_CODE e detalhar
   W-042 (hoje sumarizado).
3. Validar cada W-### contra o código atual (nada mudou desde 9288785?).
4. Revisar priority/effort com o aprovador se houver discordância.

Saída: registros completos, zero TO_ENUMERATE.
Critério de saída: aprovador confirma o inventário como base do ciclo.
Gate: nenhum (leitura e registro).
Effort típico: MEDIUM (enumeração) com pontos UltraCode (reconciliação manuscrito).
