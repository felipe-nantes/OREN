# TASK-2026-08-25-ROB-BATCH — backlog de robustez ROB-06..11 (W-014/015/017/018/020/039)

STATUS: DONE (2026-08-25) - 4 fechados (W-014/015/018/039), 2 entregaveis aguardando gates (W-017/020); suite 1807/4/0
Autorização: Felipe Nantes, 2026-08-25 ("commit e push, depois siga para os
backlogs de robustez"). Executor: Fable 5 · Efforts: LOW-HIGH por item ·
Gates: HG-11 para ROB-09 (proposta apresentada) e ratificação da política
ROB-11; demais sem gate.

## ROB-07 (W-014) — git na imagem: skipif declarado — DONE

Runtime oficial é NATIVO (migração 2026-08-18); mudar a imagem legada seria
o lado errado. Lista REAL medida rodando a suíte sem git no PATH: **8
testes** (a auditoria contava 6; cresceu) em 4 arquivos — inclui 2 guards
de PHI que USAM git para verificar não-versionamento (sem git, não há como
checar; skip é honesto). Marker único `requer_git` em tests/conftest.py
(`shutil.which("git") is None`), aplicado aos 8. Verificação dupla:
sem git → skips limpos; com git → tudo roda. Suíte com git: 1804/4/0.
Nenhum assert enfraquecido.

## ROB-08 (W-039, metade final) — agregador de auditoria DICOM — DONE

`aggregate_phase_resolution_audit()` ADITIVA em raw_dicom_phase_resolver
(leitura pura de manifestos; heurística intocada) + ligada em
tools/run_raw_phase_equivalence_benchmark: grava
`phase_resolution_audit_summary.json` SEPARADO (o benchmark_report.json
congelado não muda). 3 testes novos pinam o contrato (vazio; agregação;
manifesto pré-item-14 sem os campos). Com a metade documental da DOC-01,
**W-039 fecha inteiro**.

## ROB-06 (W-015) — lockfiles por backend — DONE (verificação declarada)

`locks/host_win_py313.lock.txt` (freeze do venv da baseline, 167 pacotes) +
`locks/container_linux_py311.lock.txt` (freeze PH00 do container, 225) +
README com uso e LIMITES HONESTOS: a validação "install em venv limpa"
custa ~10 GB e não foi executada — documentada como passo obrigatório
quando um ambiente novo nascer. BLK-DEPS-LOCK atendido no essencial
(estado auditado congelado e versionado).

## ROB-10 (W-018) — TODO server.py:2554 — DONE: FALSO POSITIVO PROVADO

Reprodução revelou que **não há TODO**: o comentário diz "marcando TODO
exame como falha" — português "todo (= every) exame", capturado pelo scan
de TODOs da PHASE_03 como marcador inglês. O cenário descrito (case_dir
relativo → launcher em %TEMP% → tudo falha → fallback CPU) é PREVENIDO por
`.resolve()` nos 4 sítios (benchmarks.py:367; jobs.py:57/218/615).
Nenhum fix necessário; nenhum gate disparado.

## ROB-11 (W-017) — inventário de retenção — ENTREGUE (política aguarda ratificação)

`evidence/ROB-11/RETENTION_INVENTORY.md`: 19 diretórios medidos; classes
A regenerável (~17,9 GB: 4 venvs + caches), B scratch (~0,25 GB),
C evidência de experimento (nunca sem gate), D manter. NENHUMA deleção
executada. Política proposta por classe; venvs órfãos (.venv Linux,
graphify-venv) apontados como primeiros candidatos SOB COMANDO.

## ROB-09 (W-020/SR-010) — política PHI — PROPOSTA ENTREGUE ao HG-11

`evidence/ROB-09/PHI_RETENTION_POLICY_PROPOSAL.md`: P1 corrigir a
divergência `phi_persisted:false` vs DICOM materializado (recomendação:
limpeza pós-conversão validada); P2 TTL 30d de `_upload/` concluídos
(execução sempre por comando); P3 retenção conservadora p/ casos de
resultados congelados; P4 burned-in PHI = revisão humana obrigatória antes
de qualquer imagem sair de casos/ (sem detector "mágico"); P5 migrações
herdam a política. 4 decisões pedidas ao operador. Nenhum PHI lido/movido.

## Verificação do lote

- ROB-07: suíte sem git = skips honestos; com git = 1804/4/0.
- ROB-08: 29 testes (3 novos + characterization do resolver) verdes; gates
  ruff limpos.
- Portão suíte completa: **1807 passed / 4 skipped / 0 failed** (2m22s;
  +3 do agregador).
