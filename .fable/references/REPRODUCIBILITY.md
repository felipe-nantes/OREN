ID: REF-REPRODUCIBILITY-001

TITLE: Reproducible scientific software and traceable artifacts

SOURCE:
- McCormick et al., ITK: enabling reproducible research and open science.
- PyTorch official Reproducibility documentation.
- ITK Software Guide.

URL:
- https://www.frontiersin.org/journals/neuroinformatics/articles/10.3389/fninf.2014.00013/full
- https://docs.pytorch.org/docs/stable/notes/randomness.html
- https://itk.org/ITKSoftwareGuide/html/

AUTHORITY_LEVEL:
- `PEER_REVIEWED_METHOD` para o artigo de reprodutibilidade ITK.
- `OFFICIAL_PRIMARY_DOCUMENTATION` para PyTorch e ITK.

VERSION_OR_DATE: O artigo ITK é identificado por DOI/URL; as documentações online não são congeladas. Registrar versões reais, ambiente e data de consulta em cada evidência.

TOPICS:
- código, dados, parâmetros e versões;
- seeds e tolerâncias;
- manifests e hashes;
- cache e artefatos;
- atomicidade, resume e idempotência;
- bundles reproduzíveis;
- scientific regression.

AFFECTED_ROUTES:
- input -> stage -> artifact;
- source/model/config -> cache key;
- pipeline interrompido -> resume;
- execução -> manifest;
- baseline -> scientific regression.

KEY_RULES:
- Tratar código, dados, configuração, parâmetros, ambiente e testes como partes do resultado científico.
- Cada estágio deve declarar inputs, outputs, versão, configuração, estado e falha.
- Registrar hashes e identidades de input, revisão de modelo/preprocessing, versão de código e ambiente.
- Cache só é reutilizável quando identidade, versão, configuração e integridade são compatíveis.
- Arquivo parcial, truncado ou corrompido nunca é artefato válido; escrita deve ser validada e, quando contratada, atômica.
- Resume não pode repetir silenciosamente efeitos já concluídos nem promover estado parcial a sucesso.
- Registrar seeds e tolerâncias, mas não prometer igualdade bitwise que a plataforma não garante.
- Preferir propriedades científicas estáveis e resultados interpretáveis a snapshots brutos gigantes.
- Fixtures e baselines devem ter licença, hash, versão, propósito e resultado esperado.
- Um bundle reproduzível deve permitir responder qual entrada, contrato, versão, parâmetro e patch produziram o resultado.

WHEN_FABLE_SHOULD_READ:
- Antes de alterar cache, persistência, manifests, resume ou execução de pipeline.
- Antes de atualizar modelo, preprocessing ou dependência numérica.
- Ao criar ou atualizar baseline de regressão científica.
- Quando um resultado não puder ser reproduzido em outro ambiente.

LIMITATIONS:
- Reprodutibilidade técnica não implica validade científica ou clínica.
- Determinismo absoluto pode ser impossível entre hardware/releases.
- Retenção, armazenamento e acesso a dados clínicos também dependem de política institucional e requisitos legais não definidos aqui.
