#!/usr/bin/env python3
"""Maintain a stable local CA and an IP-specific HTTPS certificate for OREN.

The CA is created (or migrated from the former self-signed certificate) once.
Only the leaf certificate changes when the workstation receives another LAN IP,
so Meta Quest does not need to trust a new certificate after every network move.
Private keys remain under the Git-ignored ``.local`` directory.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


CA_CERT_NAME = "oren-quest-ca.pem"
CA_KEY_NAME = "oren-quest-ca-key.pem"
SERVER_CERT_NAME = "oren-quest-cert.pem"
SERVER_KEY_NAME = "oren-quest-key.pem"
STATE_NAME = "certificate-state.json"


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _load_certificate(path: Path) -> x509.Certificate:
    return x509.load_pem_x509_certificate(path.read_bytes())


def _load_key(path: Path):
    return serialization.load_pem_private_key(path.read_bytes(), password=None)


def _public_key_bytes(value) -> bytes:
    public_key = value.public_key() if hasattr(value, "public_key") else value
    return public_key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _key_matches(cert: x509.Certificate, key) -> bool:
    return _public_key_bytes(cert) == _public_key_bytes(key)


def _is_ca(cert: x509.Certificate) -> bool:
    try:
        return cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    except x509.ExtensionNotFound:
        return False


def _is_valid(cert: x509.Certificate, *, minimum_days: int = 30) -> bool:
    expiry = cert.not_valid_after_utc if hasattr(cert, "not_valid_after_utc") else _utc(cert.not_valid_after)
    start = cert.not_valid_before_utc if hasattr(cert, "not_valid_before_utc") else _utc(cert.not_valid_before)
    now = datetime.now(timezone.utc)
    return start <= now and expiry >= now + timedelta(days=minimum_days)


def _verify_signature(cert: x509.Certificate, issuer: x509.Certificate) -> bool:
    try:
        issuer.public_key().verify(
            cert.signature,
            cert.tbs_certificate_bytes,
            padding.PKCS1v15(),
            cert.signature_hash_algorithm,
        )
        return True
    except Exception:
        return False


def _write_private_key(path: Path, key) -> None:
    data = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    path.write_bytes(data)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _create_ca(now: datetime):
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "OREN Quest Local CA")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    return cert, key


def _create_server_certificate(address, ca_cert: x509.Certificate, ca_key, now: datetime):
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "OREN Meta Quest")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=825))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("oren.local"),
                    x509.DNSName("localhost"),
                    x509.IPAddress(address),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    return cert, key


def _server_is_current(
    cert_path: Path,
    key_path: Path,
    address,
    ca_cert: x509.Certificate,
) -> bool:
    if not cert_path.exists() or not key_path.exists():
        return False
    try:
        cert = _load_certificate(cert_path)
        key = _load_key(key_path)
        sans = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        return (
            not _is_ca(cert)
            and _is_valid(cert)
            and _key_matches(cert, key)
            and cert.issuer == ca_cert.subject
            and _verify_signature(cert, ca_cert)
            and address in sans.get_values_for_type(x509.IPAddress)
        )
    except Exception:
        return False


def ensure_certificate(ip: str, output: Path) -> dict[str, object]:
    address = ipaddress.ip_address(ip)
    if address.version != 4 or address.is_loopback or address.is_link_local:
        raise ValueError("A valid non-loopback LAN IPv4 address is required")

    output.mkdir(parents=True, exist_ok=True)
    ca_cert_path = output / CA_CERT_NAME
    ca_key_path = output / CA_KEY_NAME
    server_cert_path = output / SERVER_CERT_NAME
    server_key_path = output / SERVER_KEY_NAME
    ca_created = False
    ca_migrated = False

    if ca_cert_path.exists() != ca_key_path.exists():
        raise RuntimeError("Incomplete OREN Quest CA; restore both CA files before continuing")

    if not ca_cert_path.exists():
        # The former implementation generated a self-signed CA certificate in
        # the server filenames. Reuse it as the stable trust anchor so a Quest
        # that already trusted it does not need another installation.
        if server_cert_path.exists() and server_key_path.exists():
            try:
                legacy_cert = _load_certificate(server_cert_path)
                legacy_key = _load_key(server_key_path)
                if _is_ca(legacy_cert) and _is_valid(legacy_cert) and _key_matches(legacy_cert, legacy_key):
                    ca_cert_path.write_bytes(legacy_cert.public_bytes(serialization.Encoding.PEM))
                    _write_private_key(ca_key_path, legacy_key)
                    ca_migrated = True
            except Exception:
                pass
        if not ca_cert_path.exists():
            ca_cert, ca_key = _create_ca(datetime.now(timezone.utc))
            ca_cert_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
            _write_private_key(ca_key_path, ca_key)
            ca_created = True

    ca_cert = _load_certificate(ca_cert_path)
    ca_key = _load_key(ca_key_path)
    if not _is_ca(ca_cert) or not _is_valid(ca_cert) or not _key_matches(ca_cert, ca_key):
        raise RuntimeError("The stored OREN Quest CA is invalid or expired")

    leaf_regenerated = not _server_is_current(server_cert_path, server_key_path, address, ca_cert)
    if leaf_regenerated:
        server_cert, server_key = _create_server_certificate(
            address, ca_cert, ca_key, datetime.now(timezone.utc)
        )
        # Nginx receives the complete chain, while the certificate server only
        # exposes the public CA file and never the private key.
        server_cert_path.write_bytes(
            server_cert.public_bytes(serialization.Encoding.PEM)
            + ca_cert.public_bytes(serialization.Encoding.PEM)
        )
        _write_private_key(server_key_path, server_key)

    result: dict[str, object] = {
        "ip": str(address),
        "ca_created": ca_created,
        "ca_migrated": ca_migrated,
        "leaf_regenerated": leaf_regenerated,
        "ca_certificate": str(ca_cert_path.resolve()),
        "server_certificate": str(server_cert_path.resolve()),
        "server_key": str(server_key_path.resolve()),
        "ca_sha256_fingerprint": ca_cert.fingerprint(hashes.SHA256()).hex(),
        "quest_ca_install_required": ca_created,
    }
    (output / STATE_NAME).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", required=True)
    parser.add_argument("--out", type=Path, default=Path(".local/quest_https"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = ensure_certificate(args.ip, args.out)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(result["server_certificate"])
        print(result["server_key"])
        print(result["ca_certificate"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
