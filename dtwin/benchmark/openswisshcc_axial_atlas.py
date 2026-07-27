"""Atlas axial cego v17 para o desenvolvimento OpenSwissHCC.

O atlas apenas reorganiza tiles axiais de painéis volumétricos previamente
gerados. Ele não abre labels, máscaras de lesão ou o holdout.
"""
from __future__ import annotations

import hashlib
import html
import json
import gc
import os
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from PIL import Image

from dtwin.core import PipelineError


ALGORITHM_VERSION = "openswisshcc-axial-atlas-v17"
CASE_SCHEMA = "argos-openswisshcc-axial-atlas-case-v17"
COHORT_SCHEMA = "argos-openswisshcc-axial-atlas-cohort-v17"
GALLERY_SCHEMA = "argos-openswisshcc-axial-atlas-gallery-v17"
REVIEW_SCHEMA = "argos-openswisshcc-axial-atlas-review-v17"
SOURCE_CANDIDATE_VERSION = "openswisshcc-volumetric-choice-pathology-v1"
SOURCE_PANEL_SCHEMA = "dtwin-medgemma-panel-set-v2"
TILE_SIZE = 384
ALLOWED_SOURCE_TILE_SIZES = (320, 384)
FRAME_GRID = 2
TILES_PER_FRAME = FRAME_GRID * FRAME_GRID
FRAME_SIZE = TILE_SIZE * FRAME_GRID
MAX_FRAMES = 32
REQUIRED_REVIEW_CONFIRMATIONS = (
    "all_frames_reviewed",
    "axial_sequence_coherent",
    "liver_not_cropped",
    "multiphase_readable",
    "venous_fallback_readable",
    "black_padding_only_terminal",
    "no_phi_or_lesion_overlay",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _pixel_sha256(image: Image.Image) -> str:
    digest = hashlib.sha256()
    digest.update(image.mode.encode("ascii"))
    digest.update(str(image.size).encode("ascii"))
    digest.update(image.tobytes())
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON inválido ou ilegível: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PipelineError(f"Objeto JSON esperado em {path}.")
    return payload


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _publish_directory(
    staging: Path, destination: Path, *, attempts: int = 12, base_delay: float = 0.25
) -> None:
    """Publica diretório atomicamente, tolerando locks transitórios do Windows."""
    if attempts < 1:
        raise PipelineError("Número de tentativas de publicação deve ser positivo.")
    if destination.exists():
        raise PipelineError(f"Destino de publicação já existe: {destination}.")
    last_error: PermissionError | None = None
    for attempt in range(attempts):
        try:
            os.replace(staging, destination)
            return
        except PermissionError as exc:
            last_error = exc
            if destination.exists():
                raise PipelineError(
                    f"Destino apareceu durante publicação atômica: {destination}."
                ) from exc
            gc.collect()
            if attempt + 1 < attempts:
                time.sleep(min(base_delay * (2**attempt), 1.0))
    assert last_error is not None
    raise last_error


def _protocol() -> dict[str, Any]:
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "source_candidate_version": SOURCE_CANDIDATE_VERSION,
        "source_panel_schema": SOURCE_PANEL_SCHEMA,
        "source_tile_sizes_allowed": list(ALLOWED_SOURCE_TILE_SIZES),
        "frame_grid": [FRAME_GRID, FRAME_GRID],
        "tiles_per_frame": TILES_PER_FRAME,
        "maximum_frame_size": [FRAME_SIZE, FRAME_SIZE],
        "maximum_frames": MAX_FRAMES,
        "ordering": "ascending_axial_index_exactly_once",
        "medical_pixel_transform": "lossless_crop_and_repack_only",
        "ground_truth_allowed": False,
        "lesion_mask_allowed": False,
        "holdout_allowed": False,
    }


PROTOCOL_SIGNATURE = _canonical_sha256(_protocol())


def _validate_case_id(case_id: str) -> None:
    if not case_id.startswith("anon-openswiss-") or any(
        token in case_id.lower() for token in ("holdout", "label", "truth")
    ):
        raise PipelineError(f"case_id não autorizado para o atlas v17: {case_id!r}.")


