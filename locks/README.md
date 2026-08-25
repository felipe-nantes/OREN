# Lockfiles por ambiente (ROB-06 / W-015 / BLK-DEPS-LOCK)

Congelam o estado AUDITADO de cada backend em 2026-08-25 — nenhuma versão
foi alterada para gerá-los; são fotografias do que a auditoria validou.

| arquivo | ambiente | origem |
|---|---|---|
| `host_win_py313.lock.txt` | host Windows, Python 3.13 (`.venv-win`) | `pip freeze --all` do venv que produziu a baseline 1804/4/0 |
| `container_linux_py311.lock.txt` | container linux, Python 3.11 (`argos-runtime:local`) | freeze capturado na PHASE_00 (`evidence/PH00/container_pip_freeze.txt`) |

## Uso

Recriar um ambiente equivalente (exemplo host):

```bash
python -m venv .venv-novo
.venv-novo/Scripts/pip install -r locks/host_win_py313.lock.txt
```

Ou como *constraints* ao instalar o projeto (mantém os ranges do
pyproject, mas resolve nas versões auditadas):

```bash
pip install -e .[dev,training] -c locks/host_win_py313.lock.txt
```

## Limites declarados (honestidade sobre a verificação)

- O lock do host é o freeze do venv vigente — consistência com o ambiente
  auditado é por CONSTRUÇÃO. A verificação completa do backlog ("install do
  lock em venv limpa == freeze atual") exige ~10 GB de downloads (torch/cu124
  etc.) e NÃO foi executada; fica documentada como passo de validação para
  quando um ambiente novo for de fato criado.
- O lock do container reflete o stack da decisão 20 (torch 2.6.0+cu124,
  cudnn 90100). Mudança de stack exige re-sonda de tolerâncias GPU
  (HUMAN_DECISIONS item 20) — o lock existe exatamente para tornar essa
  mudança visível e deliberada, nunca acidental.
- Lockfiles NÃO substituem o `hybrid_v1_protocol.lock.json` (contrato
  científico); cobrem apenas dependências de software.
