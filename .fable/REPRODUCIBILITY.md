# Reprodutibilidade

## Manifesto mínimo por execução

- commit/dirty state e diff relevante;
- sistema operacional, Python e package versions;
- config e hashes canônicos;
- model ID/revision/hash, backend e offline/local-files policy;
- input identity/hash e licença/proveniência;
- seeds, folds e patient groups;
- CPU/GPU/driver/CUDA/MPS, dtype e tolerância;
- outputs/hashes, tempos warm/cold, falhas e denominadores;
- comando completo e timestamps UTC.

## Observado

Há hashes, protocol locks, escrita atômica, checkpoints/resume e manifests em vários subsistemas (`dtwin/learning/protocol.py`, `medsiglip_embeddings.py`, benchmark/reporting e volumetry). A implementação é distribuída e não há um único lock de ambiente cobrindo todos os extras, modelo, driver e hardware.

## Regras

- Mesma lógica não implica igualdade bitwise entre CPU/CUDA/MPS/releases.
- Separe `LOGIC_REGRESSION` determinística de `NUMERICAL_REGRESSION` com tolerância aprovada.
- Cache é válido somente para identidade de input+modelo+revision+preprocessing+config+pipeline+artefato.
- Run retomada deve verificar prefixo/checkpoint/hash; presença de arquivo não equivale a conclusão.
- Métrica deve registrar população, unidade, endpoint, n, falhas, TP/TN/FP/FN e método de IC.
- “Assinado” deve declarar se significa SHA-256/canonical hash ou assinatura criptográfica.

## Lacunas prioritárias

Lockfile completo, imagem/container digest, baseline por backend, tolerâncias cross-hardware, provenance uniforme e reprodução independente da Etapa C.

