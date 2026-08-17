# MODULE_ID: WEBXR_QUEST

MODULE_NAME: WebXR/Meta Quest, sessões e LODs

## REAL_PATHS

- viewer/xr.js
- dtwin/viewer_xr.py
- webapp/static/quest/index.html
- webapp/static/quest/setup/index.html
- tools/create_quest_access_page.py
- tools/create_quest_certificate.py
- tools/serve_quest_certificate.py
- tools/start_oren_quest_dynamic.ps1
- tests/test_viewer_xr.py
- tests/test_quest_certificate_server.py

STATUS: PRODUCTION

## RESPONSIBILITY

Gerar assets dentro do orçamento XR, renderizar cena imersiva, criar/consultar sessões Quest, registrar eventos/approval e fornecer acesso TLS/LAN.

## ENTRYPOINTS

- build_xr_render_asset
- xr_triangle_budget
- viewer/xr.js
- POST /api/jobs/{job_id}/xr-session
- GET /api/jobs/{job_id}/xr-session/{token}
- ferramentas Quest

## PUBLIC INTERFACES

Manifesto XR/LOD; endpoints /api/quest e /api/jobs/.../xr-session; controles e eventos do viewer XR.

## INPUTS

STL/source metrics; material/triangle budget; viewer manifest; token/session; eventos de controller/headset.

## OUTPUTS

STL XR otimizado, hashes/métricas, cena WebXR, session/client events e approval.

## SIDE_EFFECTS

Decima/grava malhas; solicita sessão immersive-vr; acessa rede/TLS; persiste eventos/aprovação; configura certificado/firewall por ferramentas.

## UPSTREAM

VIEWER_ARTIFACTS_3D; VOLUMETRY; WEBAPP_API_ORCHESTRATION; DOCKER_LAUNCHERS.

## DOWNSTREAM

Meta Quest/browser WebXR; operador/revisor.

## ARTIFACTS_READ

Viewer manifest; STL/metrics; material pack; session token.

## ARTIFACTS_WRITTEN

LOD STL; metadados XR; eventos e approval de sessão; certificados locais quando scripts são usados.

## DEPENDENCIES

PyVista; Three.js/WebXR; FastAPI endpoints; TLS/browser/headset.

## OBSERVED_BEHAVIOR

Seleciona budget por material e reutiliza source quando já atende ao alvo; caso contrário decima e mede novamente. O papel clinician é informado pelo request, não autenticado por identidade externa.

## SOFTWARE_CONTRACTS

Token deve ser imprevisível, scoped e expirar; assets devem corresponder a hashes; eventos devem referenciar job/session; certificado/chave não entram no repositório.

## GEOMETRIC_CONTRACTS

LOD deve preservar escala/unidade/orientação e manter erro quantitativo registrado; interação não deve alterar a geometria-fonte.

## SCIENTIFIC_CONTRACTS

Triangle budget/decimation e affordances de medição podem afetar percepção; não representam verdade quantitativa sem contrato.

## DOMAIN_POLICIES

Sessão XR e approval não equivalem a autenticação clínica; acesso LAN deve ser minimizado e auditado.

## KNOWN_FAILURE_MODES

WebXR indisponível; certificado não confiável; token inválido; GPU móvel insuficiente; LOD falhar; asset ausente.

## SILENT_FAILURE_MODES

Escala/unidade errada; papel autoatribuído; token vazado; LOD visualmente aceitável perder estrutura; approval sem identidade.

## RISK_LEVEL

HIGH_SCIENTIFIC_GEOMETRIC para LOD/medição; MEDIUM para transporte; OUT_OF_AUTHORITY para claim clínico.

## HUMAN_GATES

HG-10 para decimation/medição; HG-11 para rede/sessão; HG-12 para uso/claim clínico.

## EXISTING_TESTS

tests/test_viewer_xr.py; tests/test_quest_certificate_server.py; tests/test_quest_dynamic_certificate.py; tests/test_quest_dynamic_launcher.py; tests/test_quest_http_launcher.py.

## TEST_GAPS

Headset E2E; auth/expiry/replay; perda de rede; cross-device scale; performance real; tolerância geométrica do LOD; security review.

## REQUIRED_TEST_TYPES

CONTRACT; NEGATIVE; INTEGRATION; E2E; GEOMETRIC_REGRESSION; PERFORMANCE; SECURITY; FAULT_INJECTION.

## RELEVANT_REFERENCES

.fable/HUMAN_GATES.md; .fable/references/MESH_3D.md; .fable/references/SECURITY_PRIVACY.md; docs/229_DOCKER_ARGOS_END_TO_END.md; docs/239_ACESSO_META_QUEST_IP_DINAMICO.md.

## OPEN_QUESTIONS

Qual provedor de identidade e expiração de sessão? Quais budgets/tolerâncias estão aprovados por dispositivo? Eventos XR contêm dados sensíveis?

## DO_NOT_CHANGE_AUTONOMOUSLY

Não alterar escala, unidade, budgets, decimation, tokens/roles, aprovação, certificados ou exposição de rede sem regressão geométrica, teste em dispositivo e revisão de segurança.

