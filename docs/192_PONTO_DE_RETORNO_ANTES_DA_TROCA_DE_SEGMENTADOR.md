# 192 — Ponto de retorno antes de avaliar a troca de segmentador

## Por que este documento existe

docs/191 mostrou que o `liver_segments_mr` bate o `total_mr` em 20/20 casos
contra referência humana. Antes de qualquer passo em direção a trocar o
segmentador de produção, ficou a exigência explícita: **garantir que voltar à
versão atual é fácil** — e verificado, não assumido.

Este documento registra o estado congelado e os caminhos de retorno.

## Estado congelado

| | |
|---|---|
| Commit | `73363e2` |
| Tag | `pre-liver-segments-mr` (anotada, no remoto) |
| Branch de trabalho | `feat/liver-segments-mr-avaliacao` |
| Árvore de trabalho | limpa no momento do congelamento |
| Segmentador em produção | `total_mr` (inalterado) |

## Lacunas que existiam e foram fechadas

Ao levantar o estado real, duas coisas não estavam garantidas:

1. **6 commits locais não estavam no remoto** — todo o trabalho das sessões
   recentes (docs/189 a docs/191) existia só neste disco. Verificado que o
   `git push` voltou a funcionar (havia falhado antes por credencial
   interativa) e os commits foram enviados: `5a93d84..73363e2`.
2. **`casos/` e `experiments/` são gitignorados** — git não restaura dado
   nenhum. O único dado mutável que uma troca de segmentador afetaria são as
   máscaras de união já existentes; havia **3**, somando 82 KB.

## Os quatro caminhos de retorno (independentes entre si)

| # | caminho | comando | cobre |
|---|---|---|---|
| 1 | Remoto | `git fetch origin && git reset --hard origin/main` | falha total do disco |
| 2 | Tag | `git checkout pre-liver-segments-mr` | retorno por nome, sem procurar hash |
| 3 | Branch | `git checkout main` | `main` nunca se moveu; sem `revert`, sem `reset` |
| 4 | Backup de dados | copiar de `experiments/_backup_unions_pre_troca/` | o que o git não cobre |

Verificação executada:

```
remoto : 73363e2b22f6...  refs/heads/main
tag    : 7f77793454...     refs/tags/pre-liver-segments-mr
branch : atual=feat/liver-segments-mr-avaliacao   main=73363e2
backup : 3 arquivos + SHA256SUMS.txt
```

O backup guarda checksums SHA-256 para que a restauração possa ser
**verificada**, não só executada:

```
a0457f8b...  34e241a43987_mask_organ_union.nii.gz
b5edda7e...  47a5d3d90085_mask_organ_union.nii.gz
4e049579...  50ea4e25cf01_mask_organ_union.nii.gz
```

## Por que o risco é pequeno mesmo antes desses passos

Vale registrar, para não superdimensionar o problema:

- A **Fase A** do plano (medição no regime real com contraste) escreve
  exclusivamente num diretório novo,
  `experiments/liver_segments_mr_vs_lld_venous_v1/`, que não existia — cria do
  zero, não sobrescreve nada.
- A **Fase B**, se acontecer, muda o segmentador **dentro do construtor da
  união**, que por desenho (docs/189) escreve num arquivo NOVO
  (`mask_organ_union.nii.gz`) e **nunca** toca em `mask_organ.nii.gz` — a
  máscara que alimenta a classificação. Uma reversão da flag de ambiente
  restabelece o comportamento anterior sem deploy.
- Nenhuma etapa planejada altera o caminho de decisão clínica. A Fase C
  (trocar o segmentador que alimenta os painéis de classificação) está
  **explicitamente fora de escopo**, porque invalidaria os números congelados
  do benchmark.

## Estado da produção neste ponto

Nenhuma alteração. `git status` em `dtwin/`, `webapp/`, `profiles/`,
`viewer/` e `configs/` estava vazio, e a suíte relevante seguia verde
(102 testes em `test_engine_finalize.py`, `test_webapp.py` e
`test_lld_mmri_v23_preparation.py`).

## Próximo passo

Fase A do plano: medir o `liver_segments_mr` na fase venosa **com contraste**
— o regime real de operação — usando cobertura de lesão anotada como âncora de
acurácia, com gate pré-especificado. É bloqueante: falhando, o `total_mr`
permanece e nada mais acontece.
