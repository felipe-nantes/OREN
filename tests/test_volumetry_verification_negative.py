"""Testes negativos de ``verify_volumetry_artifacts`` (PHASE_07 sobrevivente S1).

Cada braço fail-closed do verificador independente é disparado por uma
corrupção dirigida de um par manifesto+CSV válido e 100% sintético —
inclusive a checagem física do GEO-004 (volume = voxels × spacing / 1000).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from dtwin.core import PipelineError
from dtwin.volumetry import (
    VOLUMETRY_CONTRACT,
    VOLUMETRY_CSV_NAME,
    VOLUMETRY_JSON_NAME,
    VOLUMETRY_SCHEMA,
    verify_volumetry_artifacts,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _structures() -> list[dict]:
    # volume_ml coerente com voxel_count x voxel_volume_mm3 / 1000 (GEO-004)
    return [
        {"role": "figado_total", "voxel_count": 1000,
         "voxel_volume_mm3": 1.5, "volume_ml": 1.5},
        {"role": "segmento_ii", "voxel_count": 200,
         "voxel_volume_mm3": 1.5, "volume_ml": 0.3},
    ]


def _csv_texto(rows: list[tuple[str, float]]) -> str:
    corpo = "".join(f"{role},{volume}\n" for role, volume in rows)
    return "role,volume_ml\n" + corpo


def _write_pair(
    output: Path,
    *,
    structures: list[dict] | None = None,
    csv_rows: list[tuple[str, float]] | None = None,
    couinaud: dict | None = None,
    mutate_manifest=None,
    stale_hash: bool = False,
) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    structures = _structures() if structures is None else structures
    if csv_rows is None:
        csv_rows = [(s["role"], s["volume_ml"]) for s in structures]
    csv_path = output / VOLUMETRY_CSV_NAME
    csv_path.write_text(_csv_texto(csv_rows), encoding="utf-8", newline="")
    manifest = {
        "schema": VOLUMETRY_SCHEMA,
        "contract": VOLUMETRY_CONTRACT,
        "artifacts": {
            "csv_sha256": "0" * 64 if stale_hash else _sha256(csv_path)
        },
        "structures": structures,
        "couinaud_partition": couinaud or {},
    }
    if mutate_manifest is not None:
        mutate_manifest(manifest)
    (output / VOLUMETRY_JSON_NAME).write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return output


def test_par_sintetico_valido_e_verificado(tmp_path):
    resultado = verify_volumetry_artifacts(_write_pair(tmp_path / "out"))
    assert resultado["status"] == "verified"
    assert resultado["structure_count"] == 2


def test_rejeita_artefatos_incompletos(tmp_path):
    output = _write_pair(tmp_path / "out")
    (output / VOLUMETRY_CSV_NAME).unlink()
    with pytest.raises(PipelineError, match="incompletos"):
        verify_volumetry_artifacts(output)


def test_rejeita_manifesto_ilegivel(tmp_path):
    output = _write_pair(tmp_path / "out")
    (output / VOLUMETRY_JSON_NAME).write_text("{quebrado", encoding="utf-8")
    with pytest.raises(PipelineError, match="invalido"):
        verify_volumetry_artifacts(output)


@pytest.mark.parametrize("campo", ["schema", "contract"])
def test_rejeita_schema_ou_contrato_incompativel(tmp_path, campo):
    def corromper(manifest):
        manifest[campo] = "desconhecido-v0"

    output = _write_pair(tmp_path / "out", mutate_manifest=corromper)
    with pytest.raises(PipelineError, match="incompativel"):
        verify_volumetry_artifacts(output)


def test_rejeita_hash_de_csv_inconsistente(tmp_path):
    output = _write_pair(tmp_path / "out", stale_hash=True)
    with pytest.raises(PipelineError, match="inconsistente"):
        verify_volumetry_artifacts(output)


def test_rejeita_contagens_divergentes_entre_csv_e_json(tmp_path):
    output = _write_pair(
        tmp_path / "out", csv_rows=[("figado_total", 1.5)]
    )
    with pytest.raises(PipelineError, match="quantidades"):
        verify_volumetry_artifacts(output)


def test_rejeita_papel_duplicado_no_manifesto(tmp_path):
    duplicado = [_structures()[0], dict(_structures()[0])]
    output = _write_pair(
        tmp_path / "out",
        structures=duplicado,
        csv_rows=[("figado_total", 1.5), ("figado_total", 1.5)],
    )
    with pytest.raises(PipelineError, match="duplicados"):
        verify_volumetry_artifacts(output)


def test_rejeita_estrutura_do_csv_ausente_no_json(tmp_path):
    output = _write_pair(
        tmp_path / "out",
        csv_rows=[("figado_total", 1.5), ("papel_fantasma", 0.3)],
    )
    with pytest.raises(PipelineError, match="ausente no JSON"):
        verify_volumetry_artifacts(output)


def test_geo004_rejeita_volume_json_divergente_da_contagem_fisica(tmp_path):
    def corromper(manifest):
        manifest["structures"][0]["volume_ml"] = 9.99

    output = _write_pair(tmp_path / "out", mutate_manifest=corromper)
    with pytest.raises(PipelineError, match="Volume JSON nao corresponde"):
        verify_volumetry_artifacts(output)


def test_geo004_rejeita_volume_csv_divergente_da_contagem_fisica(tmp_path):
    output = _write_pair(
        tmp_path / "out",
        csv_rows=[("figado_total", 9.99), ("segmento_ii", 0.3)],
    )
    with pytest.raises(PipelineError, match="Volume CSV nao corresponde"):
        verify_volumetry_artifacts(output)


def test_rejeita_gate_couinaud_aprovado_sem_particao_exata(tmp_path):
    output = _write_pair(
        tmp_path / "out",
        couinaud={
            "gate_passed": True,
            "actual_segment_count": 7,
            "missing_liver_voxels": 0,
            "overlapping_segment_voxels": 0,
            "segment_voxels_outside_liver": 0,
        },
    )
    with pytest.raises(PipelineError, match="sem particao exata"):
        verify_volumetry_artifacts(output)
