# Ferramentas determinísticas

Snapshot em 2026-08-17, commit `9683eaa…`. Não instale nada automaticamente; mudança de toolchain/dependência é MEDIUM e pode elevar a HIGH.

| Ferramenta | Estado host/.venv-win | Uso | Próximo gate |
|---|---|---|---|
| Python | AVAILABLE 3.13.14 | runtime/CI compatível com `>=3.10,<3.14` | registrar patch version |
| pytest | AVAILABLE em `.venv-win` | 1.610 testes coletados | executar baseline global |
| GitHub Actions | AVAILABLE | `doctor` + pytest Python 3.13 | preservar antes de expandir |
| Graphify 0.9.42 | AVAILABLE via `tools/graphify_argos.ps1`/Docker | mapa arquitetural, sem dados médicos | query antes de codebase task |
| Docker CLI/Compose | CLIENT AVAILABLE; daemon OFF | runtime Windows/Mac/Quest | ligar e baseline containerizado |
| coverage.py | NOT_AVAILABLE | branch coverage | RECOMMENDED após baseline |
| Hypothesis | NOT_AVAILABLE | property tests | RECOMMENDED geometria/cache/metrics |
| Ruff | NOT_AVAILABLE | lint/imports | RECOMMENDED, primeiro report-only |
| mypy | NOT_AVAILABLE | typing/static | RECOMMENDED incremental, não gate global imediato |
| pip-audit | NOT_AVAILABLE | supply chain | RECOMMENDED report-only |
| mutmut/Cosmic Ray | NOT_AVAILABLE | mutation | RECOMMENDED seletivo |
| pytest-benchmark | NOT_AVAILABLE | performance | RECOMMENDED em ambiente controlado |

## Comandos conhecidos

```powershell
# Consulta arquitetural; grafo de engenharia, nunca dados médicos
powershell -ExecutionPolicy Bypass -File tools/graphify_argos.ps1 -Action Query -Question "..."

# Coleta sem executar e sem cache
.\.venv-win\Scripts\python.exe -m pytest --collect-only -q -p no:cacheprovider

# Suite atual (executar apenas em baseline autorizado)
.\.venv-win\Scripts\python.exe -m pytest -q

# Preflight atual
.\.venv-win\Scripts\python.exe digital_twin.py doctor
```

## Regras

- Capture versão, comando, exit code e ambiente.
- Nunca “corrija” findings automaticamente durante auditoria.
- Static analysis não substitui contracts/tests.
- Benchmark exige hardware, warm/cold cache, rounds e tolerâncias declarados.
- Graphify arquitetural é separado de `dtwin/graphrag`; nunca indexe DICOM/NIfTI/labels/máscaras/case outputs.

