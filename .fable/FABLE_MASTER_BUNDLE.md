# ARGOS/OREN Fable Engineering Pack — master fallback

Este arquivo permite recuperação rápida quando navegação modular falhar. A fonte principal continua sendo os arquivos apontados; não copie este bundle para substituir contratos/cartões mais atuais.

## 1. Papel e fronteira

O agente faz engenharia de software científico: testes, correção numérica, processamento, geometria, infraestrutura ML/estatística, reprodutibilidade e auditoria. ARGOS/OREN permanece experimental, `research_only`, revisão humana obrigatória, sem claim de diagnóstico, segurança clínica, terapia, cirurgia ou anatomia verdadeira. `CLINICAL_CLAIM` está fora da autoridade.

## 2. Ordem de início

1. `CLAUDE.md`
2. [START_HERE.md](START_HERE.md)
3. [CURRENT_STATE.md](CURRENT_STATE.md)
4. [TASK_PROTOCOL.md](TASK_PROTOCOL.md)
5. [ROUTER.md](ROUTER.md)
6. gerar [TASK_CARD](templates/TASK_CARD.md)
7. carregar rotas/módulos/contratos/referências mínimos.

## 3. Evidência

L1 standard/documentação normativa/oficial aplicável → L2 scientific contract aprovado → L3 specification/invariant test aprovado → L4 implementação/docs atuais → L5 characterization → L6 inferência. Nível inferior não sobrescreve superior. Nunca converter `OBSERVED_BEHAVIOR` em `SCIENTIFIC_CONTRACT`. Veja [EVIDENCE_HIERARCHY.md](EVIDENCE_HIERARCHY.md).

## 4. Routing condensado

- DICOM/fase/slice → DICOM + DEID + GEOMETRY.
- origin/spacing/direction/LPS/RAS → GEOMETRY; incluir RESAMPLING/REGISTRATION/SEGMENTATION/3D conforme fluxo.
- mask/model/postprocess → SEGMENTATION + VOLUME + 3D.
- panels/pixels/channels → PANELS + EMBEDDINGS/MODEL + scientific regression.
- embedding/cache/revision → EMBEDDINGS + MODEL_LOADING + CACHE + PROVENANCE.
- prediction/folds/threshold/metrics → ML + CV + METRICS.
- candidate/ROI/subtype → LOCALIZATION/SUBTYPING + ML/GEOMETRY.
- mesh/viewer/XR → 3D + GEOMETRY + VOLUME + FRONTEND/WEBXR.
- job/perf/OOM → ORCHESTRATION + MEMORY/CONCURRENCY + CACHE.
- dead/duplicate/refactor → DEPENDENCIES + TESTS + every semantic route crossed.

Use o [router completo](ROUTER.md), que contém paths reais e expansões transitivas.

## 5. Autoridade

- LOW: após baseline/testes, investigar/testar/modificar.
- MEDIUM: investigar/testar/propor patch; aplicar cautelosamente somente em escopo autorizado; promover se científico.
- HIGH: investigar/reproduzir/testar/propor; nenhuma mudança semântica sem human gate.
- OUT_OF_AUTHORITY: parar e pedir decisão qualificada.

Human gates HG-01–HG-12 estão em [HUMAN_GATES.md](HUMAN_GATES.md). Scientific/geometric possibilities exigem consultar [SCIENTIFIC_CONTRACTS.yaml](SCIENTIFIC_CONTRACTS.yaml).

## 6. Contratos centrais

- ARRAY != medical image geometry; origin/spacing/direction/affine/convention/reference grid importam.
- DICOM não mistura séries e deve ordenar/verificar por geometria física; phase/derived policy é HIGH.
- Labels discretos não usam interpolação contínua sem contrato; máscaras e imagens quantitativas compartilham espaço físico.
- Cache/artefato depende de input+model revision+preprocessing+config+pipeline+artifact hash e publicação atômica.
- Patient/group não cruza folds; learned transforms/tuning/threshold respeitam inner/outer; uma OOF por unidade.
- Falha/denominador/metric/threshold são scientific contracts, não atalhos de implementação.
- Volume autoritativo vem de voxels da máscara × spacing; malha/LOD é derivada.
- Localização automática é candidato não confirmado e pós-inferência.

Veja [CONTRACTS.md](CONTRACTS.md) e o registry YAML.

## 7. Sistema real

CLI `digital_twin.py` → `Engine` → sete stages. Webapp multifásico resolve DICOM, harmoniza para venosa, segmenta, gera panels, classifica, opcionalmente localiza candidato, finaliza artifacts/volume e entrega viewer/WebXR. Runtime importa partes de `dtwin/learning` e `dtwin/benchmark`; não remova namespaces em bloco. Mapa completo: [SYSTEM_MAP.md](SYSTEM_MAP.md), [DEPENDENCY_MAP.md](DEPENDENCY_MAP.md), [modules/INDEX.md](modules/INDEX.md).

## 8. Test protocol

Baseline primeiro. Depois characterization explícita, contract/invariant/negative/property, integration real, scientific/geometric regression, branch coverage, selective mutation/fault/static. Coverage/test count isolados não provam contrato. Veja [TEST_STRATEGY.md](TEST_STRATEGY.md) e [TOOLING.md](TOOLING.md).

## 9. Plano longo

Phase 00 Freeze → 01 Cartography → 02 Contracts → 03 Characterization → 04 Invariants → 05 Integration → 06 Scientific regression → 07 Adversarial → 08 Low-risk refactor → 09 High-risk review → 10 Consolidation. Estado persiste em [LONG_PLAN.md](LONG_PLAN.md) e [CURRENT_STATE.md](CURRENT_STATE.md).

## 10. Sessão e evidência

Ao iniciar: conferir commit/dirty/state/task/router/blockers. Ao terminar: pacote de evidências, testes/riscos/gates, current state e handoff. Schema completo em [EVIDENCE_PACKAGE_SCHEMA.md](EVIDENCE_PACKAGE_SCHEMA.md); protocolo em [SESSION_PROTOCOL.md](SESSION_PROTOCOL.md).

## 11. Stop

Conflito de fonte, contrato desconhecido, geometria/label ambíguos, leakage possível, mudança de threshold/denominator/cohort, PHI, baseline irreproduzível, HIGH sem aprovação, claim clínico, dado ausente ou resultado irreproduzível → [STOP_REPORT](templates/STOP_REPORT.md). Não contorne silenciosamente. Veja [STOP_CONDITIONS.md](STOP_CONDITIONS.md).

## 12. Referências

Use [references/INDEX.md](references/INDEX.md), priorizando DICOM standard, docs oficiais ITK/SimpleITK/NiBabel/PyTorch/sklearn/pytest e papers metodológicos. “Fable 5” está `NOT_VERIFIED`; o pack usa apenas comportamento oficial documentado do Claude Code e permanece model-agnostic.

