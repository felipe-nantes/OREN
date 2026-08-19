# EVIDENCE PACKAGE — TASK-2026-08-18-PH06-REG-02

```yaml
TASK_ID: TASK-2026-08-18-PH06-REG-02
DATE: 2026-08-18 (America/Sao_Paulo)
BASE_COMMIT: main em 637d9e1
TASK_DESCRIPTION: >
  PHASE_06 wave 2 — tolerancias numericas por backend, MEDIDAS (fecha a
  metade "medir" da decisao humana item 8 de 2026-08-17; a ratificacao da
  proposta e a outra metade).
ROUTE: [REPRODUCIBILITY, METRICS_STATISTICS, GEOMETRY, HARMONIZATION_RESAMPLING]
MODULES: [cross-cutting]
METODO: >
  Sonda deterministica identica (evidence/PH06/ph06_backend_probe.py) executada
  em dois backends reais, sem GPU (alvo: bibliotecas CPU):
  HOST    = Windows 11 / Python 3.13.14 / numpy 2.5.0 / SimpleITK 2.5.5
  CONTAINER = Linux WSL2 / Python 3.11.11 / numpy 2.2.2 / SimpleITK 2.5.6
  Quantidades: digest canonico de splits (24 casos sinteticos, 4/3 folds,
  seed 20260724); Wilson em 6 pontos incl. extremos; volumetria em phantom
  anisotropico (0.7x1.3x2.9mm, origem nao trivial); harmonizacao linear
  float32 entre grades diferentes (soma/media/cobertura + checksum bitwise).
RESULTADOS:
  - "LOGIC (splits digest): IDENTICO"
  - "Wilson (12 valores): delta maximo = 0.0"
  - "Volumetria: voxel_count identico (7153); voxel_volume_mm3 e volume_ml delta = 0.0"
  - "Harmonizacao: cobertura/soma/media delta = 0.0; array resampleado BITWISE IDENTICO (sha256 canonico igual)"
  - "CONCLUSAO EMPIRICA: para os componentes CPU sondados, a variacao cross-backend observada e ZERO, apesar de SO/Python/numpy/SimpleITK diferentes."
PROPOSTA_DE_TOLERANCIAS (aguardando ratificacao humana):
  - "LOGIC (splits, digests, contagens, voxel_count, denominadores): igualdade EXATA obrigatoria entre backends. Divergencia = bug, nunca tolerancia."
  - "NUMERICAL escalar CPU (Wilson, volumes mm3/mL, cobertura, medias): tolerancia relativa <= 1e-12 (na pratica bitwise; a margem cobre reassociacao de somas em versoes futuras de lib sem mascarar erro real)."
  - "NUMERICAL array CPU (resample/harmonizacao): fracao de voxels divergentes acima de 1e-9 relativo deve ser 0 no escopo de versoes testado; mudanca de major de numpy/SimpleITK exige re-executar a sonda ANTES de aceitar novos numeros."
  - "GPU/CUDA (TotalSegmentator, MedGemma, torch): NAO MEDIDO nesta wave (fora de alcance sem carga na GPU dedicada a testes). Igualdade bitwise segue NAO assumida (decisao item 8). Tolerancias GPU ficam explicitamente EM ABERTO."
ARTEFATOS: [evidence/PH06/probe_host.json, evidence/PH06/probe_container.json, evidence/PH06/ph06_backend_probe.py, evidence/PH06/ph06_compare.py]
BLOCKERS: [GPU nao sondada]
HUMAN_GATE: ratificacao das tolerancias propostas (fecha HUMAN_DECISIONS item 8)
NOTA_OPERACIONAL: >
  As imagens Docker "sumiram" de novo ao recriar settings-store.json; causa
  raiz identificada e corrigida por restauracao da chave
  UseContainerdSnapshotter=true (as imagens vivem no store containerd, 45GB).
  Memoria e KNOWN_FAILURES atualizados.
FINAL_STATUS: DONE (medicao); ratificacao pendente
```
