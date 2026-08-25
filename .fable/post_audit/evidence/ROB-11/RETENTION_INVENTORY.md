# ROB-11 — Inventário de retenção de diretórios locais (W-017/TD-010)

Data: 2026-08-25 · NENHUMA deleção foi executada — este documento é
inventário + proposta; qualquer limpeza exige aprovação explícita
(HG-11 se houver dado de paciente).

## Inventário medido (fora de casos/, data/ e webapp — cobertos pela migração/ROB-09)

| diretório | GB | arquivos | classe proposta |
|---|---:|---:|---|
| `.venv-win` | 10,50 | 54.416 | **A — regenerável** (venv ativo; recriável via locks/host_win_py313.lock.txt) |
| `.venv-mrseg` | 5,15 | 38.418 | **A — regenerável** (venv do MRSegmentator) |
| `.venv` | 2,02 | 47.412 | **A — regenerável** (venv Linux/WSL py3.12; provável órfão no host Windows) |
| `.local/graphify-venv` | 0,16 | 5.081 | **A — regenerável** (venv do graphify) |
| `artifacts/` | 0,44 | 2.301 | **C — evidência de experimento** (benchmark_lote2 runs; citado por docs) |
| `experiments/` | 0,42 | 3.333 | **C — evidência de experimento** (benchmarks de segmentação v2, docs/196-199) |
| `graphify-out/` | 0,10 | 1.825 | **B — saída regenerável de ferramenta** (mapa arquitetural; regenerável pelo graphify) |
| `.codex-tmp` | 0,09 | 2.872 | **B — scratch de agente** (fonte do graphify duplicada) |
| `.mypy_cache`/`.ruff_cache`/`.pytest_cache`/`.hypothesis` | 0,04 | ~700 | **A — cache** (regeneram sozinhos) |
| `.tmp-medgemma-official` | 0,03 | 41 | **B — scratch** (contém um .git aninhado; corrompe robocopy — visto na migração) |
| `.pytest-tmp-v15`, `.pytest-tmp-v15-recreated`, `.timing-v16-work`, `.tmp` | ~0 | ~70 | **B — scratch histórico** |
| `contexto/`, `flywheel/` | ~0 | 20 | **D — manter** (estratégia do produto; dados anonimizados de teste) |

Total recuperável classe A: **~17,9 GB** (os 4 venvs + caches).
Classe B (scratch): ~0,25 GB. Classe C: NUNCA apagar sem gate (evidência).

## Política proposta (aguarda ratificação humana)

1. **Classe A (regenerável)**: elegível a remoção a qualquer momento SOB
   COMANDO EXPLÍCITO do operador; nunca automática. Pré-requisito cumprido:
   locks/ registra o estado para recriação (ROB-06). Nota: `.venv` (Linux)
   e `graphify-venv` parecem órfãos no host — candidatos primeiro.
2. **Classe B (scratch)**: janela de retenção proposta de 30 dias após o
   último uso; remoção listada e aprovada item a item.
3. **Classe C (evidência de experimento)**: retenção INDEFINIDA no estado
   atual; qualquer movimentação segue o padrão da migração SSD (copiar,
   verificar por comparação direta, só então propor remoção da origem).
4. **Classe D**: fora de escopo de limpeza.
5. **PHI**: nenhum dos diretórios acima deve conter DICOM de paciente; se
   algum item da classe B/C revelar conteúdo de paciente na revisão, ele
   passa imediatamente ao escopo da política ROB-09 (HG-11).

## Observação operacional (da migração SSD, 2026-08-24/25)

Os 4 venvs foram a causa das falhas de robocopy do Bloco B (reparse points
do uv + caminhos longos). A classe A é também a razão de o "resto" do
argos-main ter ~2 GB reais, não ~20 GB.
