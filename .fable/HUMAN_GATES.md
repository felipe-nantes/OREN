# Human gates

Uma aprovação vale somente para o `TASK_ID`, diff/alternativa, contrato e evidência citados. Formato mínimo: `APROVO <HG-ID> para <TASK-ID>, opção <ID/hash>, escopo <paths/contratos>, aprovador <identidade>, data <ISO-8601>`.

## HG-01 — Scientific contract

- TRIGGER: criar, mudar, depreciar ou reinterpretar `SCIENTIFIC_CONTRACT`.
- WHAT_FABLE_MAY_DO: localizar fontes, reproduzir, escrever testes, comparar opções.
- WHAT_FABLE_MAY_NOT_DO: editar valor/semântica ou promover comportamento observado.
- EVIDENCE_REQUIRED: fonte L1/L2, impacto, before/after, regressão científica, rollback.
- APPROVAL_FORMAT: usar o formato mínimo global, citando `HG-01`, contrato e valor/opção aprovados.
- POST_APPROVAL_TESTS: testes de contrato + regressão científica + atualização de ledger.

## HG-02 — DICOM selection/phase logic

- TRIGGER: série/fase/sequence mapping, inclusão de derivados, ordenação ou fallback.
- WHAT_FABLE_MAY_DO: construir fixtures, caracterizar seleção, apontar ambiguidade.
- WHAT_FABLE_MAY_NOT_DO: escolher heurística clinicamente “melhor”.
- EVIDENCE_REQUIRED: tags, fixtures sem PHI, casos positivos/negativos, downstream geometry.
- APPROVAL_FORMAT: usar o formato mínimo global, citando `HG-02`, regra de seleção/fase e escopo aprovados.
- POST_APPROVAL_TESTS: DICOM contract/property/integration tests e auditoria de privacidade.

## HG-03 — Geometry/coordinates

- TRIGGER: LPS/RAS, origin, spacing, direction, affine, ordem de eixos ou unidade.
- WHAT_FABLE_MAY_DO: phantoms assimétricos, round-trips e patch hipotético.
- WHAT_FABLE_MAY_NOT_DO: alterar convenção sem aprovação.
- EVIDENCE_REQUIRED: landmarks físicos, transforms nomeados, tolerâncias e regressão.
- APPROVAL_FORMAT: usar o formato mínimo global, citando `HG-03`, convenção/transform e tolerâncias aprovadas.
- POST_APPROVAL_TESTS: property + geometric regression + integração.

## HG-04 — Registration/resampling/interpolation

- TRIGGER: fixed/moving, direção, reference grid, interpolador ou harmonização.
- WHAT_FABLE_MAY_DO: testar identidade/transformação conhecida/degeneração.
- WHAT_FABLE_MAY_NOT_DO: alterar método, parâmetros ou interpolador semanticamente.
- EVIDENCE_REQUIRED: transform/metric/optimizer, before/after, labels preservados.
- APPROVAL_FORMAT: usar o formato mínimo global, citando `HG-04`, fixed/moving, grade e interpolador aprovados.
- POST_APPROVAL_TESTS: regressão geométrica e científica pertinente.

## HG-05 — Segmentation/postprocessing semantics

- TRIGGER: modelo/task, mask gate, componente, morfologia, fusão ou cleanup.
- WHAT_FABLE_MAY_DO: medir máscara, comparar e propor.
- WHAT_FABLE_MAY_NOT_DO: limpar universalmente ou reclassificar máscara.
- EVIDENCE_REQUIRED: cohort/phantom, qualidade, falhas, impacto volumétrico.
- APPROVAL_FORMAT: usar o formato mínimo global, citando `HG-05`, modelo/task e semântica de máscara aprovados.
- POST_APPROVAL_TESTS: contracts, mask geometry, segmentation regression, volumetry.

## HG-06 — Labels/cohort/inclusion

- TRIGGER: labels, subtype, positive/negative, coorte, deduplicação, inclusão/exclusão.
- WHAT_FABLE_MAY_DO: auditar leakage/ledger.
- WHAT_FABLE_MAY_NOT_DO: relabel/redefinir população.
- EVIDENCE_REQUIRED: provenance, patient groups, denominadores, análise before/after.
- APPROVAL_FORMAT: usar o formato mínimo global, citando `HG-06`, versão do ledger/coorte/label aprovados.
- POST_APPROVAL_TESTS: split/leakage tests e regressão científica integral.

