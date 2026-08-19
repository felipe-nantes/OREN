"""Compara as sondas host vs container e deriva a proposta de tolerancias."""
import json, sys
from pathlib import Path

scratch = Path(sys.argv[1])
host = json.loads((scratch / "probe_host.json").read_text(encoding="utf-8-sig"))
cont = json.loads((scratch / "probe_container.json").read_text(encoding="utf-8-sig"))

print("=== AMBIENTES ===")
for nome, d in (("host", host), ("container", cont)):
    print(f"{nome}: {d['environment']}")

print("\n=== LOGIC ===")
igual = host["logic_splits_sha256"] == cont["logic_splits_sha256"]
print(f"splits digest identico: {igual}")

print("\n=== NUMERICAL: wilson ===")
max_delta_wilson = 0.0
for chave in host["numerical_wilson"]:
    for lado in ("low", "high"):
        a = float(eval(host["numerical_wilson"][chave][lado]))
        b = float(eval(cont["numerical_wilson"][chave][lado]))
        d = abs(a - b)
        max_delta_wilson = max(max_delta_wilson, d)
        if d != 0:
            print(f"  {chave} {lado}: host={a!r} cont={b!r} delta={d:.3e}")
print(f"max delta wilson: {max_delta_wilson:.3e}")

print("\n=== NUMERICAL: volumetria ===")
hv, cv = host["numerical_volumetry"], cont["numerical_volumetry"]
print(f"voxel_count: host={hv['voxel_count']} cont={cv['voxel_count']} identico={hv['voxel_count']==cv['voxel_count']}")
for k in ("voxel_volume_mm3", "volume_ml"):
    a, b = float(eval(hv[k])), float(eval(cv[k]))
    print(f"{k}: delta={abs(a-b):.3e} (host={a!r})")

print("\n=== NUMERICAL: harmonizacao ===")
hh, ch = host["numerical_harmonize"], cont["numerical_harmonize"]
print(f"checksum bitwise identico: {hh['checksum_exact']==ch['checksum_exact']}")
for k in ("coverage", "sum", "mean"):
    a, b = float(eval(hh[k])), float(eval(ch[k]))
    rel = abs(a-b)/max(abs(a), 1e-300)
    print(f"{k}: abs_delta={abs(a-b):.3e} rel_delta={rel:.3e}")
