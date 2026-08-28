# -*- coding: utf-8 -*-
"""Download TCIA para o braço de TIPO do benchmark CT-01-F.

Coortes com diagnóstico conhecido por construção (licença CC-BY 4.0):
- HCC-TACE-Seg (todos HCC confirmado)         -> D:/datasets_ct/TCIA_HCC
- Colorectal-Liver-Metastases (todos metástase) -> D:/datasets_ct/TCIA_CRLM
(destino no SSD externo D: por ordem do operador, 2026-08-27; escrita de
150MB verificada por sha256 antes do redirecionamento)

Seleção PRÉ-REGISTRADA e cega a imagem (gravada em
_tcia_selecao_40_40.json): primeiros 40 PatientID em ordem lexicográfica;
por paciente, a série CT de maior ImageCount (desempate por UID).
Resumível: paciente com .dcm extraído é pulado. Dado público
desidentificado (TCIA de-identification); atribuição CC-BY registrada na
evidência do benchmark.
"""
from __future__ import annotations

import io
import json
import sys
import time
import zipfile
from pathlib import Path
from urllib.request import urlopen

BASE = Path(r"C:\datasets_ct")          # seleção pré-registrada + log
# Destino final = SSD externo D: (ordem do operador 2026-08-27), mas o D:
# desconectou em 2026-08-27; staging temporário em C: até ele voltar —
# mover com robocopy verificado e reapontar.
API = ("https://services.cancerimagingarchive.net/nbia-api/services/v1/"
       "getImage?SeriesInstanceUID=")
DESTINOS = {"HCC": BASE / "TCIA_HCC", "CRLM": BASE / "TCIA_CRLM"}


def baixa_serie(uid: str, destino: Path) -> int:
    """Baixa o zip da série e extrai; retorna nº de arquivos extraídos."""
    ultimo_erro: Exception | None = None
    for tentativa in range(3):
        try:
            with urlopen(API + uid, timeout=300) as resp:
                blob = resp.read()
            with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                nomes = [n for n in zf.namelist() if not n.endswith("/")]
                destino.mkdir(parents=True, exist_ok=True)
                zf.extractall(destino)
            return len(nomes)
        except Exception as exc:  # rede/zip: retry com backoff
            ultimo_erro = exc
            time.sleep(10 * (tentativa + 1))
    raise RuntimeError(f"serie {uid}: {ultimo_erro}")


def main() -> None:
    selecao = json.loads(
        (BASE / "_tcia_selecao_40_40.json").read_text(encoding="utf-8"))
    log = (BASE / "_tcia_download_log.jsonl").open("a", encoding="utf-8")
    total_ok = total_falha = 0
    for coorte, series in selecao.items():
        raiz = DESTINOS[coorte]
        for s in series:
            pid, uid = s["PatientID"], s["SeriesInstanceUID"]
            destino = raiz / pid
            esperado = int(s.get("ImageCount") or 0)
            # completo = nº de .dcm >= ImageCount da série (dir parcial refaz)
            if destino.is_dir() and len(list(destino.rglob("*.dcm"))) >= max(esperado, 1):
                continue
            t0 = time.monotonic()
            registro = {"coorte": coorte, "paciente": pid, "uid": uid}
            try:
                n = baixa_serie(uid, destino)
                registro.update(status="ok", arquivos=n,
                                segundos=round(time.monotonic() - t0, 1))
                total_ok += 1
            except Exception as exc:
                registro.update(status="failed", motivo=str(exc)[:200])
                total_falha += 1
            log.write(json.dumps(registro, ensure_ascii=False) + "\n")
            log.flush()
            print(json.dumps(registro, ensure_ascii=False), flush=True)
    print(f"DOWNLOAD_COMPLETO ok={total_ok} falha={total_falha}", flush=True)


if __name__ == "__main__":
    main()
