# EVIDENCE PACKAGE — TASK-2026-08-18-PH04-INV-03

```yaml
TASK_ID: TASK-2026-08-18-PH04-INV-03
DATE: 2026-08-18 (America/Sao_Paulo)
BASE_COMMIT: main em dfb36b5; testes novos NÃO commitados
TASK_DESCRIPTION: >
  PHASE_04 wave 3 — SW-ATOMIC-01 (publicação atômica não expõe parcial como
  sucesso) e SW-ARTIFACT-01 (artefato consumido deve casar com hash; parcial/
  corrompido é recusado) codificados como property tests + auditoria estrutural.
ROUTE: [CACHE_ARTIFACTS, LOGGING_AUDIT_PROVENANCE, TESTS_BUILD_ENVIRONMENT]
MODULES: [ARTIFACT_PROVENANCE, VOLUMETRY, MEDSIGLIP_EMBEDDINGS, BENCHMARK_METRICS_REPORTING, TEST_SUITE]
FILES_ANALYZED:
  - 56 helpers atômicos mapeados por AST em dtwin/ (nome contendo "atomic")
  - canônicos citados pelo contrato, lidos e sondados empiricamente:
    benchmark/reporting.py:_atomic_text, learning/protocol.py:atomic_write_json,
    volumetry.py:_write_json_atomic, learning/medsiglip_embeddings.py:_atomic_npy
  - volumetry.py:558-583 (verify_volumetry_artifacts) para SW-ARTIFACT-01
FILES_CHANGED:
  - tests/test_property_atomic_and_artifact.py (NOVO; 12 testes)
RISK_LEVEL: LOW
AUTHORITY_LEVEL: PHASE_04 autorizada; nenhum código de produção alterado
CONTRACTS_INVOLVED: [SW-ATOMIC-01, SW-ARTIFACT-01]
SCIENTIFIC_CONTRACTS_INVOLVED: [nenhum editado]
BASELINE: 1633 passed / 0 failed / 4 skipped
BUG_REPRODUCTION: N/A — o invariante de ambos os contratos vale no código atual
TESTS_ADDED:
  - "test_property_escrita_atomica_produz_json_sempre_completo — Hypothesis, 100 exemplos"
  - "test_interrupcao_no_rename_nunca_expoe_destino_parcial — parametrizado nos 3 escritores canônicos"
  - "test_interrupcao_sem_versao_anterior_nao_cria_destino_parcial — idem, primeira publicação"
  - "test_escrita_atomica_de_npy_tambem_e_completa_ou_ausente — cobre NPY (embeddings)"
  - "test_auditoria_todo_helper_atomico_usa_temporario_mais_rename — varredura AST de 56 helpers"
  - "test_property_qualquer_adulteracao_de_byte_muda_o_hash — Hypothesis, 60 exemplos"
  - "test_artefato_de_volumetria_incompleto_e_recusado"
  - "test_artefato_de_volumetria_com_json_corrompido_e_recusado"
TESTS_AFTER:
  - "arquivo isolado: 12 passed, 4.59s"
  - "suíte completa: 1645 passed, 0 failed, 4 skipped, 103.50s"
MUTATION_RESULT: >
  Dois mutantes dirigidos, ambos detectados (EXIT_CRITERIA da fase):
  (1) módulo novo em dtwin/ com helper chamado `_write_json_atomic` que escreve
      direto no destino → auditoria estrutural FALHA (exit 1);
  (2) `volumetry._write_json_atomic` real substituído por escrita direta →
      o invariante de interrupção FALHA (2 failed / 4 passed).
  Ambos revertidos no finally; `dtwin/volumetry.py` confirmado byte-a-byte
  idêntico ao HEAD por `git hash-object` (8b5f2318… nos dois lados).
PROPERTY_TEST_RESULT: PASSED
BEHAVIOR_CHANGE: NONE (nenhum código de produção alterado)
SCIENTIFIC_BEHAVIOR_CHANGE: NONE
GEOMETRIC_BEHAVIOR_CHANGE: NONE
KNOWN_LIMITATIONS:
  - A interrupção é simulada patchando o rename; não cobre falha real de energia/kernel nem garantias de fsync do sistema de arquivos.
  - A auditoria estrutural é heurística sobre o NOME da função ("atomic"); um escritor não-atômico com outro nome não é alcançado por ela.
  - SW-ARTIFACT-01 foi coberto na camada de volumetria e de hash genérico; bundle de produção e shadow mask já tinham cobertura prévia (test_learning_visual_inference.py, test_segmentation_contract.py) e não foram duplicados.
UNRESOLVED_RISKS:
  - "TD-007 (divergência de semântica entre escritores atômicos) confirmado empiricamente — ver seção abaixo. Não corrigido nesta wave."
HUMAN_GATE: nenhum acionado
APPROVAL_STATUS: dentro do escopo autorizado
DIFF_SUMMARY: 1 arquivo de teste novo (~240 linhas)
ROLLBACK: deletar tests/test_property_atomic_and_artifact.py
FINAL_STATUS: DONE (não commitado)
```

## Achado empírico — TD-007 confirmado com evidência

O contrato SW-ATOMIC-01 é sobre o **destino**, e nesse ponto os três escritores
canônicos se comportam identicamente e corretamente: interrompidos entre
escrever o temporário e renomear, **o destino preserva exatamente a versão
anterior** (ou não passa a existir, na primeira publicação). O contrato vale.

A divergência prevista pelo `TD-007` ("semânticas divergentes") aparece na
**higiene do temporário**, e foi medida:

| Escritor | Destino íntegro na interrupção | Temporário após falha |
|---|---|---|
| `learning/protocol.py::atomic_write_json` | sim | limpo (`try/finally`) |
| `volumetry.py::_write_json_atomic` | sim | limpo (`try/finally`) |
| `learning/medsiglip_embeddings.py::_atomic_npy` | sim | limpo (`try/finally`) |
| `benchmark/reporting.py::_atomic_text` | sim | **vaza `.<nome>.tmp`** (sem `try/finally`) |

Correção seria de 2 linhas (envolver em `try/finally`), mas é código de
produção fora do escopo desta wave — registrado para decisão, não aplicado.

### Nota de método

A primeira sonda deste achado foi mal desenhada: interceptou `Path.write_text`,
o que impedia o temporário de ser criado e produzia um falso "nenhum
vazamento". Refeita interceptando o **rename** — o ponto de interrupção
realista — o vazamento apareceu. Os testes commitados usam o ponto correto.

Do mesmo modo, a auditoria estrutural flagrou inicialmente
`lld_mmri_v23_preparation.py::_write_jsonl_checkpoint_atomic`; a investigação
mostrou que ele publica via `_replace_checkpoint_file(...)` — um helper nomeado,
mais robusto que a média (fsync + validação + backup). O heurístico foi
ampliado para reconhecer delegação, em vez de silenciar o caso com allowlist.
