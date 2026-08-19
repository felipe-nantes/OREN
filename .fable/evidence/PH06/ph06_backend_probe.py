"""PHASE_06 wave 2 — sonda deterministica de backend.

Computa as mesmas quantidades cientificas nos dois backends (host py3.13 vs
container py3.11/CUDA-image) e emite JSON canonico com floats em repr()
completo, separando LOGIC (deve ser IDENTICO) de NUMERICAL (delta medido).
Nenhuma GPU e usada: o alvo sao as bibliotecas CPU (numpy/sitk/python)."""
import json
import platform
import sys

import numpy as np
import SimpleITK as sitk

from dtwin.benchmark.metrics import wilson_interval
from dtwin.learning.protocol import canonical_sha256
from dtwin.learning.schemas import ProtectedTrainingCase
from dtwin.learning.splits import build_nested_splits
from dtwin.learning.multiphase_ingest import harmonize_to_reference
from dtwin.volumetry import measure_mask, VolumetryStructure
from pathlib import Path
import tempfile

saida = {"environment": {
    "python": sys.version.split()[0],
    "platform": platform.platform(),
    "numpy": np.__version__,
    "simpleitk": sitk.Version_VersionString(),
}}

# ---------- LOGIC: splits (python puro + hashlib) ----------
casos = []
for label, prefixo in (("POSITIVE", "pos"), ("NEGATIVE", "neg")):
    for i in range(12):
        casos.append(ProtectedTrainingCase(
            case_id=f"{prefixo}_{i:02d}_e0", patient_group_id=f"{prefixo}_{i:02d}",
            dataset_id="probe", label=label))
splits = build_nested_splits(casos, outer_folds=4, inner_folds=3, seed=20260724)
saida["logic_splits_sha256"] = canonical_sha256(splits)

# ---------- NUMERICAL: wilson ----------
grade = [(0, 50), (1, 10), (81, 263), (220, 467), (500, 1000), (466, 467)]
saida["numerical_wilson"] = {
    f"{k}/{n}": {kk: repr(vv) for kk, vv in wilson_interval(k, n).items()}
    for k, n in grade
}

# ---------- NUMERICAL: volumetria em phantom anisotropico ----------
def esfera(shape, centro, raio):
    zz, yy, xx = np.ogrid[: shape[0], : shape[1], : shape[2]]
    d2 = (zz - centro[0]) ** 2 + (yy - centro[1]) ** 2 + (xx - centro[2]) ** 2
    return (d2 <= raio * raio).astype(np.uint8)

arr = esfera((40, 40, 40), (20, 20, 20), 12)
img = sitk.GetImageFromArray(arr)
img.SetSpacing((0.7, 1.3, 2.9))       # anisotropico de proposito
img.SetOrigin((-11.5, 3.25, 100.125))
tmp = Path(tempfile.mkdtemp())
sitk.WriteImage(img, str(tmp / "mask.nii.gz"))
registro, mascara = measure_mask(
    VolumetryStructure(role="figado", label="Figado", mask_path=tmp / "mask.nii.gz", material="organ"),
    img,
)
saida["numerical_volumetry"] = {
    "voxel_count": registro["voxel_count"],                       # LOGIC na pratica
    "voxel_volume_mm3": repr(registro["voxel_volume_mm3"]),
    "volume_ml": repr(registro["volume_ml"]),
    "left_right_mm": repr(registro["dimensions_mm"]["left_right"]) if "dimensions_mm" in registro else repr(registro.get("left_right_mm")),
}

# ---------- NUMERICAL: harmonizacao (resample linear) ----------
mov = sitk.GetImageFromArray((arr.astype(np.float32) * 700.0 + 55.0))
mov.SetSpacing((0.7, 1.3, 2.9)); mov.SetOrigin((-11.2, 3.5, 100.0))
ref = sitk.Image(36, 38, 34, sitk.sitkFloat32)
ref.SetSpacing((0.8, 1.2, 3.1)); ref.SetOrigin((-11.5, 3.25, 100.125))
harmonizada, cobertura = harmonize_to_reference(mov, ref)
h = sitk.GetArrayFromImage(harmonizada).astype(np.float64)
saida["numerical_harmonize"] = {
    "coverage": repr(cobertura),
    "sum": repr(float(h.sum())),
    "mean": repr(float(h.mean())),
    "checksum_exact": canonical_sha256(h.tobytes().hex()),  # identico so se bitwise igual
}

print(json.dumps(saida, indent=2, sort_keys=True, ensure_ascii=False))
