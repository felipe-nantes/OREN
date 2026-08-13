#!/usr/bin/env python3
"""Serve only the public OREN Quest CA certificate on the private LAN."""
from __future__ import annotations

import argparse
import io
import ssl
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


class CertificateHandler(BaseHTTPRequestHandler):
    certificate: bytes = b""
    certificate_zip: bytes = b""

    def _headers(self, status: int, content_type: str, length: int) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/health":
            body = b'{"status":"ready","service":"oren-quest-certificate"}'
            self._headers(200, "application/json; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/oren-quest-cert.zip":
            body = self.certificate_zip
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", 'attachment; filename="oren-quest-cert.zip"')
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/oren-quest-cert.crt":
            body = self.certificate
            self.send_response(200)
            self.send_header("Content-Type", "application/x-x509-ca-cert")
            self.send_header("Content-Disposition", 'attachment; filename="oren-quest-cert.crt"')
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/":
            body = (
                "<!doctype html><meta charset=utf-8><title>OREN Quest</title>"
                "<h1>Certificado local OREN</h1>"
                "<p>Uso exclusivo na rede privada de pesquisa.</p>"
                "<p><a download href=/oren-quest-cert.zip style='font-size:1.4rem'>"
                "Baixar pacote ZIP do certificado</a></p>"
                "<p>Abra o ZIP em Arquivos, extraia e instale oren-quest-cert.crt.</p>"
                "<p><a download href=/oren-quest-cert.crt>Download direto alternativo (.crt)</a></p>"
            ).encode("utf-8")
            self._headers(200, "text/html; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        body = b"Not found"
        self._headers(404, "text/plain; charset=utf-8", len(body))
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[quest-cert] {self.address_string()} {fmt % args}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--certificate", type=Path, required=True)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    pem = args.certificate.read_text("ascii")
    # DER evita que navegadores Chromium tratem o PEM como texto. O ZIP é o
    # caminho principal porque o Quest Browser pode bloquear downloads .crt.
    CertificateHandler.certificate = ssl.PEM_cert_to_DER_cert(pem)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("oren-quest-cert.crt", CertificateHandler.certificate)
        bundle.writestr(
            "LEIA-ME.txt",
            "Extraia oren-quest-cert.crt e instale como certificado CA. "
            "Uso exclusivo na rede privada de pesquisa OREN.\n",
        )
    CertificateHandler.certificate_zip = archive.getvalue()
    server = ThreadingHTTPServer((args.host, args.port), CertificateHandler)
    print(f"OREN certificate server: http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
