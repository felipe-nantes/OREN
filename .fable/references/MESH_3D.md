ID: REF-MESH-3D-001

TITLE: Physically scaled and auditable 3D meshes

SOURCE:
- scikit-image official `skimage.measure` documentation, including `marching_cubes`.
- Trimesh official documentation.
- Metrics Reloaded for problem-aware metric selection.

URL:
- https://scikit-image.org/docs/stable/api/skimage.measure.html
- https://trimesh.org/
- https://www.nature.com/articles/s41592-023-02151-z

AUTHORITY_LEVEL:
- `OFFICIAL_PRIMARY_DOCUMENTATION` para scikit-image e Trimesh.
- `PEER_REVIEWED_METHOD` para Metrics Reloaded.

VERSION_OR_DATE: Documentações online sem versão instalada presumida; o artigo é identificado por seu URL de publicação. Registrar versão de biblioteca e data de consulta no patch.

TOPICS:
- marching cubes e isosurface;
- spacing e unidades físicas;
- componentes conectados;
- Euler characteristic e watertightness;
- volume e área;
- faces degeneradas;
- cleanup e perda quantitativa;
- phantoms geométricos.

AFFECTED_ROUTES:
- máscara -> marching cubes -> malha;
- malha -> cleanup;
- malha -> visualizador/exportação;
- malha -> volume/topologia/auditoria.

KEY_RULES:
- Fornecer o spacing físico correto ao extrair a superfície; shape isolado não define escala.
- Registrar convenção de eixos, unidade e transform aplicada entre volume e malha.
- Medir componentes, Euler, watertightness, volume, área e faces degeneradas quando relevantes.
- Comparar métricas antes e depois de cleanup e registrar perda de volume/topologia.
- Validar com cubo, esfera e phantoms assimétricos de dimensões físicas conhecidas.
- Não introduzir `keep largest component`, smoothing, decimation ou hole filling como regra universal sem contrato científico.
- Uma malha bonita pode estar invertida, escalada ou quantitativamente errada; inspeção visual é complemento, não oráculo.
- Thresholds de cleanup com efeito quantitativo são de alto risco científico e exigem aprovação.

WHEN_FABLE_SHOULD_READ:
- Antes de alterar marching cubes, spacing, transform, cleanup, smoothing, decimation ou exportação.
- Ao investigar divergência de volume entre voxel mask e mesh.
- Antes de afirmar preservação topológica ou física.

LIMITATIONS:
- Watertightness e topologia correta não demonstram anatomia verdadeira ou validade clínica.
- Algoritmos e propriedades dependem da versão instalada e do contrato de unidade/orientação.
- Métricas de malha devem ser selecionadas conforme a pergunta; este cartão não define tolerâncias clínicas.
