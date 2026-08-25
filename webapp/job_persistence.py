"""Persistência e restauração de jobs concluídos (REF-03 seam 1).

Extraído de server.py sem mudança de comportamento. REGRA R2 do design:
config (WORKSPACE, DISCLAIMER), estado (_jobs, _lock) e símbolos que os
testes monkeypatcham (_model_done, _rgb_panel_files) são resolvidos via
`server.<nome>` EM TEMPO DE CHAMADA — nunca copiados para cá — para que
`monkeypatch.setattr(server, ...)` continue valendo. O import circular é
seguro: só o objeto módulo é capturado no import; atributos são lidos
depois da inicialização completa.
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from webapp import server


def _case_dir_for_job(job_id: str) -> Path:
    if not job_id or any(ch not in "0123456789abcdef" for ch in job_id.lower()):
        raise HTTPException(status_code=404, detail="Job nao encontrado.")
    return (server.WORKSPACE / job_id / "case").resolve()


def _completed_job_state_path(job_id: str) -> Path:
    return server._case_dir_for_job(job_id) / "outputs" / "webapp_job_state.json"


def _persist_completed_job_state(job_id: str, job: dict[str, Any]) -> Path:
    """Persist a completed webapp state atomically beside its artifacts."""
    if job.get("state") != "done":
        raise ValueError("only completed jobs may be persisted")
    allowed = {
        "state", "step", "progress", "analysis_scenario", "enhanced_3d",
        "result", "approval", "operational_timing", "operational_timing_artifact",
        "viewer_error",
    }
    payload = {key: job.get(key) for key in allowed if key in job}
    payload.update(
        schema="oren-webapp-completed-job-v1",
        job_id=job_id,
        persisted_at=datetime.now(timezone.utc).isoformat(),
    )
    path = _completed_job_state_path(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        for attempt in range(5):
            try:
                temporary.replace(path)
                break
            except PermissionError:
                # TD-015: replaces concorrentes do mesmo destino falham com
                # WinError 5 no Windows mesmo com o destino integro.
                if attempt == 4:
                    raise
                time.sleep(0.05 * (attempt + 1))
    finally:
        temporary.unlink(missing_ok=True)
    return path


def _legacy_completed_job_from_artifacts(job_id: str) -> dict[str, Any] | None:
    """Migrate a pre-persistence completed job without fabricating analysis data."""
    case_dir = server._case_dir_for_job(job_id)
    if not server._model_done(case_dir):
        return None
    manifest_path = case_dir / "outputs" / "viewer_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    candidate = manifest.get("candidate_region") or {}
    request = candidate.get("request") or {}
    raw_prediction = str(request.get("prediction") or "INCONCLUSIVE").upper()
    prediction = {
        "POSITIVE": "POSITIVA",
        "NEGATIVE": "NEGATIVA",
        "INCONCLUSIVE": "INCONCLUSIVA",
    }.get(raw_prediction, raw_prediction)
    approval_path = case_dir / "outputs" / "approval.json"
    approval: dict[str, Any] = {"status": "pending"}
    if approval_path.is_file():
        try:
            loaded = json.loads(approval_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                approval = loaded
        except (OSError, json.JSONDecodeError):
            pass
    result = {
        "status": "concluido",
        "analysis_scenario": "recovered_legacy_completed_job",
        "prediction": prediction,
        "visual_score": request.get("visual_score"),
        "visual_threshold": request.get("visual_threshold"),
        "panel_count": len(server._rgb_panel_files(job_id)),
        "candidate_localization": candidate or None,
        "viewer_ready": True,
        "viewer_url": f"/viewer/index.html?case=/api/jobs/{job_id}/model&job={job_id}",
        "approval": approval,
        "requires_human_review": True,
        "research_only": True,
        "clinical_use_allowed": False,
        "disclaimer": server.DISCLAIMER,
        "restored_from_artifacts": True,
    }
    return {
        "state": "done",
        "step": "concluido",
        "progress": 100,
        "analysis_scenario": result["analysis_scenario"],
        "enhanced_3d": False,
        "result": result,
        "approval": approval,
    }


def _restore_completed_job(job_id: str) -> dict[str, Any] | None:
    path = _completed_job_state_path(job_id)
    restored: dict[str, Any] | None = None
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if (
                isinstance(payload, dict)
                and payload.get("schema") == "oren-webapp-completed-job-v1"
                and payload.get("job_id") == job_id
                and payload.get("state") == "done"
                and isinstance(payload.get("result"), dict)
            ):
                result = payload["result"]
                if not result.get("viewer_ready") or server._model_done(server._case_dir_for_job(job_id)):
                    restored = payload
        except (OSError, json.JSONDecodeError):
            restored = None
    if restored is None:
        restored = server._legacy_completed_job_from_artifacts(job_id)
        if restored is not None:
            server._persist_completed_job_state(job_id, restored)
    if restored is None:
        return None
    with server._lock:
        existing = server._jobs.get(job_id)
        if existing is None:
            server._jobs[job_id] = restored
            existing = server._jobs[job_id]
    return existing
