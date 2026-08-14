#!/usr/bin/env python3
"""Create an offline QR access card for the current OREN Quest LAN URL."""
from __future__ import annotations

import argparse
import base64
import html
import io
from pathlib import Path

import qrcode
import qrcode.image.svg


def build_page(*, url: str, ip: str, network: str, fingerprint: str) -> str:
    qr_buffer = io.BytesIO()
    qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=12, border=3).save(qr_buffer)
    qr_data = base64.b64encode(qr_buffer.getvalue()).decode("ascii")
    safe_url = html.escape(url, quote=True)
    short_fingerprint = ":".join(fingerprint.upper()[i : i + 2] for i in range(0, min(len(fingerprint), 32), 2))
    return f"""<!doctype html>
<html lang=\"pt-BR\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>OREN — acesso Meta Quest</title>
<style>
  *{{box-sizing:border-box}} body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#07110e;color:#edf8f2;font:16px/1.45 system-ui,sans-serif}}
  main{{width:min(94vw,920px);padding:34px;border:1px solid #2d5c4a;border-radius:28px;background:linear-gradient(145deg,#12241eeb,#091510f5);box-shadow:0 24px 80px #0009}}
  header{{display:flex;justify-content:space-between;gap:20px;align-items:center}} h1{{margin:0;color:#8de3b8;font-size:clamp(1.6rem,4vw,2.7rem)}} .status{{color:#73e0a9}}
  .grid{{display:grid;grid-template-columns:minmax(280px,420px) 1fr;gap:32px;margin-top:28px}} .qr{{background:#fff;border-radius:22px;padding:16px;width:100%}}
  .url{{display:block;margin:16px 0;padding:14px;border-radius:12px;background:#07100d;color:#a9f0cd;overflow-wrap:anywhere;font-weight:700}}
  dl{{display:grid;grid-template-columns:auto 1fr;gap:8px 18px}} dt{{color:#8fa69c}} dd{{margin:0}} .note{{color:#aabbb3;font-size:.92rem}}
  @media(max-width:700px){{.grid{{grid-template-columns:1fr}}}}
</style>
<main><header><div><h1>OREN · Meta Quest</h1><div class=\"status\">● acesso local pronto</div></div><strong>{html.escape(network)}</strong></header>
<section class=\"grid\"><div><img class=\"qr\" src=\"data:image/svg+xml;base64,{qr_data}\" alt=\"QR code OREN\"></div>
<div><h2>Abra no Quest</h2><p>Leia o QR ou abra o link curto abaixo. Na página, escolha o exame recente.</p>
<a class=\"url\" href=\"{safe_url}\">{safe_url}</a>
<dl><dt>IP atual</dt><dd>{html.escape(ip)}</dd><dt>Rede</dt><dd>{html.escape(network)}</dd><dt>CA</dt><dd>{short_fingerprint}…</dd></dl>
<p class=\"note\">O QR não contém token clínico. A sessão temporária é criada somente depois que um caso é selecionado.</p>
<p class=\"note\">PC e Quest devem estar na mesma rede local. Redes de convidados podem bloquear comunicação entre dispositivos.</p></div></section></main></html>"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--ip", required=True)
    parser.add_argument("--network", required=True)
    parser.add_argument("--fingerprint", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        build_page(url=args.url, ip=args.ip, network=args.network, fingerprint=args.fingerprint),
        encoding="utf-8",
    )
    print(args.out.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
