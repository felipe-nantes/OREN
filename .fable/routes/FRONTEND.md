# FRONTEND

TRIGGERS: FastAPI endpoint, upload, status, webapp UI, viewer controls, approval.  
REAL_PATHS: `webapp/server.py`, `webapp/static/`, `viewer/index.html`, `viewer/app.js`, `viewer/argos-viewer.css`.  
MODULES: WEBAPP_API_ORCHESTRATION, FRONTEND_DESKTOP, VIEWER_ARTIFACTS_3D.  
MINIMUM_CONTEXT: PIPELINE, SECURITY, PRIVACY; WEBXR/3D when relevant.  
REFERENCES: security/privacy/testing.  
CONTRACTS: authorized config/path only; artifact allowlist/hash; explicit nonclinical state; review not fabricated; accessible errors.  
RISKS: MEDIUM; HIGH if clinical/scientific display/decision semantics.  
AUTHORITY: UI-only change if output semantics preserved; scientific labels/workflow require gates.  
REQUIRED_TESTS: API schema/auth/path/payload, restart/tamper, browser flows, accessibility/legibility, desktop regression.  
HUMAN_GATE: semantic route; HG-11/12 when data/claim.  
STOP_CONDITIONS: endpoint exposure/auth unknown, hidden data, UI alters measurement/decision.  
EXPECTED_EVIDENCE: endpoint contract, screenshots plus DOM/API tests, asset hashes and desktop/XR behavior.

