import pytest

from app import virus_scan
from app.config import settings
from tests.helpers import PDF

# Taken before conftest stubs the scanner out for every test.
REAL_SCAN = virus_scan.scan
# The standard antivirus test file, split so this source file itself doesn't look infected.
EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$" + b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


def test_clamav_finds_the_eicar_test_file_and_passes_a_clean_pdf(tmp_path):
    clean = tmp_path / "ok.pdf"
    clean.write_bytes(PDF)
    try:
        assert REAL_SCAN(clean) is None
    except virus_scan.ScannerUnavailable as exc:
        pytest.skip(f"clamd isn't reachable (still loading signatures?): {exc}")
    bad = tmp_path / "eicar.com"
    bad.write_bytes(EICAR)
    assert "Eicar" in REAL_SCAN(bad)


def test_no_scanner_is_unavailable_not_clean(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "clamav_port", 1)  # nothing listens there
    path = tmp_path / "ok.pdf"
    path.write_bytes(PDF)
    with pytest.raises(virus_scan.ScannerUnavailable):
        REAL_SCAN(path)
