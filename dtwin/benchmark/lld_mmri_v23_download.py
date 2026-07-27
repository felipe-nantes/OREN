"""Fail-closed image-only downloader for the frozen LLD-MMRI v23 cohort."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Callable

from dtwin.benchmark.lld_mmri_v23_external import (
    MAPPING_SCHEMA,
    PROTOCOL_SCHEMA,
    REPO_ID,
    REPO_REVISION,
)
from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.core import PipelineError, sha256_of
from dtwin.medgemma_screening import _write_json_atomic


DOWNLOAD_SCHEMA = "argos-lld-mmri-v23-image-download-manifest-v1"
PHASE_SUFFIXES = {
    "t1_native": "C-pre",
    "t1_arterial": "C+A",
    "t1_venous": "C+V",
    "t1_delayed": "C+Delay",
    "t2": "T2WI",
    "dwi": "DWI",
    "t1_in_phase": "InPhase",
    "t1_out_phase": "OutPhase",
}
FORBIDDEN_PATH_TERMS = ("label", "mask", "bbox", "annotation", "ground_truth", "lesion")


def _load_and_validate_protocol(protocol_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    protocol_root = Path(protocol_root).resolve()
    protocol_path = protocol_root / "protocol.json"
    mapping_path = protocol_root / "protected_source" / "mapping.jsonl"
    try:
        protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
        mappings = [
            json.loads(line)
            for line in mapping_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Protocolo externo LLD-MMRI invalido para download.") from exc
    signature = protocol.get("protocol_signature")
    unsigned = dict(protocol)
    unsigned.pop("protocol_signature", None)
    case_ids = protocol.get("case_ids")
    if (
        protocol.get("schema") != PROTOCOL_SCHEMA
        or protocol.get("status") != "frozen_before_external_images_and_predictions"
        or signature != _canonical_sha(unsigned)
        or protocol.get("dataset_repo_id") != REPO_ID
        or protocol.get("dataset_revision") != REPO_REVISION
        or protocol.get("protected_mapping_sha256") != sha256_of(mapping_path)
        or protocol.get("lesion_masks_allowed_in_inference") is not False
        or not isinstance(case_ids, list)
        or len(case_ids) != len(set(case_ids))
        or len(mappings) != protocol.get("case_count")
        or len(case_ids) != len(mappings)
    ):
        raise PipelineError("Protocolo externo LLD-MMRI adulterado ou inseguro.")
    for index, mapping in enumerate(mappings):
        if (
            mapping.get("schema") != MAPPING_SCHEMA
            or mapping.get("case_id") != case_ids[index]
            or mapping.get("lesion_masks_allowed_in_inference") is not False
            or mapping.get("raw_uids_persisted") is not False
        ):
            raise PipelineError("Mapeamento protegido LLD-MMRI divergiu.")
    return protocol, mappings


def select_subject_image_files(source_subject_id: str, repo_files: list[str]) -> dict[str, str]:
    prefix = f"images/{source_subject_id}_"
    matches = [path for path in repo_files if path.startswith(prefix) and path.endswith("_0000.nii.gz")]
    selected: dict[str, str] = {}
    for role, suffix in PHASE_SUFFIXES.items():
        candidates = [path for path in matches if path.endswith(f"_{suffix}_0000.nii.gz")]
        if len(candidates) != 1:
            raise PipelineError(f"LLD-MMRI {source_subject_id} nao possui uma imagem unica para {role}.")
        selected[role] = candidates[0]
    if len(set(selected.values())) != len(PHASE_SUFFIXES) or len(matches) != len(PHASE_SUFFIXES):
        raise PipelineError(f"LLD-MMRI {source_subject_id} possui conjunto de imagens inesperado.")
    return selected


def download_lld_mmri_v23_images(
    *,
    protocol_root: Path,
    destination: Path,
    accept_license: bool,
    repo_files: list[str],
    downloader: Callable[..., str],
    progress: Callable[[int, int, str], None] | None = None,
    workers: int = 1,
) -> dict[str, Any]:
    if accept_license is not True:
        raise PipelineError("Download LLD-MMRI exige aceite explicito dos termos CC BY-NC 4.0 e nao comerciais.")
    if isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= 16:
        raise PipelineError("Download LLD-MMRI exige entre 1 e 16 workers.")
    protocol_root = Path(protocol_root).resolve()
    protocol, mappings = _load_and_validate_protocol(protocol_root)
    signature = protocol["protocol_signature"]
    destination = Path(destination).resolve()
    manifest_path = destination / "image_download_manifest.json"
    if manifest_path.exists():
        raise PipelineError("Manifesto de download LLD-MMRI ja existe; reuso deve ser validado separadamente.")
    destination.mkdir(parents=True, exist_ok=True)
    cases: list[dict[str, Any] | None] = [None] * len(mappings)

    def download_case(index: int, mapping: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        selected = select_subject_image_files(mapping["source_subject_id"], repo_files)
        downloaded: dict[str, dict[str, Any]] = {}
        for role, repo_path in selected.items():
            if not repo_path.startswith("images/") or any(
                term in repo_path.lower() for term in FORBIDDEN_PATH_TERMS
            ):
                raise PipelineError("Tentativa de baixar ground truth LLD-MMRI bloqueada.")
            local = Path(
                downloader(
                    repo_id=REPO_ID,
                    repo_type="dataset",
                    revision=REPO_REVISION,
                    filename=repo_path,
                    local_dir=str(destination),
                )
            ).resolve()
            if not local.is_file() or not local.is_relative_to(destination):
                raise PipelineError("Download LLD-MMRI saiu do destino autorizado.")
            downloaded[role] = {
                "relative_path": local.relative_to(destination).as_posix(),
                "bytes": local.stat().st_size,
                "sha256": _sha256(local),
            }
        return index, {"case_id": mapping["case_id"], "images": downloaded}

    completed = 0
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="lld-v23") as executor:
        futures = {
            executor.submit(download_case, index, mapping): index
            for index, mapping in enumerate(mappings)
        }
        for future in as_completed(futures):
            index, record = future.result()
            cases[index] = record
            completed += 1
            if progress is not None:
                progress(completed, len(mappings), str(record["case_id"]))
    if any(record is None for record in cases):
        raise PipelineError("Download paralelo LLD-MMRI terminou com caso ausente.")
    ordered_cases = [record for record in cases if record is not None]
    base = {
        "schema": DOWNLOAD_SCHEMA,
        "status": "selected_images_downloaded_no_lesion_ground_truth",
        "protocol_signature": signature,
        "dataset_repo_id": REPO_ID,
        "dataset_revision": REPO_REVISION,
        "case_count": len(ordered_cases),
        "image_count": len(ordered_cases) * len(PHASE_SUFFIXES),
        "cases": ordered_cases,
        "download_workers": workers,
        "license_terms_explicitly_accepted": True,
        "labels_downloaded": False,
        "lesion_masks_downloaded": False,
        "raw_uids_persisted": False,
        "ground_truth_read_during_download": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    manifest = dict(base)
    manifest["manifest_signature"] = _canonical_sha(base)
    _write_json_atomic(manifest_path, manifest)
    return validate_lld_mmri_v23_download(
        protocol_root=protocol_root,
        destination=destination,
    )


def validate_lld_mmri_v23_download(
    *, protocol_root: Path, destination: Path
) -> dict[str, Any]:
    """Verify the complete image-only download before any image may be processed."""

    protocol, _ = _load_and_validate_protocol(protocol_root)
    destination = Path(destination).resolve()
    manifest_path = destination / "image_download_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Manifesto de download LLD-MMRI ausente ou invalido.") from exc
    unsigned = dict(manifest) if isinstance(manifest, dict) else {}
    signature = unsigned.pop("manifest_signature", None)
    cases = manifest.get("cases") if isinstance(manifest, dict) else None
    if (
        manifest.get("schema") != DOWNLOAD_SCHEMA
        or manifest.get("status") != "selected_images_downloaded_no_lesion_ground_truth"
        or signature != _canonical_sha(unsigned)
        or manifest.get("protocol_signature") != protocol["protocol_signature"]
        or manifest.get("dataset_repo_id") != REPO_ID
        or manifest.get("dataset_revision") != REPO_REVISION
        or manifest.get("case_count") != protocol["case_count"]
        or manifest.get("image_count") != protocol["case_count"] * len(PHASE_SUFFIXES)
        or manifest.get("labels_downloaded") is not False
        or manifest.get("lesion_masks_downloaded") is not False
        or manifest.get("ground_truth_read_during_download") is not False
        or manifest.get("license_terms_explicitly_accepted") is not True
        or not isinstance(cases, list)
        or len(cases) != protocol["case_count"]
    ):
        raise PipelineError("Manifesto de download LLD-MMRI adulterado ou inseguro.")
    seen_paths: set[str] = set()
    for index, case in enumerate(cases):
        images = case.get("images") if isinstance(case, dict) else None
        if (
            case.get("case_id") != protocol["case_ids"][index]
            or not isinstance(images, dict)
            or set(images) != set(PHASE_SUFFIXES)
        ):
            raise PipelineError("Caso baixado LLD-MMRI incompleto ou fora de ordem.")
        for item in images.values():
            relative_text = str(item.get("relative_path", "")) if isinstance(item, dict) else ""
            relative = PurePosixPath(relative_text)
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or not relative.parts
                or relative.parts[0] != "images"
                or any(term in relative_text.lower() for term in FORBIDDEN_PATH_TERMS)
                or relative_text in seen_paths
            ):
                raise PipelineError("Caminho de imagem LLD-MMRI inseguro ou duplicado.")
            path = (destination / Path(*relative.parts)).resolve()
            if (
                not path.is_relative_to(destination)
                or not path.is_file()
                or path.stat().st_size != item.get("bytes")
                or _sha256(path) != item.get("sha256")
            ):
                raise PipelineError("Imagem LLD-MMRI ausente ou adulterada.")
            seen_paths.add(relative_text)
    if len(seen_paths) != manifest["image_count"]:
        raise PipelineError("Cobertura do download LLD-MMRI divergiu do protocolo.")
    return manifest


__all__ = [
    "DOWNLOAD_SCHEMA",
    "PHASE_SUFFIXES",
    "download_lld_mmri_v23_images",
    "select_subject_image_files",
    "validate_lld_mmri_v23_download",
]
