# EVIDENCE — TASK-2026-08-18-PH07-ADV-01 (PHASE_07, wave 1: baseline adversarial)

Data: 2026-08-18 (America/Sao_Paulo) · Executor: agente (Claude Code) · Aprovador da fase: Felipe Nantes
Protocolo: context-efficient review (bloco 4 de HUMAN_DECISOES; ferramentas determinísticas primeiro).

## RESUMO

Wave 1 concluída: baseline de cobertura por branch da suíte completa + corte do
núcleo científico (8 módulos), auditoria de dependências (pip-audit) com
remediação, varredura mypy do núcleo, e gap ledger. NENHUM código de produção
foi alterado para elevar cobertura (proibição da wave respeitada); a única
mudança de ambiente foi `setuptools 70.2.0 → 84.0.0` (remediação de CVE, sem
impacto em runtime científico — build tooling).

## Comandos (determinísticos, reproduzíveis)

```
pytest -q -p no:cacheprovider --cov=dtwin --cov=webapp --cov-branch --cov-report=
coverage json -o .fable/evidence/PH07/coverage_branch_2026-08-18.json
coverage report --include=<8 módulos do núcleo> --show-missing --precision=1
pip-audit  (antes/depois em evidence/PH07/pip_audit_*.txt)
mypy <núcleo científico>  (evidence/PH07/mypy_nucleo_2026-08-18.txt)
```

## OBSERVED — suíte

- **1706 passed / 4 skipped / 1 failed** em 225,98s (.venv-win, py3.13.14).
- Falha única: `tests/test_learning_environment.py::test_environment_report_accepts_free_gpu`
  — AMBIENTAL (exige GPU livre; VRAM ocupada durante a medição). Mesma classe
  de falha intermitente já registrada no estado; não é regressão de código.

## OBSERVED — cobertura por branch

Global (dtwin+webapp, 254 arquivos): **62,9%** branch (39.603 stmts, 12.884
branches, 2.760 parciais). JSON: `evidence/PH07/coverage_branch_2026-08-18.json`.

Núcleo científico (corte definido no task card): **82,6%** branch.

| Módulo | Stmts | Miss | Branch | BrPart | Cover |
|---|---|---|---|---|---|
| dtwin/benchmark/metrics.py | 96 | 0 | 18 | 0 | **100,0%** |
| dtwin/learning/raw_dicom_phase_resolver.py | 210 | 20 | 66 | 6 | 89,9% |
| dtwin/learning/multiphase_ingest.py | 150 | 15 | 50 | 8 | 87,5% |
| dtwin/learning/splits.py | 107 | 10 | 52 | 10 | 87,4% |
| dtwin/learning/visual_inference.py | 130 | 16 | 24 | 2 | 87,0% |
| dtwin/volumetry.py | 274 | 41 | 106 | 27 | 80,0% |
| dtwin/segmentation_contract.py | 136 | 22 | 50 | 16 | 79,6% |
| dtwin/learning/robustness.py | 186 | 63 | 62 | 2 | **63,3%** |

## GAP LEDGER (núcleo científico)

Mapeamento faixa→função por AST (determinístico). Prioridade = risco para os
contratos congelados (SCI-004 denominadores, SCI-013 IC, GEO-004 volume).

