# -*- coding: utf-8 -*-
"""RIM-01 fase E — smoke real do fluxo ponta-a-ponta (Engine de produção).

Prova, com o mesmo Engine (dtwin.engine.Engine) e stages usados em
produção, que perfis/rins*.yaml funcionam fim-a-fim:
- TC: um caso real TCIA (série DICOM de abdome já local, comprovadamente
  com rins) → segmentação (union kidney_left+kidney_right) → candidato
  de cisto renal (kidney_cysts) → malha → volumetria por lado + total →
  viewer_manifest.json.
- RM: um caso CHAOS-MR (série DICOM T1DUAL InPhase local, com Ground
  humano) → mesmo fluxo, sem candidato (task não existe em RM).

Não passa por webapp/jobs.py (isola o motor do plumbing HTTP, já
coberto pelos testes com mocks); usa Engine.prepare/finalize + a mesma
_localize_candidate_ct via chamada direta ao candidate_region para TC.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ))

from dtwin.candidate_region import generate_candidate_region  # noqa: E402
from dtwin.engine import Engine  # noqa: E402

TRABALHO = Path(r"C:\datasets_ct\_bench_work\rim_smoke")


def _um_caso(nome: str, perfil_path: str, dicom_dir: Path, com_candidato: bool) -> dict:
    case_dir = TRABALHO / nome
    if case_dir.exists():
        import shutil
        shutil.rmtree(case_dir)
    engine = Engine(RAIZ / perfil_path)
    case = engine.prepare(dicom_dir, case_dir, device="gpu", fast=False)

    candidato = None
    if com_candidato:
        bloco = engine.profile.get("localizacao_candidata") or {}
        request_path = case.root / "candidate_request.json"
        request_path.write_text(json.dumps({
            "schema": "argos-candidate-request-v1",
            "task": str(bloco.get("motor_task")),
            "modality": "CT",
        }), encoding="utf-8")
        candidato = generate_candidate_region(
            case.root, device="gpu", request_path=request_path
        )

    engine.finalize(case_dir, no_lesion=True)

    manifest = json.loads((case.outputs / "viewer_manifest.json").read_text(encoding="utf-8"))
    volumetry = manifest.get("volumetry") or {}
    estruturas = {s["role"]: s for s in volumetry.get("structures", [])}
    return {
        "caso": nome,
        "organ_label": manifest.get("organ_label"),
        "organ_summary_volume_ml": (volumetry.get("organ_summary") or {}).get("volume_ml"),
        "rim_esquerdo_ml": (estruturas.get("rim_esquerdo") or {}).get("volume_ml"),
        "rim_direito_ml": (estruturas.get("rim_direito") or {}).get("volume_ml"),
        "measurement_class_orgao": (estruturas.get("orgao") or {}).get("measurement_class"),
        "candidate_present": (candidato or {}).get("candidate_present"),
        "candidate_volume_mm3": (candidato or {}).get("total_candidate_volume_mm3"),
        "viewer_meshes": [m["role"] for m in manifest.get("meshes", [])],
    }


def main() -> None:
    quais = sys.argv[1] if len(sys.argv) > 1 else "all"
    resultados = []
    # --- TC: primeiro caso TCIA HCC local com série de abdome completa ---
    if quais in ("all", "ct"):
        hcc_dir = Path(r"C:\datasets_ct\TCIA_HCC\HCC_001")
        dcm = sorted(hcc_dir.rglob("*.dcm"))
        if dcm:
            resultados.append(_um_caso(
                "hcc001_rim_ct", "profiles/rins_ct.yaml", dcm[0].parent, com_candidato=True
            ))
    if quais not in ("all", "mr"):
        for r in resultados:
            print(json.dumps(r, ensure_ascii=False, indent=2), flush=True)
        print("RIM_SMOKE_COMPLETO", flush=True)
        return
    # --- RM: primeiro caso CHAOS-MR (T1DUAL InPhase, com Ground humano) ---
    # C: (NTFS) — a extracao inicial foi para o D: durante uma janela de
    # corrupcao do exFAT e nasceu com bytes 0xFF; re-extraido direto do
    # zip fonte (Downloads) para C:, verificado 20/20 por leitura real.
    chaos_dir = Path(r"C:\datasets_ct\CHAOS_MR\Train_Sets\MR\1\T1DUAL\DICOM_anon\InPhase")
    if chaos_dir.is_dir():
        resultados.append(_um_caso(
            "chaos1_rim_mr", "profiles/rins.yaml", chaos_dir, com_candidato=False
        ))
    for r in resultados:
        print(json.dumps(r, ensure_ascii=False, indent=2), flush=True)
    print("RIM_SMOKE_COMPLETO", flush=True)


if __name__ == "__main__":
    main()
