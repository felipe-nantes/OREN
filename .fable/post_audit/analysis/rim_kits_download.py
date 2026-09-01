# -*- coding: utf-8 -*-
"""RIM-01 — download do KiTS (CT renal, imagem+label) para validação.

Fonte oficial (script get_imaging.py do repo neheller/kits19): imagens em
Hugging Face `neheller/KiTS-Challenge-Imaging` (revision main); labels
(segmentation.nii.gz) em texto puro no repo git kits19 (data/case_NNNNN/,
sem LFS — confirmado por Content-Type/Content-Length no HEAD). Só os 210
casos com segmentation.nii.gz públicos entram (o resto é held-out do
desafio, sem label — não serve para validação).

Amostra pré-registrada: primeiros N case_id em ordem numérica (mesmo
padrão de seleção cega usado no CT01-F/CT-03). Destino: C:\\datasets_ct\\
KiTS (NTFS — D: tem histórico de corrupção nesta sessão; dados de
validação não entram lá até o SSD provar estabilidade sustentada).
Resumível por verificação de gzip íntegro; requests via stdlib.

Uso: python rim_kits_download.py [n_casos]  (default 40)
"""
from __future__ import annotations

import gzip
import json
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

DESTINO = Path(r"C:\datasets_ct\KiTS")
HF_BASE = "https://huggingface.co/datasets/neheller/KiTS-Challenge-Imaging/resolve/main/images"
GH_LABEL_BASE = "https://raw.githubusercontent.com/neheller/kits19/master/data"
API_TREE = "https://api.github.com/repos/neheller/kits19/git/trees/master?recursive=1"


def _gz_integro(path: Path) -> bool:
    try:
        with gzip.open(path, "rb") as f:
            while f.read(1 << 20):
                pass
        return True
    except Exception:
        return False


def _baixa(url: str, destino: Path, tentativas: int = 3) -> None:
    ultimo: Exception | None = None
    for i in range(tentativas):
        try:
            req = Request(url, headers={"User-Agent": "oren-rim01/1.0"})
            with urlopen(req, timeout=180) as resp:
                destino.parent.mkdir(parents=True, exist_ok=True)
                tmp = destino.with_suffix(destino.suffix + ".part")
                with tmp.open("wb") as f:
                    while True:
                        chunk = resp.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                tmp.replace(destino)
            if not _gz_integro(destino):
                destino.unlink(missing_ok=True)
                raise RuntimeError("gzip invalido apos download")
            return
        except Exception as exc:
            ultimo = exc
            time.sleep(8 * (i + 1))
    raise RuntimeError(f"{url}: {ultimo}")


def casos_com_label() -> list[str]:
    req = Request(API_TREE, headers={"User-Agent": "oren-rim01/1.0"})
    with urlopen(req, timeout=60) as resp:
        arvore = json.loads(resp.read().decode("utf-8"))
    casos = sorted({
        item["path"].split("/")[1]
        for item in arvore.get("tree", [])
        if item["path"].endswith("segmentation.nii.gz")
    })
    return casos


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    todos = casos_com_label()
    selecao = todos[:n]
    print(f"selecao pre-registrada: {len(selecao)}/{len(todos)} casos com label "
          f"(primeiros em ordem, mesma regra do CT01-F)", flush=True)
    log = (DESTINO / "_download_log.jsonl")
    log.parent.mkdir(parents=True, exist_ok=True)
    ok = falha = 0
    with log.open("a", encoding="utf-8") as f:
        for caso in selecao:
            pasta = DESTINO / caso
            img = pasta / "imaging.nii.gz"
            lbl = pasta / "segmentation.nii.gz"
            registro = {"caso": caso}
            try:
                if not (img.is_file() and _gz_integro(img)):
                    _baixa(f"{HF_BASE}/{caso}.nii.gz", img)
                if not (lbl.is_file() and _gz_integro(lbl)):
                    _baixa(f"{GH_LABEL_BASE}/{caso}/segmentation.nii.gz", lbl)
                registro["status"] = "ok"
                ok += 1
            except Exception as exc:
                registro.update(status="failed", motivo=str(exc)[:200])
                falha += 1
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")
            f.flush()
            print(json.dumps(registro, ensure_ascii=False), flush=True)
    print(f"KITS_DOWNLOAD_COMPLETO ok={ok} falha={falha}", flush=True)


if __name__ == "__main__":
    main()
