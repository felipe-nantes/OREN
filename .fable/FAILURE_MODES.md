# Modos de falha

| ID | Área | Falha | Silenciosa? | Consequência | Rota/ação |
|---|---|---|---|---|---|
| FM-DICOM-01 | DICOM | seleção de série/fase derivada ou errada | sim | input semântico errado | DICOM + HG-02 |
| FM-DICOM-02 | DICOM | ordem por filename/InstanceNumber | sim | volume invertido/desordenado | DICOM/GEOMETRY |
| FM-PHI-01 | privacidade | PHI em tag privada/overlay/pixel/log | sim | exposição | DEIDENTIFICATION/PRIVACY, STOP |
| FM-GEO-01 | geometria | perda de origin/spacing/direction | sim | medida/malha errada | GEOMETRY + HG-03 |
| FM-GEO-02 | resampling | interpolação linear de label | sim | classes/volume alterados | RESAMPLING + HG-04 |
| FM-REG-01 | registration | transform direction invertida | sim | desalinhamento plausível | REGISTRATION |
| FM-SEG-01 | segmentação | máscara vazia/implausível aceita | às vezes | pipeline inválido | SEGMENTATION fail-closed |
| FM-SEG-02 | segmentação | cleanup remove anatomia relevante | sim | volume/forma alterados | HG-05/HG-10 |
| FM-PANEL-01 | painéis | crop omite fígado/lesão | sim | representação incompleta | PANELS/HG-09 |
| FM-EMB-01 | embeddings | cache de outra revisão/input | sim | score incorreto | EMBEDDINGS+CACHE |
| FM-ML-01 | ML | patient/group leakage | sim | estimativa inflada | STOP + HG-07 |
| FM-ML-02 | ML | scaler/threshold aprende no outer/test | sim | viés | CROSS_VALIDATION |
| FM-MET-01 | métricas | falha/inconclusivo excluído | sim | resultado inflado | HG-08 |
| FM-ART-01 | artefato | parcial/truncado tratado como concluído | sim | reuse corrupto | CACHE_ARTIFACTS |
| FM-3D-01 | malha | spacing/unidade ignorados | sim | dimensões/volume errado | RECONSTRUCTION_3D |
| FM-3D-02 | malha | visual realista interpretado como verdade | humano | claim indevido | HG-12 |
| FM-XR-01 | WebXR | LOD/clipping esconde estrutura | sim | inspeção enganosa | FRONTEND/3D |
| FM-CONC-01 | concorrência | dois workers escrevem mesmo caso | sim | artefato misto | PERFORMANCE/CACHE |
| FM-REPRO-01 | GPU | resultado varia sem tolerância registrada | sim | irreprodutibilidade | REPRODUCIBILITY |
| FM-DOC-01 | docs | documentação antiga vence código/contrato | sim | decisão incorreta | evidência L1–L6 |

Toda ocorrência deve registrar input minimizado, hash, etapa, erro, denominador e se houve publicação parcial. Nunca converter falha técnica em classe clínica.

