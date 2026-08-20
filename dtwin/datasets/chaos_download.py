"""License-gated, atomic acquisition of the official CHAOS v1.03 train set."""
from __future__ import annotations

import hashlib
import os
import shutil
import stat
import urllib.request
import uuid
import zipfile
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic

MANIFEST_SCHEMA = "argos-chaos-v103-download-manifest-v1"
EXTRACTION_SCHEMA = "argos-chaos-v103-mri-extraction-manifest-v1"
LICENSE_ID = "CC-BY-NC-SA-4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by-nc-sa/4.0/"
SOURCE_RECORD = "https://zenodo.org/records/3431873"


@dataclass(frozen=True)
class ChaosDownloadSpec:
    filename: str
    url: str
    size_bytes: int
    md5: str
    record_id: str = "3431873"
    version: str = "v1.03"


CHAOS_TRAIN_SPEC = ChaosDownloadSpec(
    filename="CHAOS_Train_Sets.zip",
    url="https://zenodo.org/api/records/3431873/files/CHAOS_Train_Sets.zip/content",
    size_bytes=890_771_694,
    md5="df21053002a1cc86df918a87da3b2c19",
)


def _archive_layout(path: Path) -> dict[str, int | bool]:
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
    except (OSError, zipfile.BadZipFile) as exc:
        raise PipelineError("Arquivo CHAOS nao e um ZIP valido.") from exc
    if not infos:
        raise PipelineError("Arquivo CHAOS vazio.")
    files = 0
    has_mr = has_t1dual = has_t2spir = False
    for info in infos:
        normalized = info.filename.replace("\\", "/")
        pure = PurePosixPath(normalized)
        if pure.is_absolute() or ".." in pure.parts:
            raise PipelineError("ZIP CHAOS contem caminho inseguro.")
        upper = normalized.upper()
        if not info.is_dir():
            files += 1
        has_mr = has_mr or "/MR/" in f"/{upper.strip('/')}"
        has_t1dual = has_t1dual or "T1DUAL" in upper
        has_t2spir = has_t2spir or "T2SPIR" in upper or "T2-SPIR" in upper
    if files < 1 or not (has_mr and has_t1dual and has_t2spir):
        raise PipelineError("ZIP CHAOS nao contem a estrutura MRI T1DUAL/T2SPIR esperada.")
    return {
        "archive_member_count": len(infos),
        "archive_file_count": files,
        "contains_mr": has_mr,
        "contains_t1dual": has_t1dual,
        "contains_t2spir": has_t2spir,
    }


def verify_chaos_train_archive(
    path: Path,
    *,
    spec: ChaosDownloadSpec = CHAOS_TRAIN_SPEC,
) -> dict[str, object]:
    source = Path(path).resolve()
    if not source.is_file() or source.name != spec.filename:
        raise PipelineError("Arquivo de treino CHAOS ausente ou com nome inesperado.")
    if source.stat().st_size != spec.size_bytes:
        raise PipelineError("Tamanho do arquivo CHAOS diverge do registro oficial.")
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    with source.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            md5.update(block)
            sha256.update(block)
    if md5.hexdigest() != spec.md5:
        raise PipelineError("MD5 do arquivo CHAOS diverge do registro oficial.")
    return {
        "path": str(source),
        "bytes": source.stat().st_size,
        "md5": md5.hexdigest(),
        "sha256": sha256.hexdigest(),
        **_archive_layout(source),
    }


