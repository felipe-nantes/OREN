ID: REF-SECURITY-PRIVACY-001

TITLE: DICOM confidentiality, PHI boundaries, secrets, and dependency audit

SOURCE:
- DICOM PS3.15, Security and System Management Profiles.
- pydicom official documentation.
- pip-audit project maintained under PyPA.

URL:
- https://dicom.nema.org/medical/dicom/current/output/html/part15.html
- https://pydicom.github.io/pydicom/stable/
- https://github.com/pypa/pip-audit

AUTHORITY_LEVEL:
- `NORMATIVE_STANDARD` para perfis DICOM de confidencialidade.
- `OFFICIAL_PRIMARY_DOCUMENTATION` para pydicom e pip-audit.

VERSION_OR_DATE: DICOM é referenciado pela edição online `current`; versões instaladas de pydicom e pip-audit não são presumidas e devem ser registradas.

TOPICS:
- PHI em metadados e pixels;
- UIDs, datas e private elements;
- overlays e gráficos;
- dados sintéticos/desidentificados;
- licença e redistribuição;
- segredos e credenciais;
- vulnerabilidades conhecidas de dependências.

AFFECTED_ROUTES:
- DICOM clínico -> desidentificação -> fixture/agente;
- fixture -> CI;
- logs/relatórios -> armazenamento;
- dependências -> build/deploy;
- contexto do agente -> revisão.

KEY_RULES:
- Não solicitar, copiar ou expor PHI desnecessariamente.
- Preferir metadados e phantoms sintéticos; usar casos reais apenas na integração quando indispensáveis e autorizados.
- `PatientName` removido ou `remove_private_tags()` executado não demonstram desidentificação integral.
- Verificar atributos identificáveis, UIDs, datas, private elements, overlays/graphics e pixel data conforme o perfil aplicável.
- Preservar relações necessárias sem reutilizar identificadores originais quando a política exigir substituição consistente.
- Cada fixture real deve registrar licença, redistribuição permitida, desidentificação, hash e presença de texto em pixels.
- Nunca incluir tokens, senhas, chaves, credenciais, dumps de ambiente ou segredos em prompts, fixtures, logs ou relatórios.
- `pip-audit` detecta vulnerabilidades conhecidas em dependências; não substitui revisão de código, threat modeling ou hardening.
- Falha de desidentificação ou integridade deve bloquear a entrada no corpus do agente.

WHEN_FABLE_SHOULD_READ:
- Antes de ler, anexar, versionar ou enviar DICOM/artefato a um agente.
- Antes de criar fixtures reais ou logs de casos.
- Ao alterar desidentificação, UIDs, exportação, cache ou telemetria.
- Antes de atualizar dependências ou interpretar resultado de `pip-audit`.

LIMITATIONS:
- Este cartão não é avaliação LGPD/HIPAA, threat model completo nem certificação de segurança.
- O perfil DICOM adequado e as obrigações legais dependem do uso e da instituição.
- Análise automática não detecta toda PHI visual nem toda vulnerabilidade.
