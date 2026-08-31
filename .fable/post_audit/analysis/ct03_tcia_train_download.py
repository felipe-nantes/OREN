# -*- coding: utf-8 -*-
"""Download TCIA do conjunto de TREINO do CT-03 (tipo hcc vs metastase).

Seleção pré-registrada e cega a imagem: por coleção, TODOS os pacientes
EXCETO os 40 primeiros PatientID em ordem lexicográfica (que formam o
TESTE CONGELADO do CT01-F/CT-03, já baixados em C:\\datasets_ct\\TCIA_*).
Por paciente, a série CT de maior ImageCount (desempate por UID) — a
mesma regra do teste. Destino: SSD externo D:\\datasets_ct\\*_TRAIN
(decisão do operador, 2026-08-28; escrita do D: verificada por sha256
antes do disparo). Licença CC-BY 4.0; dados públicos desidentificados.

Resumível: paciente com nº de .dcm >= ImageCount é pulado.
"""
from __future__ import annotations

import io
import json
import time
import zipfile
from pathlib import Path
from urllib.request import urlopen

BASE = Path(r"C:\datasets_ct")            # metadados/seleções/logs
DESTINO_RAIZ = Path(r"D:\datasets_ct")    # dados de treino no SSD externo
API = ("https://services.cancerimagingarchive.net/nbia-api/services/v1/"
       "getImage?SeriesInstanceUID=")
COLECOES = {
    "HCC": (BASE / "_hcc_series.json", DESTINO_RAIZ / "TCIA_HCC_TRAIN"),
    "CRLM": (BASE / "_crlm_series.json", DESTINO_RAIZ / "TCIA_CRLM_TRAIN"),
}
N_TESTE = 40  # primeiros N PatientID = teste congelado; treino = o resto


def selecao_treino(series_json: Path) -> list[dict]:
    dados = json.loads(series_json.read_text(encoding="utf-8"))
    cts = [s for s in dados if s.get("Modality") == "CT"]
    por_pac: dict[str, dict] = {}
    for s in cts:
        pid = s["PatientID"]
        chave = (int(s.get("ImageCount") or 0), s["SeriesInstanceUID"])
        atual = por_pac.get(pid)
        if atual is None or chave > (int(atual.get("ImageCount") or 0),
                                     atual["SeriesInstanceUID"]):
            por_pac[pid] = s
    pacientes = sorted(por_pac)
    treino = pacientes[N_TESTE:]  # exclui o teste congelado
    return [por_pac[p] for p in treino]


def baixa_serie(uid: str, destino: Path) -> int:
    ultimo: Exception | None = None
    for tentativa in range(3):
        try:
            with urlopen(API + uid, timeout=600) as resp:
                blob = resp.read()
            with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                nomes = [n for n in zf.namelist() if not n.endswith("/")]
                destino.mkdir(parents=True, exist_ok=True)
                zf.extractall(destino)
            return len(nomes)
        except Exception as exc:
            ultimo = exc
            time.sleep(15 * (tentativa + 1))
    raise RuntimeError(f"serie {uid}: {ultimo}")


def main() -> None:
    log = (BASE / "_ct03_train_download_log.jsonl").open("a", encoding="utf-8")
    ok = falha = 0
    selecao_registrada = {}
    for coorte, (series_json, raiz) in COLECOES.items():
        series = selecao_treino(series_json)
        selecao_registrada[coorte] = [
            {"PatientID": s["PatientID"], "SeriesInstanceUID": s["SeriesInstanceUID"],
             "ImageCount": s.get("ImageCount"), "FileSize": s.get("FileSize")}
            for s in series
        ]
        for s in series:
            pid, uid = s["PatientID"], s["SeriesInstanceUID"]
            destino = raiz / pid
            esperado = max(int(s.get("ImageCount") or 0), 1)
            if destino.is_dir() and len(list(destino.rglob("*.dcm"))) >= esperado:
                continue
            registro = {"coorte": coorte, "paciente": pid, "uid": uid}
            t0 = time.monotonic()
            try:
                n = baixa_serie(uid, destino)
                registro.update(status="ok", arquivos=n,
                                segundos=round(time.monotonic() - t0, 1))
                ok += 1
            except Exception as exc:
                registro.update(status="failed", motivo=str(exc)[:200])
                falha += 1
            log.write(json.dumps(registro, ensure_ascii=False) + "\n")
            log.flush()
            print(json.dumps(registro, ensure_ascii=False), flush=True)
    # seleção de treino pré-registrada gravada junto aos metadados
    (BASE / "_ct03_selecao_treino.json").write_text(
        json.dumps(selecao_registrada, ensure_ascii=False), encoding="utf-8")
    print(f"TREINO_DOWNLOAD_COMPLETO ok={ok} falha={falha}", flush=True)


if __name__ == "__main__":
    main()
