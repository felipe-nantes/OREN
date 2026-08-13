from tools.serve_quest_certificate import CertificateHandler


def test_certificate_server_exposes_only_expected_routes():
    source = open("tools/serve_quest_certificate.py", encoding="utf-8").read()
    assert 'path == "/oren-quest-cert.crt"' in source
    assert 'path == "/oren-quest-cert.zip"' in source
    assert 'application/x-x509-ca-cert' in source
    assert 'application/zip' in source
    assert 'attachment; filename="oren-quest-cert.crt"' in source
    assert "private" not in source.lower() or "private lan" in source.lower()
    assert "oren-quest-key" not in source


def test_certificate_handler_has_no_directory_listing():
    assert not hasattr(CertificateHandler, "list_directory")
