"""Multiphase DICOM ingestion for the Etapa C visual benchmark.

The webapp benchmark was single-series: one folder per case, one MR series
chosen by `select_best_mr_series`. The Etapa C classifier instead needs the
three dynamic phases (arterial / venous / delayed) rendered into liver-enriched
multiphase panels, so a case must supply all three.

Since automatic identification of which DICOM series is which dynamic phase is
an unsolved, vendor/protocol-dependent problem (out of scope — see docs/123),
the phase is taken from the FOLDER the files were uploaded under:

    caso-001/arterial/*.dcm
    caso-001/venous/*.dcm
    caso-001/delayed/*.dcm

Two things this module gets right that a naive implementation would miss:

1. **Grid harmonization.** The panel renderer requires every phase and the liver
   mask to share one 3D grid, but separate dynamic acquisitions generally do
   not. Arterial/delayed are resampled onto the venous grid with an identity
   physical transform (same approach as the LLD-MMRI harmonization used to build
   the training data), and the resampled coverage is reported so a
   non-overlapping acquisition fails loudly instead of silently producing a
   mostly-empty phase.
2. **Venous is the reference.** The liver mask comes from segmenting the venous
   phase, so using the segmentation's own emitted volume as the reference grid
   guarantees mask and phases line up by construction.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
import SimpleITK as sitk

from dtwin.core import PipelineError

# Canonical phase names expected by the liver-enriched panel config.
ARTERIAL = "t1_arterial"
VENOUS = "t1_venous"
DELAYED = "t1_delayed"
REQUIRED_PHASES = (ARTERIAL, VENOUS, DELAYED)

# Folder-name aliases -> canonical phase. Matching is case/accent/separator
# tolerant because these folders are named by hand.
_PHASE_ALIASES: dict[str, str] = {
    "arterial": ARTERIAL, "art": ARTERIAL, "arterialphase": ARTERIAL,
    "fasearterial": ARTERIAL, "t1arterial": ARTERIAL, "ap": ARTERIAL,
    "venous": VENOUS, "venoso": VENOUS, "venosa": VENOUS, "portal": VENOUS,
    "portalvenous": VENOUS, "fasevenosa": VENOUS, "t1venous": VENOUS,
    "pv": VENOUS, "vp": VENOUS,
    "delayed": DELAYED, "tardio": DELAYED, "tardia": DELAYED, "late": DELAYED,
    "fasetardia": DELAYED, "t1delayed": DELAYED, "equilibrio": DELAYED,
    "equilibrium": DELAYED,
}

# Minimum fraction of the reference grid that a resampled phase must actually
# cover; below this the acquisitions do not overlap enough to be the same exam.
MINIMUM_COVERAGE = 0.5


def normalize_phase_name(folder_name: str) -> str | None:
    """Map a folder name onto a canonical phase, or None if unrecognized."""
    token = str(folder_name or "").strip().lower()
    token = token.replace("á", "a").replace("â", "a").replace("ã", "a")
    token = token.replace("é", "e").replace("ê", "e").replace("í", "i")
    token = token.replace("ó", "o").replace("ô", "o").replace("õ", "o")
    token = token.replace("ú", "u").replace("ç", "c")
    token = re.sub(r"[^a-z0-9]", "", token)
    return _PHASE_ALIASES.get(token)


def discover_phase_folders(case_dir: Path) -> dict[str, Path]:
    """Find one folder per canonical phase inside an uploaded case directory.

    Searches the case directory recursively so an extra wrapper folder (very
    common when users drag a study folder) does not break detection. Fails
    closed on ambiguity — two folders claiming the same phase is a curation
    error the operator must fix, not something to silently resolve.
    """
    case_dir = Path(case_dir)
    if not case_dir.is_dir():
        raise PipelineError(f"Diretório do caso inexistente: {case_dir}")
    found: dict[str, list[Path]] = {}
    for path in sorted(case_dir.rglob("*")):
        if not path.is_dir():
            continue
        phase = normalize_phase_name(path.name)
        if phase is None:
            continue
        if not any(child.is_file() for child in path.rglob("*")):
            continue
        found.setdefault(phase, []).append(path)
    ambiguous = sorted(name for name, paths in found.items() if len(paths) > 1)
    if ambiguous:
        raise PipelineError(
            f"Fases ambíguas em {case_dir.name}: {ambiguous} — mais de uma pasta por fase."
        )
    missing = [phase for phase in REQUIRED_PHASES if phase not in found]
    if missing:
        raise PipelineError(
            f"Caso {case_dir.name} sem as fases obrigatórias: {missing}. "
            "Organize as pastas como <caso>/arterial, <caso>/venous, <caso>/delayed."
        )
    return {phase: paths[0] for phase, paths in found.items() if phase in REQUIRED_PHASES}


def read_phase_series(phase_dir: Path, *, min_slices: int = 3) -> sitk.Image:
    """Read the best MR series inside a phase folder as a 3D image."""
    from dtwin.benchmark.dataset_audit import select_best_mr_series

    files, frames, _metadata = select_best_mr_series(Path(phase_dir), min_slices=min_slices)
    if not files or frames < min_slices:
        raise PipelineError(
            f"Nenhuma série de RM válida em {phase_dir.name} (mínimo {min_slices} cortes)."
        )
    reader = sitk.ImageSeriesReader()
    reader.SetFileNames([str(path) for path in files])
    image = reader.Execute()
    if image.GetDimension() != 3:
        raise PipelineError(f"Série de {phase_dir.name} não é volumétrica.")
    return image


def harmonize_to_reference(moving: sitk.Image, reference: sitk.Image) -> tuple[sitk.Image, float]:
    """Resample ``moving`` onto ``reference``'s grid with an identity physical
    transform, returning the image and the fraction of the reference grid that
    the moving acquisition actually covers.

    Identity (not registration) is deliberate: it preserves the physical
    positions the scanner recorded, which is the same convention used to build
    the training data. It corrects grid mismatch, not patient motion.
    """
    identity = sitk.Transform(3, sitk.sitkIdentity)
    output = sitk.Resample(
        sitk.Cast(moving, sitk.sitkFloat32), reference, identity,
        sitk.sitkLinear, 0.0, sitk.sitkFloat32,
    )
    support = sitk.Image(moving.GetSize(), sitk.sitkUInt8) + 1
    support.CopyInformation(moving)
    covered = sitk.Resample(
        support, reference, identity, sitk.sitkNearestNeighbor, 0, sitk.sitkUInt8
    )
    coverage = float(np.count_nonzero(sitk.GetArrayViewFromImage(covered))) / float(
        np.prod(reference.GetSize())
    )
    return output, coverage


@dataclass(frozen=True)
class MultiphaseCase:
    case_id: str
    phase_paths: dict[str, Path]
    coarse_liver_mask_path: Path
    coverage: dict[str, float]


def build_multiphase_case(
    *,
    case_id: str,
    case_upload_dir: Path,
    output_dir: Path,
    segment_venous: Callable[[Path, Path], Path],
    minimum_coverage: float = MINIMUM_COVERAGE,
) -> MultiphaseCase:
    """Turn an uploaded multiphase case folder into panel-ready inputs.

    ``segment_venous(venous_dicom_dir, case_work_dir)`` must run the existing
    segmentation and return the directory holding ``volume.nii.gz`` (the
    ingested venous volume, which becomes the reference grid) and
    ``mask_organ.nii.gz``. Injecting it keeps this module testable and avoids
    duplicating the webapp's GPU/CPU fallback logic.
    """
    phase_dirs = discover_phase_folders(Path(case_upload_dir))
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    segmented_dir = Path(segment_venous(phase_dirs[VENOUS], output_dir / "segmentation"))
    reference_path = segmented_dir / "volume.nii.gz"
    mask_path = segmented_dir / "mask_organ.nii.gz"
    for path, label in ((reference_path, "volume venoso"), (mask_path, "máscara hepática")):
        if not path.is_file():
            raise PipelineError(f"Segmentação não produziu {label}: {path}")
    reference = sitk.ReadImage(str(reference_path))

    phase_paths: dict[str, Path] = {VENOUS: reference_path}
    coverage: dict[str, float] = {VENOUS: 1.0}
    for phase in (ARTERIAL, DELAYED):
        image = read_phase_series(phase_dirs[phase])
        harmonized, covered = harmonize_to_reference(image, reference)
        if covered < float(minimum_coverage):
            raise PipelineError(
                f"Fase {phase} cobre apenas {100*covered:.1f}% da grade de referência "
                f"(mínimo {100*float(minimum_coverage):.0f}%) — aquisições não correspondem."
            )
        destination = output_dir / f"{phase}.nii.gz"
        sitk.WriteImage(harmonized, str(destination))
        phase_paths[phase] = destination
        coverage[phase] = covered

    return MultiphaseCase(
        case_id=str(case_id),
        phase_paths=phase_paths,
        coarse_liver_mask_path=mask_path,
        coverage=coverage,
    )