def _validate_source(
    source_case_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    candidate_path = source_case_dir / "candidate_manifest.json"
    panel_manifest_path = source_case_dir / "medgemma_liver_screening_manifest.json"
    candidate = _load_json(candidate_path)
    panel_manifest = _load_json(panel_manifest_path)

    case_id = str(candidate.get("case_id", ""))
    _validate_case_id(case_id)
    if source_case_dir.name != case_id:
        raise PipelineError("Diretório e case_id do candidato-fonte não coincidem.")
    if candidate.get("candidate_version") != SOURCE_CANDIDATE_VERSION:
        raise PipelineError("Versão do candidato-fonte não autorizada para v17.")
    if candidate.get("panel_strategy") != "volumetric_blocks":
        raise PipelineError("v17 exige painéis-fonte volumetric_blocks.")
    if candidate.get("ground_truth_read") is not False:
        raise PipelineError("Candidato-fonte não prova isolamento do ground truth.")
    if panel_manifest.get("schema_version") != SOURCE_PANEL_SCHEMA:
        raise PipelineError("Schema do manifesto de painéis-fonte incompatível.")
    if panel_manifest.get("case_id") != case_id:
        raise PipelineError("case_id diverge entre manifestos-fonte.")
    if panel_manifest.get("lesion_pre_marked") is not False:
        raise PipelineError("Painel com lesão pré-marcada não é permitido.")
    if panel_manifest.get("panel_strategy") != "volumetric_blocks":
        raise PipelineError("Manifesto-fonte não é volumetric_blocks.")

    coverage = candidate.get("coverage")
    if not isinstance(coverage, dict):
        raise PipelineError("Cobertura-fonte ausente.")
    expected = [int(index) for index in coverage.get("expected_axial_indices", [])]
    if not expected or expected != sorted(set(expected)):
        raise PipelineError("Índices axiais esperados inválidos ou duplicados.")
    if (
        coverage.get("gate_passed") is not True
        or coverage.get("missing_axial_indices") != []
        or coverage.get("duplicate_axial_indices") != []
        or int(coverage.get("covered_liver_voxels", -1))
        != int(coverage.get("total_liver_voxels", -2))
    ):
        raise PipelineError("Gate de cobertura-fonte não prova 100% exatos.")

    candidate_panels = candidate.get("panels")
    manifest_panels = panel_manifest.get("panels")
    if not isinstance(candidate_panels, list) or not isinstance(manifest_panels, list):
        raise PipelineError("Coleção de painéis-fonte ausente.")
    candidate_by_number = {int(panel["panel_number"]): panel for panel in candidate_panels}
    if len(candidate_by_number) != len(candidate_panels):
        raise PipelineError("Número de painel-fonte duplicado.")

    axial_tiles: list[dict[str, Any]] = []
    for panel in manifest_panels:
        number = int(panel.get("panel_number", -1))
        candidate_panel = candidate_by_number.get(number)
        if candidate_panel is None:
            raise PipelineError(f"Painel {number} ausente no candidato-fonte.")
        filename = str(panel.get("image", ""))
        if not filename or Path(filename).name != filename:
            raise PipelineError("Nome de painel-fonte inseguro.")
        if candidate_panel.get("image") != filename:
            raise PipelineError("Nome de painel diverge entre manifestos-fonte.")
        image_path = source_case_dir / filename
        expected_hash = str(panel.get("sha256", ""))
        if expected_hash != candidate_panel.get("sha256") or _sha256(image_path) != expected_hash:
            raise PipelineError(f"Hash inconsistente no painel-fonte {filename}.")

        tiles = panel.get("tiles")
        if not isinstance(tiles, list):
            raise PipelineError(f"Tiles ausentes no painel-fonte {number}.")
        for tile in tiles:
            if tile.get("orientation") != "axial" or tile.get(
                "counts_toward_coverage"
            ) is not True:
                continue
            tile_number = int(tile.get("tile_number", -1))
            if not 1 <= tile_number <= 9:
                raise PipelineError("Posição axial fora da grade 3x3 do painel-fonte.")
            axial_tiles.append(
                {
                    "axial_index": int(tile["index"]),
                    "relative_position_percent": float(
                        tile["relative_position_percent"]
                    ),
                    "liver_voxels_in_plane": int(tile["liver_voxels_in_plane"]),
                    "liver_volume_percent": float(tile["liver_volume_percent"]),
                    "source_panel_number": number,
                    "source_panel_filename": filename,
                    "source_panel_sha256": expected_hash,
                    "source_tile_number": tile_number,
                }
            )

    axial_tiles.sort(key=lambda item: item["axial_index"])
    actual = [tile["axial_index"] for tile in axial_tiles]
    if actual != expected:
        missing = sorted(set(expected) - set(actual))
        duplicates = sorted({index for index in actual if actual.count(index) > 1})
        raise PipelineError(
            f"Tiles axiais não representam o intervalo esperado: missing={missing}, "
            f"duplicates={duplicates}."
        )
    return candidate, panel_manifest, axial_tiles


def _source_tile_size(source_case_dir: Path, axial_tiles: Sequence[Mapping[str, Any]]) -> int:
    sizes: set[int] = set()
    checked: set[str] = set()
    for tile in axial_tiles:
        filename = str(tile["source_panel_filename"])
        if filename in checked:
            continue
        checked.add(filename)
        with Image.open(source_case_dir / filename) as source:
            width, height = source.size
        if width % 4 or height % 3 or width // 4 != height // 3:
            raise PipelineError(
                f"Grade 4x3 inválida no painel-fonte {filename}: {(width, height)}."
            )
        sizes.add(width // 4)
    if len(sizes) != 1:
        raise PipelineError(f"Resolução de tile varia dentro do caso: {sorted(sizes)}.")
    tile_size = next(iter(sizes))
    if tile_size not in ALLOWED_SOURCE_TILE_SIZES:
        raise PipelineError(
            f"Resolução de tile-fonte não autorizada: {tile_size}; "
            f"permitidas={list(ALLOWED_SOURCE_TILE_SIZES)}."
        )
    return tile_size


def _crop_source_tile(
    source_case_dir: Path, tile: Mapping[str, Any], tile_size: int
) -> Image.Image:
    image_path = source_case_dir / str(tile["source_panel_filename"])
    with Image.open(image_path) as source:
        source.load()
        if source.size != (tile_size * 4, tile_size * 3):
            raise PipelineError(
                f"Dimensão inesperada em {image_path.name}: {source.size}."
            )
        position = int(tile["source_tile_number"]) - 1
        column, row = position % 3, position // 3
        box = (
            column * tile_size,
            row * tile_size,
            (column + 1) * tile_size,
            (row + 1) * tile_size,
        )
        cropped = source.convert("RGB").crop(box)
    if cropped.size != (tile_size, tile_size):
        raise PipelineError("Crop axial resultou em dimensão incorreta.")
    return cropped


def build_axial_atlas_case(source_case_dir: Path, output_root: Path) -> dict[str, Any]:
    """Gera atomicamente um atlas v17 para um caso de desenvolvimento."""
    source_case_dir = Path(source_case_dir).resolve()
    output_root = Path(output_root).resolve()
    candidate, panel_manifest, axial_tiles = _validate_source(source_case_dir)
    case_id = str(candidate["case_id"])
    destination = output_root / case_id
    if destination.exists():
        raise PipelineError(f"Destino v17 já existe: {destination}.")
    frame_count = (len(axial_tiles) + TILES_PER_FRAME - 1) // TILES_PER_FRAME
    if frame_count > MAX_FRAMES:
        raise PipelineError(
            f"Caso exige {frame_count} frames; limite congelado é {MAX_FRAMES}."
        )

    tile_size = _source_tile_size(source_case_dir, axial_tiles)
    frame_size = tile_size * FRAME_GRID
    output_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{case_id}.v17-", dir=output_root))
    frames: list[dict[str, Any]] = []
    represented_indices: list[int] = []
    try:
        for frame_offset in range(frame_count):
            subset = axial_tiles[
                frame_offset * TILES_PER_FRAME : (frame_offset + 1) * TILES_PER_FRAME
            ]
            frame_number = frame_offset + 1
            filename = f"axial_atlas_frame_{frame_number:03d}_of_{frame_count:03d}.png"
            canvas = Image.new("RGB", (frame_size, frame_size), color=(0, 0, 0))
            frame_tiles: list[dict[str, Any]] = []
            for quadrant in range(TILES_PER_FRAME):
                column, row = quadrant % FRAME_GRID, quadrant // FRAME_GRID
                if quadrant >= len(subset):
                    frame_tiles.append(
                        {"quadrant": quadrant + 1, "empty": True, "counts_toward_coverage": False}
                    )
                    continue
                tile = subset[quadrant]
                crop = _crop_source_tile(source_case_dir, tile, tile_size)
                canvas.paste(crop, (column * tile_size, row * tile_size))
                source_position = int(tile["source_tile_number"]) - 1
                source_column, source_row = source_position % 3, source_position // 3
                record = dict(tile)
                record.update(
                    {
                        "quadrant": quadrant + 1,
                        "empty": False,
                        "counts_toward_coverage": True,
                        "source_crop_box": [
                            source_column * tile_size,
                            source_row * tile_size,
                            (source_column + 1) * tile_size,
                            (source_row + 1) * tile_size,
                        ],
                        "tile_pixel_sha256": _pixel_sha256(crop),
                    }
                )
                frame_tiles.append(record)
                represented_indices.append(int(tile["axial_index"]))
            frame_path = staging / filename
            canvas.save(frame_path, format="PNG", optimize=False)
            frames.append(
                {
                    "frame_number": frame_number,
                    "frame_total": frame_count,
                    "image": filename,
                    "sha256": _sha256(frame_path),
                    "bytes": frame_path.stat().st_size,
                    "size_pixels": [frame_size, frame_size],
                    "axial_interval": [subset[0]["axial_index"], subset[-1]["axial_index"]],
                    "tiles": frame_tiles,
                }
            )

        expected = [int(index) for index in candidate["coverage"]["expected_axial_indices"]]
        missing = sorted(set(expected) - set(represented_indices))
        duplicates = sorted(
            {index for index in represented_indices if represented_indices.count(index) > 1}
        )
        gate_passed = represented_indices == expected and not missing and not duplicates
        if not gate_passed:
            raise PipelineError(
                f"Gate v17 falhou: missing={missing}, duplicates={duplicates}."
            )
        frame_hashes = [frame["sha256"] for frame in frames]
        manifest = {
            "schema_version": CASE_SCHEMA,
            "algorithm_version": ALGORITHM_VERSION,
            "protocol_signature": PROTOCOL_SIGNATURE,
            "case_id": case_id,
            "research_only": True,
            "clinical_use_allowed": False,
            "ground_truth_read": False,
            "lesion_mask_read": False,
            "holdout_read": False,
            "eligible_for_inference": False,
            "source": {
                "candidate_version": candidate["candidate_version"],
                "candidate_signature": candidate.get("candidate_signature"),
                "candidate_manifest_sha256": _sha256(source_case_dir / "candidate_manifest.json"),
                "panel_manifest_sha256": _sha256(
                    source_case_dir / "medgemma_liver_screening_manifest.json"
                ),
                "panel_set_sha256": candidate.get("panel_set_sha256"),
                "candidate_kind": candidate.get("candidate_kind"),
                "panel_schema": panel_manifest.get("schema_version"),
            },
            "atlas": {
                "layout": "2x2_axial",
                "tile_size_pixels": [tile_size, tile_size],
                "frame_size_pixels": [frame_size, frame_size],
                "tile_count": len(axial_tiles),
                "frame_count": frame_count,
                "maximum_frames": MAX_FRAMES,
                "expected_axial_indices": expected,
                "represented_axial_indices": represented_indices,
                "missing_axial_indices": missing,
                "duplicate_axial_indices": duplicates,
                "coverage_percent": 100.0,
                "gate_rule": "represented_axial_indices == expected_axial_indices exactly once",
                "gate_passed": gate_passed,
                "atlas_set_sha256": _canonical_sha256(frame_hashes),
            },
            "frames": frames,
        }
        _write_json(staging / "axial_atlas_manifest.json", manifest)
        _publish_directory(staging, destination)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def build_axial_atlas_cohort(
    source_root: Path, output_root: Path, case_ids: Iterable[str]
) -> dict[str, Any]:
    """Gera um coorte explicitamente enumerado, sem descobrir casos ocultos."""
    source_root = Path(source_root).resolve()
    output_root = Path(output_root).resolve()
    normalized = [str(case_id) for case_id in case_ids]
    if not normalized or len(normalized) != len(set(normalized)):
        raise PipelineError("Lista de casos v17 vazia ou duplicada.")
    for case_id in normalized:
        _validate_case_id(case_id)
    if output_root.exists():
        raise PipelineError(f"Destino de coorte v17 já existe: {output_root}.")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".v17-cohort-", dir=output_root.parent))
    manifests: list[dict[str, Any]] = []
    try:
        for case_id in normalized:
            manifests.append(build_axial_atlas_case(source_root / case_id, staging))
        records = [
            {
                "case_id": manifest["case_id"],
                "manifest": f"{manifest['case_id']}/axial_atlas_manifest.json",
                "manifest_sha256": _sha256(
                    staging / manifest["case_id"] / "axial_atlas_manifest.json"
                ),
                "frame_count": manifest["atlas"]["frame_count"],
                "tile_count": manifest["atlas"]["tile_count"],
                "atlas_set_sha256": manifest["atlas"]["atlas_set_sha256"],
                "source_candidate_kind": manifest["source"]["candidate_kind"],
                "gate_passed": manifest["atlas"]["gate_passed"],
            }
            for manifest in manifests
        ]
        cohort = {
            "schema_version": COHORT_SCHEMA,
            "algorithm_version": ALGORITHM_VERSION,
            "protocol": _protocol(),
            "protocol_signature": PROTOCOL_SIGNATURE,
            "case_count": len(records),
            "frame_count": sum(record["frame_count"] for record in records),
            "tile_count": sum(record["tile_count"] for record in records),
            "ground_truth_read": False,
            "lesion_mask_read": False,
            "holdout_read": False,
            "eligible_for_inference": False,
            "all_gates_passed": all(record["gate_passed"] for record in records),
            "cases": records,
        }
        _write_json(staging / "cohort_manifest.json", cohort)
        _publish_directory(staging, output_root)
        return cohort
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def build_axial_atlas_gallery(atlas_root: Path, gallery_root: Path) -> dict[str, Any]:
    """Publica galeria sem labels, copiando apenas frames e manifestos v17."""
    atlas_root = Path(atlas_root).resolve()
    gallery_root = Path(gallery_root).resolve()
    cohort = _load_json(atlas_root / "cohort_manifest.json")
    if cohort.get("schema_version") != COHORT_SCHEMA:
        raise PipelineError("Coorte v17 incompatível para galeria.")
    if gallery_root.exists():
        raise PipelineError(f"Galeria já existe: {gallery_root}.")
    gallery_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".v17-gallery-", dir=gallery_root.parent))
    gallery_cases: list[dict[str, Any]] = []
    try:
        cards: list[str] = []
        for ordinal, record in enumerate(cohort["cases"], start=1):
            case_id = str(record["case_id"])
            manifest_path = atlas_root / str(record["manifest"])
            if _sha256(manifest_path) != record["manifest_sha256"]:
                raise PipelineError(f"Manifesto v17 alterado para {case_id}.")
            manifest = _load_json(manifest_path)
            case_output = staging / case_id
            case_output.mkdir()
            frame_html: list[str] = []
            copied_frames: list[dict[str, Any]] = []
            for frame in manifest["frames"]:
                source = atlas_root / case_id / str(frame["image"])
                if _sha256(source) != frame["sha256"]:
                    raise PipelineError(f"Frame v17 alterado: {source}.")
                target = case_output / source.name
                shutil.copyfile(source, target)
                copied_frames.append(
                    {"image": f"{case_id}/{source.name}", "sha256": _sha256(target)}
                )
                interval = frame["axial_interval"]
                frame_html.append(
                    f'<figure><img loading="lazy" src="{html.escape(source.name)}" '
                    f'alt="frame {frame["frame_number"]}"><figcaption>Frame '
                    f'{frame["frame_number"]}/{frame["frame_total"]} · cortes '
                    f'{interval[0]}–{interval[1]}</figcaption></figure>'
                )
            page = (
                "<!doctype html><meta charset='utf-8'><title>Atlas v17</title>"
                "<style>body{background:#111;color:#eee;font:16px sans-serif;margin:24px}"
                "a{color:#8fd3ff} .frames{display:grid;grid-template-columns:repeat(auto-fit,minmax("
                "520px,1fr));gap:20px}figure{margin:0;background:#222;padding:10px}"
                "img{width:100%;height:auto;image-rendering:auto}figcaption{padding-top:8px}</style>"
                f"<p><a href='../index.html'>← índice</a></p><h1>{ordinal}. "
                f"{html.escape(case_id)}</h1><p>Revisar todos os frames; quadrantes pretos no "
                "último frame são preenchimento autorizado.</p><div class='frames'>"
                + "".join(frame_html)
                + "</div>"
            )
            (case_output / "index.html").write_text(page, encoding="utf-8")
            cards.append(
                f'<li><a href="{html.escape(case_id)}/index.html">{ordinal}. '
                f'{html.escape(case_id)}</a> — {record["frame_count"]} frames, '
                f'{record["tile_count"]} cortes</li>'
            )
            gallery_cases.append(
                {"ordinal": ordinal, "case_id": case_id, "frames": copied_frames}
            )
        index = (
            "<!doctype html><meta charset='utf-8'><title>Revisão v17 — atlas axial</title>"
            "<style>body{max-width:1050px;margin:36px auto;background:#111;color:#eee;"
            "font:17px/1.5 sans-serif}a{color:#8fd3ff}li{margin:9px 0}</style>"
            "<h1>OpenSwissHCC desenvolvimento — piloto cego v17</h1>"
            "<p>Objetivo: confirmar sequência axial completa em atlas 2×2, legibilidade, "
            "ausência de cortes truncados e ausência de PHI/marcação de lesão. Não há labels "
            "nesta galeria.</p><ol>" + "".join(cards) + "</ol>"
        )
        (staging / "index.html").write_text(index, encoding="utf-8")
        gallery = {
            "schema_version": GALLERY_SCHEMA,
            "protocol_signature": PROTOCOL_SIGNATURE,
            "case_count": len(gallery_cases),
            "ground_truth_read": False,
            "lesion_mask_read": False,
            "holdout_read": False,
            "review_status": "pending_human_review",
            "cases": gallery_cases,
        }
        _write_json(staging / "gallery_manifest.json", gallery)
        _publish_directory(staging, gallery_root)
        return gallery
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def case_ids_from_cohort_manifest(path: Path) -> Sequence[str]:
    payload = _load_json(Path(path))
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise PipelineError("Coorte piloto sem lista de casos.")
    result: list[str] = []
    for item in cases:
        case_id = item if isinstance(item, str) else item.get("case_id")
        if not isinstance(case_id, str):
            raise PipelineError("Entrada de caso inválida no coorte piloto.")
        _validate_case_id(case_id)
        result.append(case_id)
    return result


