# WEBXR

TRIGGERS: Meta Quest, XR/MR, hands/pinch, tablet, calibration, LOD, XR token/session.  
REAL_PATHS: `viewer/xr.js`, `viewer/app.js`, `dtwin/viewer_xr.py`, `webapp/server.py`, `webapp/static/quest/`, Quest launch/certificate scripts.  
MODULES: WEBXR_QUEST, FRONTEND_DESKTOP, VIEWER_ARTIFACTS_3D, DOCKER_LAUNCHERS.  
MINIMUM_CONTEXT: FRONTEND, RECONSTRUCTION_3D, PERFORMANCE, SECURITY.  
REFERENCES: WebXR/browser primary docs when task requires; mesh/security cards.  
CONTRACTS: desktop preserved; role/token bounded; no asset without allowlist/hash; XR LOD not quantitative source; review auditable.  
RISKS: MEDIUM visual/performance, HIGH measurement/clipping/approval semantics.  
AUTHORITY: UI/performance changes after physical/browser baseline; quantitative behavior gated.  
REQUIRED_TESTS: feature detection, session lifecycle, controller/hands, calibration, visibility/clipping, LOD, reconnect/token expiry, Quest physical gate.  
HUMAN_GATE: HG-10 for measurement/geometry; HG-11/12.  
STOP_CONDITIONS: no physical device for claimed validation, asset disappearance, insecure exposure.  
EXPECTED_EVIDENCE: device/browser/build, FPS/memory, task checklist, screenshots/video supplemental, API/event logs sanitized.

