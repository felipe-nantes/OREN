ID: REF-GEOMETRY-001

TITLE: Physical-space contracts for medical images

SOURCE:
- ITK Software Guide, including registration and resampling chapters.
- SimpleITK Fundamental Concepts and Registration Overview.
- NiBabel coordinate-system and orientation documentation.
- DICOM PS3.3 Image Plane Module.

URL:
- https://itk.org/ITKSoftwareGuide/html/
- https://itk.org/ITKSoftwareGuide/html/Book2/ITKSoftwareGuide-Book2ch2.html
- https://itk.org/ITKSoftwareGuide/html/Book2/ITKSoftwareGuide-Book2ch3.html
- https://simpleitk.readthedocs.io/en/release/fundamentalConcepts.html
- https://simpleitk.readthedocs.io/en/v2.3.0/registrationOverview.html
- https://nipy.org/nibabel/coordinate_systems.html
- https://nipy.org/nibabel/reference/nibabel.orientations.html
- https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_C.7.6.2.html

AUTHORITY_LEVEL:
- `NORMATIVE_STANDARD` para a geometria definida pelo DICOM.
- `OFFICIAL_PRIMARY_DOCUMENTATION` para a semântica de ITK, SimpleITK e NiBabel.

VERSION_OR_DATE: Documentação online sem versão única congelada neste cartão. A versão das bibliotecas e a data de consulta devem constar no pacote de evidências.

TOPICS:
- origin, spacing, direction e affine;
- coordenadas voxel, físicas e de scanner;
- DICOM LPS+ e NiBabel RAS+;
- reference grid;
- fixed/moving e direção de transform;
- registration e resampling;
- interpolação de imagem contínua e label map;
- landmarks e phantoms geométricos.

AFFECTED_ROUTES:
- DICOM -> volume;
- volume -> harmonização;
- fixed/moving -> registration;
- imagem/máscara -> resampling;
- máscara -> métrica voxel a voxel;
- volume/máscara -> malha 3D.

KEY_RULES:
- Um array não contém toda a semântica espacial; preservar e rastrear `origin`, `spacing`, `direction`/affine e convenção de coordenadas.
- Toda mudança de grade deve registrar a imagem ou os valores que forneceram size, origin, spacing e direction.
- Nomear e testar a direção de cada transformação; não assumir silenciosamente fixed->moving ou moving->fixed.
- Testar conversões LPS+ <-> RAS+ com landmarks assimétricos, flips e permutações de eixos.
- O round-trip ponto físico -> índice contínuo -> ponto físico deve fechar dentro de tolerância justificada.
- Reamostragem identidade para a própria grade deve ser aproximadamente identidade.
- Label maps discretos não podem adquirir classes novas; usar interpolação apropriada a labels, normalmente nearest-neighbor.
- Registration deve registrar fixed, moving, transform, métrica, optimizer, parâmetros, referência e critérios de falha.
- Avaliar registration com landmarks/propriedades geométricas e métricas complementares, não com um único score universal.
- Phantoms devem ser assimétricos e cobrir identidade, translação, rotação, permutação, inversão, anisotropia, crop e padding.
- Comparações voxel a voxel exigem imagem e máscara no mesmo espaço físico, não apenas shapes iguais.

WHEN_FABLE_SHOULD_READ:
- Antes de qualquer alteração em orientação, affine, crop, padding, registration, resampling ou interpolação.
- Ao diagnosticar volume preto, flip, escala incorreta, drift físico ou desalinhamento de máscara.
- Antes de mudar de biblioteca de imagem médica.
- Antes de declarar preservação geométrica em um patch.

LIMITATIONS:
- As fontes definem semântica e APIs, mas não escolhem o método científico do ARGOS/OREN.
- Tolerâncias, referência anatômica e política de falha são contratos do projeto e exigem aprovação.
- Resultado visual plausível não prova correspondência física nem validade anatômica/clinicamente verdadeira.
