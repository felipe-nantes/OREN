# EVIDENCE — TASK-2026-08-24-OPT00-INV-01 (OPT_00: consolidação do inventário)

Data: 2026-08-24 · Executor: agente (Fable 5) · Autorização: Felipe Nantes
("commit e push, depois inicie a OPT_00").

## RESUMO

OPT_00 concluída: os 4 campos TO_ENUMERATE do EXPERIMENT_LEDGER foram
preenchidos com números reais extraídos dos artefatos congelados; um índice
completo de **43 avaliações congeladas** foi gerado e versionado como
evidência; W-042 foi detalhado com o conteúdo real dos CONFLICTs/UNVERIFIED
do MANUSCRIPT_VS_CODE; o baseline foi revalidado contra os 2 commits novos.
Nenhum código/teste/contrato tocado.

## OBSERVED — enumeração do ledger (fonte: casos/qualification/hybrid_v1)

- **SEED-002 (vocabulário)**: binário 76,4/75,8/bal 76,14 vs subtipo
  75,2/77,0/bal 76,06 (n=335; ambos passed) — EMPATE; vocabulário fino não
  pagou no agregado.
- **SEED-003 (fusões)**: TRÊS negativos congelados — late fusion bal 72,0
  (n=132, reprovada, mesmo acima de cada componente); multi_signal_fusion
  bal 72,8 em n=467 (ABAIXO do oficial 76,0); fusão do estimador oficial
  gate_ii_passed=False em v1 E v2.
- **SEED-004 (variantes)**: índice de 43 evaluation.json em
  `evidence/OPT00/frozen_evaluations_index_2026-08-24.txt`. Só 5/43 passaram
  75/75; baseline oficial confirmado no artefato
  (`medsiglip_multiclass_oof_evaluation_v1`: 75,9/76,1, n=467 — bate o
  manuscrito); TODAS as variantes OpenSwiss-only entre 45-63 bal (n=44-132)
  — a perda de transferência do SR-007, quantificada artefato a artefato;
  LoRA 72,7 > head 70,0 (ambas reprovadas).
- **SEED-005 (ROI)**: linha de candidatos localizados automáticos congelada
  em bal 50,2-52,9 (n=87, 4 variantes, nenhuma passou) — o gap
  localização vs ROI correta tem números.

## OBSERVED — W-042 detalhado (MANUSCRIPT_VS_CODE lido na íntegra dos itens)

4 CONFLICTs (MVC-021, MVA-001, MVA-003, MVA-013) + 1 UNVERIFIED (MVA-008) +
2 relacionados (MVA-002 MANUSCRIPT_ONLY, MVA-014). Constatação central:
**MVA-001 já está resolvido no lado da engenharia** pela decisão 1 (GEO-002,
dois contratos escopados — Dice 0,80 coortes / coverage 0,50 produto); o que
resta em todos os itens é majoritariamente a ponta EDITORIAL do manuscrito,
mais as decisões humanas já registradas como pendentes (W-020/SR-010,
W-044/SR-020). Nenhum item novo de engenharia surgiu.

## OBSERVED — revalidação do baseline

Desde o registro (base 9288785): 2 commits novos — `0d56547` (operador, fora
da sessão: fix do health-check HTTPS em `tools/start_oren_quest_dynamic.ps1`,
parâmetro `-SkipCertificateCheck` inexistente no PowerShell 5.1 causava falso
"webapp fora do ar") e `d7e4ace` (o próprio plano post_audit). Nenhum dos 35
W-### é afetado (o fix toca launcher do Quest, área sem item aberto; nada de
produção científica mudou). Inventário permanece válido sobre `d7e4ace`.

## Divergências de prioridade/effort

Nenhuma identificada que exija revisão do aprovador — os números enumerados
REFORÇAM as prioridades já postas: os 3 negativos de fusão e o empate de
vocabulário elevam o valor relativo das medições H-01/H-03/H-04 (entender
antes de tentar de novo); os OpenSwiss-only a 45-63 confirmam domain shift
como eixo nº 1.

## Classificação de evidência

- OBSERVED: todas as métricas acima (lidas dos evaluation.json congelados,
  com assinaturas presentes nos artefatos); diff do commit externo.
- SOURCE_SUPPORTED: correspondência 335=157+178 com SR-003; correspondência
  75,9/76,1 com o manuscrito.
- INFERRED: nada material.
- Labels clínicos protegidos NÃO foram lidos (somente métricas agregadas e
  metadados de avaliação).

## CONTEXT_EFFICIENCY

- 43 avaliações enumeradas com 1 varredura programática (schema comum
  overall.*); zero releitura de módulos de código.
- Leituras dirigidas: 3 blocos do MANUSCRIPT_VS_CODE, 1 git show, 5 JSONs
  profundos — total ~8 comandos para fechar a fase inteira.
- O índice virou artefato reutilizável (lista do-not-repeat de OPT_03/04).

## Critérios de saída

- [x] Ledger com zero TO_ENUMERATE
- [x] W-042 detalhado
- [x] Baseline revalidado (d7e4ace)
- [x] Evidence package

OPT_00 DONE. Próxima fase sugerida: OPT_01 (refactors com oracle) ou direto
DS-PROBE-01 (primeira task recomendada, medição de domain shift) — a
autorização é do operador.
