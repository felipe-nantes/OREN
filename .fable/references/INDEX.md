# Fable Engineering Reference Index

Este diretório é o corpus técnico mínimo para auditoria e engenharia assistida do ARGOS/OREN. Os cartões não substituem a leitura da fonte primária, não criam validade clínica e não autorizam alteração de contrato científico.

## Como usar

1. Identifique a rota afetada e leia os cartões indicados abaixo.
2. Registre a fonte e o contrato aplicável no pacote de evidências do patch.
3. Separe comportamento observado, contrato de software, contrato geométrico, contrato científico, política de domínio e alegação clínica.
4. Quando uma fonte estiver marcada como `current` ou `stable`, registre no patch a data de consulta e a versão efetivamente instalada; este índice não inventa nem congela versões.
5. Em caso de conflito, siga [EVIDENCE_HIERARCHY.md](../EVIDENCE_HIERARCHY.md) e solicite decisão humana quando necessário.

## Níveis de autoridade

- `NORMATIVE_STANDARD`: padrão formal aplicável, como DICOM.
- `OFFICIAL_PRIMARY_DOCUMENTATION`: documentação oficial da linguagem, biblioteca ou plataforma; autoritativa para sua API e semântica declarada.
- `PEER_REVIEWED_METHOD`: artigo científico/metodológico; fundamenta critérios, mas não cria automaticamente requisito de produto.
- `PRIMARY_RESEARCH_PREPRINT`: evidência primária ainda não equivalente a norma ou validação do produto.
- `PROJECT_SCIENTIFIC_CONTRACT`: decisão interna somente após aprovação do responsável científico.
- `ENGINEERING_RECOMMENDATION`: prática recomendada que deve ser justificada e testada.

## Cartões

| Cartão | Ler quando |
|---|---|
| [DICOM.md](DICOM.md) | ingestão, seleção/ordenação de séries, pixel data, Transfer Syntax e desidentificação |
| [MEDICAL_GEOMETRY.md](MEDICAL_GEOMETRY.md) | origin, spacing, direction/affine, LPS/RAS, registration e resampling |
| [PYTHON.md](PYTHON.md) | runtime Python, tipos, I/O, serialização e comportamento portável |
| [PYTORCH.md](PYTORCH.md) | inferência, CPU/GPU, seeds, determinismo e regressão numérica |
| [SKLEARN.md](SKLEARN.md) | pipelines, group splits, nested CV e prevenção de leakage |
| [TESTING.md](TESTING.md) | characterization, contratos, propriedades, integração, coverage, mutação e benchmark |
| [STATISTICS.md](STATISTICS.md) | métricas, denominadores, seleção de modelo e interpretação estatística |
| [REPRODUCIBILITY.md](REPRODUCIBILITY.md) | manifests, versões, seeds, tolerâncias, cache e artefatos |
| [SECURITY_PRIVACY.md](SECURITY_PRIVACY.md) | PHI, DICOM desidentificado, segredos e dependências |
| [MESH_3D.md](MESH_3D.md) | marching cubes, escala física, topologia, volume e cleanup |
| [FABLE_PLATFORM.md](FABLE_PLATFORM.md) | uso verificável do Claude Code, contexto por `@path` e limites da plataforma |

## Roteamento rápido

- `DICOM -> volume`: DICOM + MEDICAL_GEOMETRY + TESTING.
- `volume -> harmonização/registration`: MEDICAL_GEOMETRY + REPRODUCIBILITY + TESTING.
- `máscara -> métricas`: MEDICAL_GEOMETRY + STATISTICS + TESTING.
- `máscara -> malha 3D`: MEDICAL_GEOMETRY + MESH_3D + REPRODUCIBILITY.
- `modelo -> inferência/embedding`: PYTORCH + REPRODUCIBILITY + TESTING.
- `coorte -> avaliação`: SKLEARN + STATISTICS + REPRODUCIBILITY.
- `DICOM/artefato -> agente`: SECURITY_PRIVACY + FABLE_PLATFORM.

## Regra de integridade

Os cartões resumem fontes. Sempre que uma decisão depender de detalhe de tag, transformação, API, métrica ou segurança, abra a URL primária e cite a seção consultada. Uma saída visualmente plausível, um teste verde ou coverage alto não constituem demonstração de correção científica ou validade clínica.
