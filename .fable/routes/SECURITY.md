# SECURITY

TRIGGERS: auth/token/cert/TLS, upload, path traversal, command injection, dependency, network exposure.  
REAL_PATHS: `webapp/server.py`, `viewer/xr.js`, Quest scripts, `compose*.yaml`, `docker/nginx.conf`, dependency files.  
MODULES: WEBAPP_API_ORCHESTRATION, WEBXR_QUEST, DOCKER_LAUNCHERS.  
MINIMUM_CONTEXT: PRIVACY, FRONTEND/DOCKER, relevant API/artifact route.  
REFERENCES: security/privacy, Python supply chain.  
CONTRACTS: least privilege; secrets outside repo; allowlisted paths/assets/configs; bounded input; short XR sessions; fail closed.  
RISKS: MEDIUM/HIGH.  
AUTHORITY: inspect/test/propose; external exposure/auth policy needs operator.  
REQUIRED_TESTS: traversal/symlink, oversized/malformed upload, token expiry/replay/role, cert/key permissions, subprocess args, dependency audit.  
HUMAN_GATE: HG-11; HG-12 for safety claim.  
STOP_CONDITIONS: credential/PHI encountered, live external target without scope, destructive security test.  
EXPECTED_EVIDENCE: threat model, sanitized reproduction, affected boundary, mitigation options and regression tests.