def record_axial_atlas_review(
    *,
    gallery_root: Path,
    out_path: Path,
    reviewer: str,
    confirmations: Mapping[str, bool],
    approved: bool,
    notes: str = "",
    approval_scope: str = "full87_generation",
    reviewed_at_utc: str | None = None,
) -> dict[str, Any]:
    """Registra uma decisão humana assinada e vinculada aos hashes da galeria."""
    gallery_root = Path(gallery_root).resolve()
    out_path = Path(out_path).resolve()
    reviewer = str(reviewer).strip()
    notes = str(notes).strip()
    approval_scope = str(approval_scope).strip()
    status_by_scope = {
        "full87_generation": "approved_for_full87_generation",
        "blind_4b_scoring": "approved_for_blind_4b_scoring",
    }
    if approval_scope not in status_by_scope:
        raise PipelineError("Escopo da revisão v17 não autorizado.")
    if not reviewer or len(reviewer) > 120:
        raise PipelineError("Identificação do revisor v17 ausente ou longa demais.")
    if set(confirmations) != set(REQUIRED_REVIEW_CONFIRMATIONS) or any(
        type(value) is not bool for value in confirmations.values()
    ):
        raise PipelineError("Confirmações da revisão v17 incompletas ou inválidas.")
    if approved and not all(confirmations.values()):
        raise PipelineError("Aprovação v17 exige todas as confirmações explícitas.")
    if not approved and not notes:
        raise PipelineError("Reprovação v17 exige observação objetiva.")
    if out_path.exists():
        raise PipelineError("Registro de revisão v17 já existe; sobrescrita recusada.")

    gallery_path = gallery_root / "gallery_manifest.json"
    gallery = _load_json(gallery_path)
    if gallery.get("schema_version") != GALLERY_SCHEMA:
        raise PipelineError("Schema da galeria v17 incompatível.")
    if (
        gallery.get("ground_truth_read") is not False
        or gallery.get("lesion_mask_read") is not False
        or gallery.get("holdout_read") is not False
    ):
        raise PipelineError("Galeria v17 não preserva as salvaguardas cegas.")
    cases = gallery.get("cases")
    if not isinstance(cases, list) or len(cases) != int(gallery.get("case_count", -1)):
        raise PipelineError("Lista de casos da galeria v17 inválida.")
    seen: set[str] = set()
    frame_count = 0
    for case in cases:
        case_id = str(case.get("case_id", ""))
        _validate_case_id(case_id)
        if case_id in seen:
            raise PipelineError("Caso duplicado na galeria v17.")
        seen.add(case_id)
        frames = case.get("frames")
        if not isinstance(frames, list) or not frames:
            raise PipelineError(f"Caso sem frames na galeria v17: {case_id}.")
        for frame in frames:
            relative = Path(str(frame.get("image", "")))
            if relative.is_absolute() or ".." in relative.parts:
                raise PipelineError("Caminho inseguro em frame da galeria v17.")
            path = gallery_root / relative
            if _sha256(path) != frame.get("sha256"):
                raise PipelineError(f"Hash alterado na galeria v17: {relative}.")
            frame_count += 1

    timestamp = reviewed_at_utc or datetime.now(timezone.utc).isoformat()
    if not isinstance(timestamp, str) or not timestamp.strip():
        raise PipelineError("Data UTC da revisão v17 inválida.")
    review = {
        "schema_version": REVIEW_SCHEMA,
        "status": (
            status_by_scope[approval_scope]
            if approved
            else "rejected_technical_review"
        ),
        "approval_scope": approval_scope,
        "reviewer": reviewer,
        "reviewed_at_utc": timestamp,
        "confirmations": {
            key: bool(confirmations[key]) for key in REQUIRED_REVIEW_CONFIRMATIONS
        },
        "notes": notes,
        "protocol_signature": gallery.get("protocol_signature"),
        "gallery_manifest_sha256": _sha256(gallery_path),
        "case_count": len(cases),
        "frame_count": frame_count,
        "ground_truth_read": False,
        "lesion_mask_read": False,
        "holdout_read": False,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    review["review_signature"] = _canonical_sha256(review)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{out_path.name}.", suffix=".tmp", dir=out_path.parent
    )
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        _write_json(temporary, review)
        os.replace(temporary, out_path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return review
