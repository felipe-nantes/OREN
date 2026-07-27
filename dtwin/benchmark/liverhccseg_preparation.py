"""Prepare label-blind, registered LiverHccSeg inputs for the public v21 pilot."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import SimpleITK as sitk
import numpy as np

from dtwin.benchmark.public_independent_cohort import anonymous_public_case_id
from dtwin.core import PipelineError


CASE_SCHEMA = "argos-liverhccseg-blind-input-case-v1"
COHORT_SCHEMA = "argos-liverhccseg-blind-input-cohort-v1"
ROLE_FILES = {
    "t1_native": "art_pre.nii.gz",
    "t1_arterial": "art.nii.gz",
    "t1_venous": "art_pv.nii.gz",
    "t1_delayed": "art_del.nii.gz",
    "liver_mask": "rater1_liver.nii.gz",
}


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{label} inválido ({path}): {exc}") from exc
    if not isinstance(payload, dict):
        raise PipelineError(f"{label} deve ser objeto.")
    return payload


def _geometry(image: sitk.Image) -> dict[str, Any]:
    return {
        "size_xyz": list(image.GetSize()),
        "spacing_xyz": [float(value) for value in image.GetSpacing()],
        "origin_xyz": [float(value) for value in image.GetOrigin()],
        "direction": [float(value) for value in image.GetDirection()],
    }


def _same_geometry(first: sitk.Image, second: sitk.Image, tolerance: float = 1e-5) -> bool:
    if first.GetDimension() != 3 or second.GetDimension() != 3:
        return False
    if first.GetSize() != second.GetSize():
        return False
    return all(
        abs(float(a) - float(b)) <= tolerance
        for left, right in (
            (first.GetSpacing(), second.GetSpacing()),
            (first.GetOrigin(), second.GetOrigin()),
            (first.GetDirection(), second.GetDirection()),
        )
        for a, b in zip(left, right)
    )


def _publish(staging: Path, destination: Path) -> None:
    if destination.exists():
        raise PipelineError(f"Destino já existe: {destination}")
    os.replace(staging, destination)


def _link_or_copy(source: Path, destination: Path) -> str:
    try:
        os.link(source, destination)
        return "hardlink"
    except OSError:
        shutil.copyfile(source, destination)
        return "copy"


def _resample_phase_to_reference(
    image: sitk.Image,
    reference: sitk.Image,
    liver_mask: sitk.Image,
    destination: Path,
    *,
    minimum_liver_support: float = 0.95,
) -> float:
    support = sitk.Image(image.GetSize(), sitk.sitkUInt8)
    support.CopyInformation(image)
    support = support + 1
    resampled_support = sitk.Resample(
        support, reference, sitk.Transform(), sitk.sitkNearestNeighbor, 0, sitk.sitkUInt8
    )
    liver = sitk.GetArrayViewFromImage(liver_mask) > 0
    if not np.any(liver):
        raise PipelineError("Máscara hepática pública está vazia.")
    available = sitk.GetArrayViewFromImage(resampled_support) > 0
    fraction = float(np.count_nonzero(available & liver) / np.count_nonzero(liver))
    if fraction < minimum_liver_support:
        raise PipelineError(
            f"Fase registrada cobre apenas {fraction:.4f} do fígado; mínimo={minimum_liver_support:.4f}."
        )
    resampled = sitk.Resample(
        sitk.Cast(image, sitk.sitkFloat32),
        reference,
        sitk.Transform(),
        sitk.sitkLinear,
        0.0,
        sitk.sitkFloat32,
    )
    sitk.WriteImage(resampled, str(destination), useCompression=True)
    return fraction


def prepare_liverhccseg_blind_inputs(
    *,
    source_root: Path,
    protected_selection_audit_path: Path,
    output_root: Path,
    cohort_id: str = "public_independent_v21_liverhccseg_chaos",
    expected_case_count: int = 14,
) -> dict[str, Any]:
    """Materialize only registered phases and a liver mask; never lesion masks."""
    source_root = Path(source_root).resolve()
    output_root = Path(output_root).resolve()
    if not source_root.is_dir():
        raise PipelineError(f"Raiz NIfTI LiverHccSeg ausente: {source_root}")
    if output_root.exists():
        raise PipelineError(f"Recuso sobrescrever preparação congelada: {output_root}")
    audit = _load_object(Path(protected_selection_audit_path).resolve(), "Auditoria protegida")
    if audit.get("status") != "tumor_positive_registry_filtered":
        raise PipelineError("Auditoria não comprova filtro tumor-positivo LiverHccSeg.")
    if audit.get("ground_truth_available_to_inference") is not False:
        raise PipelineError("Auditoria não comprova isolamento do ground truth.")
    allowed_hashes = set(audit.get("included_subject_hashes") or [])
    if len(allowed_hashes) != expected_case_count:
        raise PipelineError("Quantidade de sujeitos autorizados diverge do esperado.")

    selected_subjects = [
        subject for subject in sorted(source_root.iterdir(), key=lambda path: path.name)
        if subject.is_dir() and hashlib.sha256(subject.name.encode()).hexdigest() in allowed_hashes
    ]
    if len(selected_subjects) != expected_case_count:
        raise PipelineError("Raiz NIfTI não contém todos os sujeitos autorizados.")

    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_root.name}-", dir=output_root.parent))
    cases: list[dict[str, Any]] = []
    try:
        for subject in selected_subjects:
            studies = [path for path in subject.iterdir() if path.is_dir()]
            if len(studies) != 1:
                raise PipelineError("Sujeito LiverHccSeg exige exatamente um estudo NIfTI.")
            study = studies[0]
            sources = {role: study / filename for role, filename in ROLE_FILES.items()}
            missing = [role for role, path in sources.items() if not path.is_file()]
            if missing:
                raise PipelineError(f"Fases/máscara LiverHccSeg ausentes: {missing}")
            reference = sitk.ReadImage(str(sources["t1_arterial"]))
            if reference.GetDimension() != 3:
                raise PipelineError("Fase arterial LiverHccSeg deve ser 3D.")
            mask = sitk.ReadImage(str(sources["liver_mask"]))
            if not _same_geometry(reference, mask):
                raise PipelineError("Máscara hepática não coincide com a grade arterial.")
            statistics = sitk.StatisticsImageFilter()
            statistics.Execute(mask)
            if statistics.GetMaximum() <= 0:
                raise PipelineError("Máscara hepática pública está vazia.")

            case_id = anonymous_public_case_id(cohort_id, "liverhccseg", subject.name)
            case_dir = staging / case_id
            case_dir.mkdir()
            files: list[dict[str, Any]] = []
            link_modes: set[str] = set()
            for role, source in sources.items():
                filename = f"{role}.nii.gz"
                destination = case_dir / filename
                image = sitk.ReadImage(str(source))
                resampled = role != "liver_mask" and not _same_geometry(reference, image)
                liver_support_fraction = 1.0
                if resampled:
                    liver_support_fraction = _resample_phase_to_reference(
                        image, reference, mask, destination
                    )
                    link_modes.add("physical_resample")
                else:
                    link_modes.add(_link_or_copy(source, destination))
                files.append({
                    "role": role,
                    "relative_path": f"{case_id}/{filename}",
                    "sha256": _hash(destination),
                    "bytes": destination.stat().st_size,
                    "resampled_to_arterial_grid": resampled,
                    "interpolation": "linear" if resampled else "none",
                    "liver_support_fraction": liver_support_fraction,
                })
            if any("tumor" in path.name.lower() or "lesion" in path.name.lower() for path in case_dir.rglob("*")):
                raise PipelineError("Máscara de tumor/lesão vazou para o workspace cego.")
            manifest = {
                "schema": CASE_SCHEMA,
                "case_id": case_id,
                "files": files,
                "reference_geometry": _geometry(reference),
                "materialization": sorted(link_modes),
                "organ_mask_source": "public_manual_liver_segmentation_rater1",
                "lesion_mask_present": False,
                "pathology_label_present": False,
                "protected_pathology_ground_truth_read_during_inference": False,
                "registered_phases": True,
                "reference_grid": "t1_arterial",
                "minimum_liver_support_fraction": 0.95,
                "research_only": True,
                "clinical_use_allowed": False,
                "requires_human_review": True,
            }
            manifest["case_signature"] = _canonical_hash(manifest)
            (case_dir / "input_manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            cases.append({
                "case_id": case_id,
                "case_manifest": f"{case_id}/input_manifest.json",
                "case_manifest_sha256": _hash(case_dir / "input_manifest.json"),
                "case_signature": manifest["case_signature"],
            })
        cases.sort(key=lambda item: item["case_id"])
        cohort = {
            "schema": COHORT_SCHEMA,
            "cohort_id": cohort_id,
            "case_count": len(cases),
            "cases": cases,
            "selection_audit_sha256": _hash(Path(protected_selection_audit_path).resolve()),
            "roles": list(ROLE_FILES),
            "lesion_masks_copied": False,
            "pathology_labels_copied": False,
            "protected_pathology_ground_truth_read_during_inference": False,
            "holdout_opened": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        cohort["cohort_signature"] = _canonical_hash(cohort)
        (staging / "cohort_manifest.json").write_text(
            json.dumps(cohort, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _publish(staging, output_root)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return cohort


def verify_liverhccseg_blind_inputs(
    *,
    prepared_root: Path,
    expected_cohort_signature: str | None = None,
    expected_case_count: int = 14,
) -> dict[str, Any]:
    """Verify every permitted input byte and refuse lesion/label artifacts."""
    prepared_root = Path(prepared_root).resolve()
    cohort = _load_object(prepared_root / "cohort_manifest.json", "Manifesto da coorte preparada")
    if cohort.get("schema") != COHORT_SCHEMA:
        raise PipelineError("Schema da coorte LiverHccSeg preparada é inválido.")
    signature = str(cohort.get("cohort_signature") or "")
    unsigned = dict(cohort)
    unsigned.pop("cohort_signature", None)
    if signature != _canonical_hash(unsigned):
        raise PipelineError("Assinatura da coorte LiverHccSeg é inconsistente.")
    if expected_cohort_signature and signature != expected_cohort_signature:
        raise PipelineError("Assinatura da coorte difere da esperada.")
    cases = cohort.get("cases")
    if not isinstance(cases, list) or len(cases) != expected_case_count:
        raise PipelineError("Quantidade de casos preparados diverge do esperado.")
    if cohort.get("lesion_masks_copied") is not False or cohort.get("pathology_labels_copied") is not False:
        raise PipelineError("Coorte não comprova isolamento de lesões/labels.")
    if cohort.get("holdout_opened") is not False:
        raise PipelineError("Coorte não comprova holdout fechado.")

    observed_ids: list[str] = []
    for case_record in cases:
        case_id = str(case_record.get("case_id") or "")
        observed_ids.append(case_id)
        if not case_id.startswith("anon-public-"):
            raise PipelineError(f"case_id não pseudonimizado: {case_id!r}")
        manifest_path = (prepared_root / Path(str(case_record.get("case_manifest") or ""))).resolve()
        try:
            manifest_path.relative_to(prepared_root)
        except ValueError as exc:
            raise PipelineError("Manifesto de caso fora da raiz preparada.") from exc
        if not manifest_path.is_file() or _hash(manifest_path) != case_record.get("case_manifest_sha256"):
            raise PipelineError(f"Hash do manifesto de caso inconsistente: {case_id}")
        manifest = _load_object(manifest_path, "Manifesto de caso")
        if manifest.get("schema") != CASE_SCHEMA or manifest.get("case_id") != case_id:
            raise PipelineError(f"Schema/case_id inválido no caso {case_id}.")
        case_unsigned = dict(manifest)
        case_signature = str(case_unsigned.pop("case_signature", ""))
        if case_signature != _canonical_hash(case_unsigned) or case_signature != case_record.get("case_signature"):
            raise PipelineError(f"Assinatura de caso inconsistente: {case_id}")
        if manifest.get("lesion_mask_present") is not False or manifest.get("pathology_label_present") is not False:
            raise PipelineError(f"Caso não comprova isolamento de lesão/label: {case_id}")
        files = manifest.get("files")
        if not isinstance(files, list) or {item.get("role") for item in files} != set(ROLE_FILES):
            raise PipelineError(f"Papéis preparados incompletos em {case_id}.")
        images: dict[str, sitk.Image] = {}
        for item in files:
            relative = Path(str(item.get("relative_path") or ""))
            path = (prepared_root / relative).resolve()
            try:
                path.relative_to(prepared_root)
            except ValueError as exc:
                raise PipelineError("Arquivo preparado fora da raiz.") from exc
            if "tumor" in path.name.lower() or "lesion" in path.name.lower():
                raise PipelineError("Arquivo de tumor/lesão presente na inferência.")
            if not path.is_file() or _hash(path) != item.get("sha256"):
                raise PipelineError(f"Arquivo preparado ausente ou alterado: {case_id}/{path.name}")
            if path.stat().st_size != int(item.get("bytes", -1)):
                raise PipelineError(f"Tamanho de arquivo divergente: {case_id}/{path.name}")
            if float(item.get("liver_support_fraction", 0.0)) < 0.95:
                raise PipelineError(f"Cobertura hepática registrada abaixo do gate: {case_id}")
            images[str(item["role"])] = sitk.ReadImage(str(path))
        reference = images["t1_arterial"]
        for role, image in images.items():
            if not _same_geometry(reference, image):
                raise PipelineError(f"Geometria preparada divergente em {case_id}/{role}.")

    if observed_ids != sorted(observed_ids) or len(observed_ids) != len(set(observed_ids)):
        raise PipelineError("Ordem ou unicidade de case_id inválida na coorte preparada.")
    return {
        "schema": "argos-liverhccseg-blind-input-preflight-v1",
        "status": "ready_for_blind_panel_generation",
        "case_count": len(observed_ids),
        "cohort_signature": signature,
        "all_file_hashes_passed": True,
        "all_geometries_passed": True,
        "minimum_liver_support_passed": True,
        "lesion_masks_present": False,
        "pathology_labels_present": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
