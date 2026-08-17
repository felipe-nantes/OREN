ID: REF-DICOM-001

TITLE: DICOM ingestion, geometry, encoding, and confidentiality

SOURCE:
- DICOM Standard portal, NEMA/MITA.
- DICOM PS3.3, Image Plane Module, Section C.7.6.2.
- DICOM PS3.5, Data Structures and Encoding.
- DICOM PS3.15, Security and System Management Profiles.
- pydicom official documentation and example datasets.

URL:
- https://www.dicomstandard.org/current
- https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_C.7.6.2.html
- https://dicom.nema.org/medical/dicom/current/output/html/part05.html
- https://dicom.nema.org/medical/dicom/current/output/html/part15.html
- https://pydicom.github.io/pydicom/stable/
- https://pydicom.github.io/pydicom/stable/reference/examples.html

AUTHORITY_LEVEL:
- `NORMATIVE_STANDARD` para as partes DICOM.
- `OFFICIAL_PRIMARY_DOCUMENTATION` para a API e os datasets de exemplo do pydicom.

VERSION_OR_DATE: O padrão é referenciado pela edição online `current` e o pydicom pela documentação `stable`; nenhuma revisão ou versão instalada é presumida. O pacote de evidências deve registrar a edição e a versão efetivamente consultadas.

TOPICS:
- estudo, série e instância;
- geometria do plano de imagem;
- Transfer Syntax, VR, byte ordering e Pixel Data;
- ordenação espacial de slices;
- séries derivadas e objetos multiframe;
- confidencialidade e desidentificação;
- fixtures sintéticas e oficiais.

AFFECTED_ROUTES:
- DICOM -> descoberta de estudos/séries/instâncias;
- série -> seleção e ordenação;
- instâncias -> volume físico;
- DICOM -> desidentificação -> fixture;
- DICOM -> decoder de Pixel Data.

KEY_RULES:
- Não misturar instâncias de `SeriesInstanceUID` diferentes sem contrato explícito.
- Não usar nome de arquivo ou `InstanceNumber` como oráculo de ordem espacial.
- Interpretar `ImagePositionPatient`, `ImageOrientationPatient` e `PixelSpacing` conforme o Image Plane Module.
- Validar cosenos diretores finitos, aproximadamente unitários e ortogonais dentro de tolerância documentada; derivar e verificar a normal do plano.
- Tornar explícita a política para MPR, MIP, subtração e outras séries derivadas.
- Tratar Transfer Syntax e Pixel Data segundo PS3.5; ausência de decoder deve produzir falha rastreável, não dados fabricados.
- Testar tags ausentes, UIDs duplicados, slices duplicados, spacing irregular, ordem permutada, arquivo truncado e multiframe quando suportado.
- Remover private tags não equivale a cumprir um perfil de desidentificação. UIDs, datas, atributos, overlays, gráficos e pixels também podem conter informação identificável.
- Fixtures reais devem ter licença, permissão de redistribuição, hash, política de desidentificação e propósito registrados.
- Para semântica DICOM, o padrão prevalece sobre comportamento casual de um reader ou exemplos de blog.

WHEN_FABLE_SHOULD_READ:
- Antes de alterar parsing, seleção, exclusão ou ordenação de séries.
- Antes de mudar codecs, escrita/leitura DICOM ou construção de volume.
- Antes de criar fixtures com DICOM clínico ou de teste.
- Sempre que um patch tocar atributos DICOM, UIDs, Pixel Data ou desidentificação.

LIMITATIONS:
- Este cartão não demonstra conformidade DICOM integral nem cobre todos os SOP Classes e IODs.
- A documentação pydicom descreve a biblioteca, mas não substitui o padrão normativo.
- Regras específicas de modalidade, fabricante e sequência exigem contrato de projeto e fixtures representativas.
- Nenhuma regra deste cartão autoriza uso de PHI ou cria alegação clínica.