| # | Módulo · faixas | O que está descoberto | Criticidade | Ação proposta |
|---|---|---|---|---|
| G1 | robustness.py 49-86 | `_json`, `_jsonl`, `load_frozen_oof_predictions` — loaders de artefatos OOF congelados | ALTA (porta de entrada dos denominadores SCI-004) | Wave 2/3: testes com fixtures sintéticas (não requer dados reais) |
| G2 | robustness.py 369-412 | `evaluate_robustness` — orquestrador LODO/bootstrap/subgrupos | ALTA | idem G1 (fixture sintética encadeada) |
| G3 | robustness.py 416-495 | `render_markdown_report` — renderização (inclui formatação de ICs) | MÉDIA | Wave 3 ou aceitar como apresentação |
| G4 | robustness.py 171, 312 | borda de `_percentile`; 1 braço de `clinical_subtype_map` | BAIXA | alvo de mutação |
| G5 | segmentation_contract.py 91-98, 111-113, 136-143, 178-188, 218-222, 274-291 | braços de raise/early-return da validação fail-closed (16 branches parciais) | ALTA (critério de saída da fase: "failures fail-closed") | Wave 2: mutação dirigida nos braços de erro |
| G6 | splits.py 30, 160-192 | braços de raise da validação de isolamento (10 branches parciais; property tests usam `assume(False)` em PipelineError, então o caminho de erro é subexercitado) | ALTA (SCI-003) | Wave 2: mutação dirigida + 2-3 testes negativos diretos |
| G7 | volumetry.py 56-68, 277-334, 571-598 | braços de erro de IO/validação e ramo final de sumarização | MÉDIA-ALTA (GEO-004) | Wave 2: mutação dirigida |
| G8 | resolver 67-108, 274-289, 319-333 · ingest 87-190, 267-289 · visual_inference 125-130, 242-267 | braços de fallback/erro dispersos | MÉDIA | mutação dirigida seletiva |
| G9 | Fora do núcleo: scripts one-shot `dtwin/benchmark/openswisshcc_*` e afins a 0-17% | análises executadas uma vez contra a coorte real (ausente nesta máquina) | JUSTIFICADO | Não testar aqui — coberto por BLK-PROTECTED-SOURCES / BLK-FULL-REEXECUTION; resultados congelados no lock |

## OBSERVED — pip-audit

- Antes: `setuptools 70.2.0` com PYSEC-2025-49 e PYSEC-2026-3447
  (`evidence/PH07/pip_audit_2026-08-18.txt`).
- Remediação: `setuptools 84.0.0`; re-audit **limpo**
  (`evidence/PH07/pip_audit_pos_fix_2026-08-18.txt`).
- Declarado: `torch/torchvision cu124` não auditáveis pelo índice (builds cu124
  fora do PyPI) — UNKNOWN, não "sem vulnerabilidade".

## OBSERVED — mypy (núcleo)

18 achados (`evidence/PH07/mypy_nucleo_2026-08-18.txt`). Candidato real
sinalizado: `robustness.py:226/233` — `sorted()` sobre `str | None` (TypeError
latente se subtipo None entrar na chave). Correção fica para PHASE_08 (mudança
LOW), registrado aqui como insumo.

## Classificação de evidência

- OBSERVED: tudo nas seções acima (saídas de pytest/coverage/pip-audit/mypy salvas em evidence/PH07/).
- SOURCE_SUPPORTED: mapeamento faixa→função (AST do fonte no working tree).
- INFERRED: criticidades do gap ledger (juízo do agente sobre os contratos; revisável).
- UNKNOWN: compat do mutmut 3.7.0 com Windows (não exercitado); auditabilidade de torch cu124.

## CONTEXT_EFFICIENCY

- Ferramentas determinísticas fizeram todo o trabalho pesado (pytest/coverage/AST/pip-audit/mypy); nenhuma releitura integral de módulo foi necessária — leituras simbólicas apenas para nomear funções descobertas.
- Suíte completa executada 1x em background (3m46s); artefatos derivados (JSON + 2 reports) extraídos do mesmo run, sem reexecução.
- Contexto protegido (SAFETY_KERNEL, contratos, gates) não foi comprimido; âncoras citadas por ID.
- Custo de contexto da wave: ~4 comandos + 2 tabelas; evidência integral vive nos arquivos, não no prompt.

## Proibições respeitadas

- Nenhum código de produção alterado para elevar cobertura.
- Nenhum teste removido/enfraquecido.
- Nenhum commit/push (aguarda solicitação explícita).

## Próxima wave proposta (aguarda autorização)

Wave 2 — mutação seletiva: alvos G4-G8 (braços de erro fail-closed de
splits/segmentation_contract/volumetry) via mutmut 3.7.0 (compat Windows
UNKNOWN; fallback = sondas de mutação dirigida manuais, técnica já validada na
PHASE_04 com 8 mutantes detectados). Ledger de mutantes sobreviventes como
saída. G1/G2 (fixtures sintéticas para loaders de robustness) podem entrar na
mesma wave se autorizado.
