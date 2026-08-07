#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Segmenta a aorta (unico rotulo arterial disponivel no total_mr -- nao ha
'hepatic_artery' nas 50 classes do modelo) nos 20 casos ja selecionados como
melhores/piores, para a galeria pedida pelo usuario incluir uma
representacao arterial alem das veias (porta/esplenica, cava inferior).

Isolamento em subprocesso com timeout (mesmo padrao de
tools/lld_mmri_v23_segment_worker.py), mas usando
tools/single_label_segment_worker.py --label aorta.

Uso:
    .venv-win/Scripts/python.exe tools/segment_aorta_for_gallery.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

SELECAO = REPO / "casos/qualification/lld_mmri_v23/analise_10_melhores_10_piores_v1"
ENTRADAS = REPO / "casos/qualification/lld_mmri_v23/prepared/external_inputs_v1/inputs"
WORKER = REPO / "tools/single_label_segment_worker.py"


def isolado(source: Path, output: Path, *, label: str, timeout_seconds: int = 600) -> dict:
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt_path = output.parent / f".{output.name}.{uuid.uuid4().hex[:8]}.receipt.json"
    command = [
        sys.executable, str(WORKER),
        "--source", str(source), "--output", str(output),
        "--receipt", str(receipt_path), "--label", label, "--device", "gpu",
    ]
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(command, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, creationflags=creationflags)
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)
        process.communicate()
        output.unlink(missing_ok=True)
        receipt_path.unlink(missing_ok=True)
        raise RuntimeError(f"timeout de {timeout_seconds}s")
    try:
        if process.returncode != 0:
            raise RuntimeError((stderr or stdout or "sem detalhe").strip()[-800:])
        return json.loads(receipt_path.read_text(encoding="utf-8"))
    finally:
        receipt_path.unlink(missing_ok=True)


def main() -> int:
    grupos = [("10_melhores", SELECAO / "10_melhores"), ("10_piores", SELECAO / "10_piores")]
    casos = []
    for nome, pasta in grupos:
        if pasta.is_dir():
            casos.extend((nome, p.name) for p in sorted(pasta.iterdir()) if p.is_dir())

    print(f"segmentando aorta em {len(casos)} casos (10 melhores + 10 piores)\n")
    for i, (grupo, case_id) in enumerate(casos, 1):
        destino = SELECAO / grupo / case_id / "mask_vessel_aorta.nii.gz"
        if destino.is_file():
            continue
        fonte = ENTRADAS / case_id / "t1_venous.nii.gz"
        if not fonte.is_file():
            print(f"[{i}/{len(casos)}] {grupo}/{case_id}: t1_venous ausente, pulado")
            continue
        print(f"[{i}/{len(casos)}] {grupo}/{case_id}", flush=True)
        try:
            receipt = isolado(fonte, destino, label="aorta")
            print(f"    ok em {receipt['elapsed_seconds']:.0f}s", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"    falhou: {exc}", flush=True)

    print("\nconcluido")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