def download_chaos_train(
    *,
    output_dir: Path,
    accept_license: bool,
    accepted_by: str,
    spec: ChaosDownloadSpec = CHAOS_TRAIN_SPEC,
    opener: Callable[[str], AbstractContextManager[BinaryIO]] = urllib.request.urlopen,
) -> dict[str, object]:
    """Download exactly the public train ZIP after explicit license acceptance."""

    if accept_license is not True:
        raise PipelineError("Termos CC BY-NC-SA 4.0 do CHAOS nao foram aceitos explicitamente.")
    reviewer = str(accepted_by).strip()
    if not reviewer or len(reviewer) > 80:
        raise PipelineError("Identificador do responsavel pelo aceite CHAOS e obrigatorio.")
    root = Path(output_dir).resolve()
    archive_path = root / spec.filename
    manifest_path = root / "download_manifest.json"
    if root.exists() or archive_path.exists() or manifest_path.exists():
        raise PipelineError("Destino CHAOS ja existe; recuso sobrescrever aquisicao.")
    root.parent.mkdir(parents=True, exist_ok=True)
    staging = root.parent / f"._chaos_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    temporary_archive = staging / spec.filename
    try:
        try:
            with opener(spec.url) as response, temporary_archive.open("xb") as target:
                shutil.copyfileobj(response, target, length=1024 * 1024)
        except (OSError, ValueError) as exc:
            raise PipelineError(f"Falha no download oficial CHAOS: {exc}") from exc
        verification = verify_chaos_train_archive(temporary_archive, spec=spec)
        payload: dict[str, object] = {
            "schema": MANIFEST_SCHEMA,
            "status": "downloaded_verified_not_extracted",
            "dataset": "CHAOS",
            "version": spec.version,
            "zenodo_record_id": spec.record_id,
            "source_record": SOURCE_RECORD,
            "source_url": spec.url,
            "filename": spec.filename,
            "bytes": verification["bytes"],
            "md5": verification["md5"],
            "sha256": verification["sha256"],
            "archive_member_count": verification["archive_member_count"],
            "archive_file_count": verification["archive_file_count"],
            "contains_mr": verification["contains_mr"],
            "contains_t1dual": verification["contains_t1dual"],
            "contains_t2spir": verification["contains_t2spir"],
            "license": LICENSE_ID,
            "license_url": LICENSE_URL,
            "license_accepted": True,
            "license_accepted_by": reviewer,
            "license_accepted_at_utc": datetime.now(timezone.utc).isoformat(),
            "noncommercial_research_only": True,
            "clinical_use_allowed": False,
            "test_set_downloaded": False,
            "test_ground_truth_requested": False,
            "extracted": False,
        }
        _write_json_atomic(staging / "download_manifest.json", payload)
        os.replace(staging, root)
        return payload
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def extract_chaos_mri_train(
    *,
    download_root: Path,
    output_dir: Path,
    spec: ChaosDownloadSpec = CHAOS_TRAIN_SPEC,
    expected_subject_count: int = 20,
) -> dict[str, object]:
    """Extract only the MR train arm after revalidating the frozen archive."""

    source_root = Path(download_root).resolve()
    archive_path = source_root / spec.filename
    download_manifest_path = source_root / "download_manifest.json"
    try:
        import json

        download_manifest = json.loads(download_manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PipelineError("Manifesto de download CHAOS ausente ou invalido.") from exc
    verification = verify_chaos_train_archive(archive_path, spec=spec)
    if (
        not isinstance(download_manifest, dict)
        or download_manifest.get("schema") != MANIFEST_SCHEMA
        or download_manifest.get("status") != "downloaded_verified_not_extracted"
        or download_manifest.get("license_accepted") is not True
        or download_manifest.get("sha256") != verification["sha256"]
        or download_manifest.get("md5") != verification["md5"]
        or download_manifest.get("test_set_downloaded") is not False
    ):
        raise PipelineError("Manifesto de download CHAOS diverge do arquivo congelado.")
    destination = Path(output_dir).resolve()
    if destination.exists():
        raise PipelineError("Destino MRI CHAOS ja existe; recuso sobrescrever extracao.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f"._chaos_mri_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    prefix = PurePosixPath("Train_Sets/MR")
    subjects: set[str] = set()
    extracted_files = 0
    extracted_bytes = 0
    tree = hashlib.sha256()
    try:
        with zipfile.ZipFile(archive_path) as archive:
            selected = sorted(
                (item for item in archive.infolist() if not item.is_dir()),
                key=lambda item: item.filename.replace("\\", "/"),
            )
            for info in selected:
                normalized = info.filename.replace("\\", "/")
                member = PurePosixPath(normalized)
                if member.is_absolute() or ".." in member.parts:
                    raise PipelineError("ZIP CHAOS contem caminho inseguro durante extracao.")
                try:
                    relative = member.relative_to(prefix)
                except ValueError:
                    continue
                if len(relative.parts) < 2 or not relative.parts[0].isdigit():
                    raise PipelineError("Membro MRI CHAOS nao pertence a um sujeito numerico.")
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise PipelineError("ZIP CHAOS contem link simbolico proibido.")
                subjects.add(relative.parts[0])
                target = staging / Path(*member.parts)
                resolved_target = target.resolve()
                if not resolved_target.is_relative_to(staging.resolve()):
                    raise PipelineError("Destino de extracao CHAOS escapou do staging.")
                target.parent.mkdir(parents=True, exist_ok=True)
                file_hash = hashlib.sha256()
                with archive.open(info) as source, target.open("xb") as output:
                    while True:
                        block = source.read(1024 * 1024)
                        if not block:
                            break
                        output.write(block)
                        file_hash.update(block)
                size = target.stat().st_size
                if size != info.file_size:
                    raise PipelineError("Arquivo extraido CHAOS possui tamanho divergente.")
                relative_token = member.as_posix()
                tree.update(relative_token.encode("utf-8"))
                tree.update(b"\0")
                tree.update(str(size).encode("ascii"))
                tree.update(b"\0")
                tree.update(file_hash.hexdigest().encode("ascii"))
                tree.update(b"\n")
                extracted_files += 1
                extracted_bytes += size
        ordered_subjects = sorted(subjects, key=int)
        if len(ordered_subjects) != int(expected_subject_count):
            raise PipelineError(
                f"Quantidade de sujeitos MRI CHAOS divergente: {len(ordered_subjects)} != {expected_subject_count}."
            )
        payload: dict[str, object] = {
            "schema": EXTRACTION_SCHEMA,
            "status": "mri_train_extracted_verified",
            "dataset": "CHAOS",
            "version": spec.version,
            "source_archive_sha256": verification["sha256"],
            "source_archive_md5": verification["md5"],
            "source_download_manifest_sha256": hashlib.sha256(
                download_manifest_path.read_bytes()
            ).hexdigest(),
            "extracted_tree_sha256": tree.hexdigest(),
            "extracted_file_count": extracted_files,
            "extracted_bytes": extracted_bytes,
            "subject_count": len(ordered_subjects),
            "subject_ids": ordered_subjects,
            "extracted_prefix": prefix.as_posix(),
            "ct_extracted": False,
            "test_set_extracted": False,
            "organ_masks_present": True,
            "lesion_masks_present": False,
            "pathology_labels_present": False,
            "license": LICENSE_ID,
            "noncommercial_research_only": True,
            "clinical_use_allowed": False,
        }
        _write_json_atomic(staging / "extraction_manifest.json", payload)
        os.replace(staging, destination)
        return payload
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def verify_chaos_mri_extraction(
    *,
    extracted_root: Path,
    expected_subject_count: int = 20,
) -> dict[str, object]:
    """Rehash every extracted MRI byte, including the public organ masks."""

    root = Path(extracted_root).resolve()
    manifest_path = root / "extraction_manifest.json"
    try:
        import json

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PipelineError("Manifesto de extracao CHAOS ausente ou invalido.") from exc
    mr_root = root / "Train_Sets" / "MR"
    if not mr_root.is_dir() or not isinstance(manifest, dict):
        raise PipelineError("Raiz MRI CHAOS extraida esta ausente.")
    tree = hashlib.sha256()
    files = 0
    total_bytes = 0
    subjects: set[str] = set()
    for path in sorted((item for item in mr_root.rglob("*") if item.is_file())):
        resolved = path.resolve()
        if not resolved.is_relative_to(mr_root.resolve()):
            raise PipelineError("Arquivo MRI CHAOS escapou da raiz extraida.")
        relative = resolved.relative_to(root).as_posix()
        parts = PurePosixPath(relative).parts
        if len(parts) < 4 or parts[:2] != ("Train_Sets", "MR") or not parts[2].isdigit():
            raise PipelineError("Estrutura extraida CHAOS possui arquivo inesperado.")
        subjects.add(parts[2])
        size = resolved.stat().st_size
        digest = hashlib.sha256()
        with resolved.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        tree.update(relative.encode("utf-8"))
        tree.update(b"\0")
        tree.update(str(size).encode("ascii"))
        tree.update(b"\0")
        tree.update(digest.hexdigest().encode("ascii"))
        tree.update(b"\n")
        files += 1
        total_bytes += size
    ordered_subjects = sorted(subjects, key=int)
    if (
        manifest.get("schema") != EXTRACTION_SCHEMA
        or manifest.get("status") != "mri_train_extracted_verified"
        or manifest.get("extracted_tree_sha256") != tree.hexdigest()
        or manifest.get("extracted_file_count") != files
        or manifest.get("extracted_bytes") != total_bytes
        or manifest.get("subject_ids") != ordered_subjects
        or manifest.get("subject_count") != expected_subject_count
        or len(ordered_subjects) != expected_subject_count
        or manifest.get("ct_extracted") is not False
        or manifest.get("test_set_extracted") is not False
        or manifest.get("lesion_masks_present") is not False
        or manifest.get("pathology_labels_present") is not False
        or manifest.get("clinical_use_allowed") is not False
    ):
        raise PipelineError("Extracao MRI CHAOS foi alterada ou perdeu salvaguardas.")
    return {
        "schema": "argos-chaos-v103-mri-extraction-preflight-v1",
        "status": "verified_for_blind_preparation",
        "subject_count": len(ordered_subjects),
        "extracted_file_count": files,
        "extracted_bytes": total_bytes,
        "extracted_tree_sha256": tree.hexdigest(),
        "lesion_masks_present": False,
        "pathology_labels_present": False,
        "test_set_extracted": False,
        "clinical_use_allowed": False,
        "research_only": True,
    }
