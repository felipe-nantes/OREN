ID: REF-PYTORCH-001

TITLE: PyTorch reproducibility and numerical regression

SOURCE:
- PyTorch official Reproducibility documentation.

URL:
- https://docs.pytorch.org/docs/stable/notes/randomness.html

AUTHORITY_LEVEL: `OFFICIAL_PRIMARY_DOCUMENTATION` para garantias e limites declarados pelo PyTorch.

VERSION_OR_DATE: Documentação `stable`; a versão instalada, CUDA/cuDNN, drivers, hardware e data de consulta devem ser registrados. Nenhuma versão é presumida.

TOPICS:
- seeds e fontes de aleatoriedade;
- algoritmos determinísticos;
- CPU/GPU e CUDA/cuDNN;
- diferenças entre releases e plataformas;
- tolerâncias de regressão numérica;
- custo de determinismo.

AFFECTED_ROUTES:
- volume/painel -> inferência;
- modelo -> embedding;
- modelo -> segmentação;
- CPU/GPU -> scientific regression;
- artefato -> provenance.

KEY_RULES:
- Não exigir igualdade bitwise entre releases, plataformas ou CPU/GPU sem contrato explícito e demonstrado.
- Registrar versão do PyTorch, dispositivo, hardware, CUDA/cuDNN quando aplicável, seeds e flags determinísticas.
- Definir separadamente regressões de lógica e regressões numéricas.
- Justificar `atol`/`rtol` por dtype, operação e impacto; não ampliar tolerância apenas para fazer o teste passar.
- Determinismo pode reduzir performance; medir correção e benchmark separadamente.
- Uma seed não elimina todas as fontes de não determinismo.
- Mudança de revisão de modelo, preprocessing ou ambiente deve participar da identidade/proveniência do artefato e da validade do cache.

WHEN_FABLE_SHOULD_READ:
- Antes de alterar inferência, dispositivo, precisão, seeds ou flags determinísticas.
- Ao criar regressões que atravessam CPU/GPU ou ambientes diferentes.
- Ao diagnosticar flakiness numérica ou mudança de embedding/segmentação.

LIMITATIONS:
- A fonte não promete reprodutibilidade absoluta.
- Este cartão não define precisão clinicamente aceitável, revisão de modelo ou tolerância científica.
- Regras de `eval`, gradients, autocast e serialização devem ser confirmadas nas páginas oficiais correspondentes à versão instalada quando afetadas.
