"""Sessões XR/Quest: tokens, QR e jobs recentes (REF-03 seam 1).

Extraído de server.py sem mudança de comportamento. REGRA R2 do design:
config/estado e símbolos monkeypatchados resolvem via `server.<nome>` em
tempo de chamada (WORKSPACE, _model_done, _case_dir_for_job).
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request

from webapp import server

log = logging.getLogger("dtwin.webapp")


def _xr_session_path(case_dir: Path, token: str) -> Path:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return case_dir / "outputs" / "xr_sessions" / f"{digest}.json"


def _read_xr_session(job_id: str, token: str) -> dict[str, Any]:
    if not token or len(token) > 256:
        raise HTTPException(status_code=401, detail="Sessao XR invalida.")
    case_dir = server._case_dir_for_job(job_id)
    path = _xr_session_path(case_dir, token)
    try:
        session = json.loads(path.read_text("utf-8"))
        expires_at = datetime.fromisoformat(str(session["expires_at"]))
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Sessao XR invalida.") from exc
    if session.get("job_id") != job_id or expires_at <= datetime.now(timezone.utc):
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=401, detail="Sessao XR expirada.")
    return session


def _quest_base_url(request: Request) -> str:
    configured = os.environ.get("OREN_QUEST_BASE_URL", "").strip().rstrip("/")
    if configured:
        return configured
    hostname = request.url.hostname or "127.0.0.1"
    request_port = request.url.port
    # Quando a sessão nasce no próprio atalho aberto pelo Quest, preservar a
    # origem que já provou estar acessível. Forçar HTTPS:8443 aqui fazia o
    # navegador abandonar o servidor HTTP:8082 funcional após a tela de loading.
    if hostname not in {"127.0.0.1", "localhost", "::1"}:
        default_port = 443 if request.url.scheme == "https" else 80
        port_suffix = f":{request_port}" if request_port and request_port != default_port else ""
        return f"{request.url.scheme}://{hostname}{port_suffix}"
    if hostname in {"127.0.0.1", "localhost", "::1"}:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("10.255.255.255", 1))
            hostname = str(probe.getsockname()[0])
        except OSError:
            hostname = "127.0.0.1"
        finally:
            probe.close()
    return f"https://{hostname}:{int(os.environ.get('OREN_QUEST_PORT', '8443'))}"


def _quest_qr_data_url(value: str) -> str | None:
    """Render a self-contained QR code without exposing the XR token in logs."""
    try:
        import qrcode
        from qrcode.image.svg import SvgPathImage
    except ImportError:
        log.warning("QR Code indisponivel: instale o extra webapp atualizado.")
        return None
    image = qrcode.make(
        value,
        image_factory=SvgPathImage,
        box_size=8,
        border=2,
    )
    buffer = io.BytesIO()
    image.save(buffer)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _recent_quest_jobs(*, limit: int = 8) -> list[dict[str, str]]:
    """Return recent viewer-ready jobs without exposing clinical metadata."""
    if not server.WORKSPACE.is_dir():
        return []
    candidates: list[tuple[float, str]] = []
    for job_root in server.WORKSPACE.iterdir():
        job_id = job_root.name
        if (
            not job_root.is_dir()
            or not job_id
            or any(ch not in "0123456789abcdef" for ch in job_id.lower())
        ):
            continue
        case_dir = job_root / "case"
        manifest = case_dir / "outputs" / "viewer_manifest.json"
        if not manifest.is_file():
            continue
        try:
            updated_at = manifest.stat().st_mtime
        except OSError:
            continue
        candidates.append((updated_at, job_id))
    candidates.sort(reverse=True)
    ready: list[dict[str, str]] = []
    # Hash validation may read several meshes. Validate newest-first and stop as
    # soon as the small headset list is full instead of hashing the whole archive.
    for updated_at, job_id in candidates:
        if not server._model_done(server.WORKSPACE / job_id / "case"):
            continue
        ready.append({
            "job_id": job_id,
            "updated_at": datetime.fromtimestamp(updated_at, timezone.utc).isoformat(),
        })
        if len(ready) >= limit:
            break
    return ready
