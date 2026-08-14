from __future__ import annotations

import ipaddress
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID

from tools.create_quest_certificate import ensure_certificate


def _load(path: Path) -> x509.Certificate:
    return x509.load_pem_x509_certificate(path.read_bytes())


def _verify(child: x509.Certificate, issuer: x509.Certificate) -> None:
    issuer.public_key().verify(
        child.signature,
        child.tbs_certificate_bytes,
        padding.PKCS1v15(),
        child.signature_hash_algorithm,
    )


def _legacy_certificate(output: Path) -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "OREN Quest LAN")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(key, hashes.SHA256())
    )
    output.mkdir(exist_ok=True)
    pem = cert.public_bytes(serialization.Encoding.PEM)
    (output / "oren-quest-cert.pem").write_bytes(pem)
    (output / "oren-quest-key.pem").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return pem


def test_stable_ca_survives_ip_change_and_leaf_is_reissued(tmp_path: Path) -> None:
    first = ensure_certificate("192.168.10.20", tmp_path)
    ca_before = (tmp_path / "oren-quest-ca.pem").read_bytes()
    leaf_before = (tmp_path / "oren-quest-cert.pem").read_bytes()
    assert first["ca_created"] is True
    assert first["leaf_regenerated"] is True

    unchanged = ensure_certificate("192.168.10.20", tmp_path)
    assert unchanged["leaf_regenerated"] is False
    assert (tmp_path / "oren-quest-cert.pem").read_bytes() == leaf_before

    changed = ensure_certificate("10.22.4.8", tmp_path)
    assert changed["leaf_regenerated"] is True
    assert changed["quest_ca_install_required"] is False
    assert (tmp_path / "oren-quest-ca.pem").read_bytes() == ca_before
    assert (tmp_path / "oren-quest-cert.pem").read_bytes() != leaf_before

    ca = _load(tmp_path / "oren-quest-ca.pem")
    leaf = _load(tmp_path / "oren-quest-cert.pem")
    assert ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is True
    assert leaf.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is False
    sans = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert ipaddress.ip_address("10.22.4.8") in sans.get_values_for_type(x509.IPAddress)
    _verify(leaf, ca)


def test_legacy_trusted_certificate_is_migrated_as_same_ca(tmp_path: Path) -> None:
    legacy_pem = _legacy_certificate(tmp_path)
    result = ensure_certificate("192.168.15.99", tmp_path)
    assert result["ca_migrated"] is True
    assert result["ca_created"] is False
    assert result["quest_ca_install_required"] is False
    assert (tmp_path / "oren-quest-ca.pem").read_bytes() == legacy_pem
    assert (tmp_path / "oren-quest-cert.pem").read_bytes() != legacy_pem
    _verify(_load(tmp_path / "oren-quest-cert.pem"), _load(tmp_path / "oren-quest-ca.pem"))


def test_invalid_lan_addresses_are_rejected(tmp_path: Path) -> None:
    for address in ("127.0.0.1", "169.254.10.1", "::1"):
        try:
            ensure_certificate(address, tmp_path / address.replace(":", "_"))
        except ValueError:
            pass
        else:
            raise AssertionError(f"address should be rejected: {address}")
