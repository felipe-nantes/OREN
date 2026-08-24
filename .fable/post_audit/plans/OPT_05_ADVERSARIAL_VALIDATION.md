# OPT_05 — ADVERSARIAL_VALIDATION

Objetivo: tentar REFUTAR cada candidato promissor antes de promover.

Ataques mínimos por candidato (registrados em
CANDIDATE_COMPARISON.adversarial_validation):
1. leakage hunt: fronteiras train-only de preprocessing; splits revalidados;
   nenhuma estatística de teste no caminho de treino;
2. domain dependence: origin probe antes/depois; candidato que sobe agregado
   E sobe dependência de origem é suspeito de shortcut;
3. cohort stress: por coorte + LODO; piora localizada = flag;
4. failure stress: composição de falhas; denominador re-reconciliado;
5. variance: dispersão entre runs/seeds vs delta observado (delta < ruído =>
   não há efeito);
6. mutation probes nos guards novos (técnica hash-verificada das fases 07-09);
7. sanity: assinaturas de artefatos (load_frozen_oof_predictions) e âncoras
   do lock intactas.

Critério de saída: candidato "survived: true" com todos os ataques
registrados, ou refutado (ledger: decision REJECTED + lessons).
Effort: UltraCode (raciocínio adversarial científico).