## HG-07 — ML preprocessing/CV/tuning

- TRIGGER: scaler/imputer/PCA/feature selection, folds, seeds, tuning, aggregation.
- WHAT_FABLE_MAY_DO: detectar leakage e montar experimento.
- WHAT_FABLE_MAY_NOT_DO: mudar desenho/tuning/folds.
- EVIDENCE_REQUIRED: fit boundaries, nested CV, OOF ledger, permuted-label test.
- APPROVAL_FORMAT: usar o formato mínimo global, citando `HG-07`, protocolo/splits/config hash aprovados.
- POST_APPROVAL_TESTS: full nested-CV regression e external/LODO quando aplicável.

## HG-08 — Threshold/metric/denominator

- TRIGGER: threshold, gate, métrica, IC/bootstrap, failure/inconclusive accounting.
- WHAT_FABLE_MAY_DO: verificar implementação contra contrato.
- WHAT_FABLE_MAY_NOT_DO: escolher threshold clínico ou otimizar no test set.
- EVIDENCE_REQUIRED: contrato, população, confusion/denominator, CI, delta completo.
- APPROVAL_FORMAT: usar o formato mínimo global, citando `HG-08`, threshold/métrica/denominador exatos aprovados.
- POST_APPROVAL_TESTS: metrics contracts + scientific regression.

## HG-09 — Model revision/representation

- TRIGGER: model/revision, input size, panel channels, normalization, embedding dimension/dtype.
- WHAT_FABLE_MAY_DO: validar hashes, compatibilidade e cache.
- WHAT_FABLE_MAY_NOT_DO: trocar representação/modelo silenciosamente.
- EVIDENCE_REQUIRED: model/preprocessing identity, cache invalidation, benchmark.
- APPROVAL_FORMAT: usar o formato mínimo global, citando `HG-09`, model ID/revision e representação aprovados.
- POST_APPROVAL_TESTS: embedding contracts, model regression, cache tests.

## HG-10 — Quantitative 3D cleanup

- TRIGGER: resampling, isovalue, smoothing, decimation, component removal, mesh-derived quantity.
- WHAT_FABLE_MAY_DO: comparar qualidade visual vs correção quantitativa.
- WHAT_FABLE_MAY_NOT_DO: declarar anatomia verdadeira ou aplicar cleanup quantitativo sem aprovação.
- EVIDENCE_REQUIRED: cube/sphere phantom, units, volume/surface error, topology and rollback.
- APPROVAL_FORMAT: usar o formato mínimo global, citando `HG-10`, operação/parâmetros e limites quantitativos aprovados.
- POST_APPROVAL_TESTS: geometric/volumetry/XR regressions.

## HG-11 — Privacy-sensitive data

- TRIGGER: dados clínicos, tags/UID/datas/private tags, overlays/burned-in pixels, logs/exports.
- WHAT_FABLE_MAY_DO: usar fixtures sintéticas/públicas desidentificadas e revisar política.
- WHAT_FABLE_MAY_NOT_DO: copiar PHI ao pack, Git, prompt ou log.
- EVIDENCE_REQUIRED: purpose, minimization, de-ID inspection, storage/deletion plan.
- APPROVAL_FORMAT: usar o formato mínimo global, citando `HG-11`, dados/propósito/retenção e aprovador responsável.
- POST_APPROVAL_TESTS: privacy negative tests e revisão humana de dados.

## HG-12 — Clinical claim

- TRIGGER: claim de diagnóstico, segurança, benefício, uso assistencial ou equivalência clínica.
- WHAT_FABLE_MAY_DO: registrar que a evidência não sustenta o claim.
- WHAT_FABLE_MAY_NOT_DO: decidir ou redigir como fato clínico.
- EVIDENCE_REQUIRED: revisão por especialista/regulatório fora do agente.
- APPROVAL_FORMAT: decisão formal do responsável clínico/regulatório, vinculada a `HG-12`; aprovação de engenharia isolada é inválida.
- POST_APPROVAL_TESTS: ainda exige escopo regulatório próprio; aprovação de engenharia não basta.
