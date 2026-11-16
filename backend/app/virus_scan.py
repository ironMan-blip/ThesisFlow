"""Malware scan for uploads: streams a file to ClamAV's clamd (the clamav service) over its INSTREAM protocol."""

import socket
import struct
import tempfile
from pathlib import Path

from app.config import settings

CHUNK = 1024 * 1024
# A 20 MB PDF scans in seconds; this only stops a hung scanner from hanging the upload forever.
TIMEOUT_SECONDS = 60


class ScannerUnavailable(Exception):
    """clamd couldn't give an answer (down, still loading signatures, or refused the file)."""


def warm_up(sample: Path | None) -> None:
    """Scan once so the first upload after clamd starts doesn't pay its ~250 ms first-PDF cost. Raises ScannerUnavailable.

    sample: a real PDF (an existing upload). Only a real-world PDF warms clamd's PDF scanning; a made-up one doesn't.
    """
    if sample is not None:
        scan(sample)
        return
    with tempfile.NamedTemporaryFile() as f:  # no uploads yet: at least open the connection and load the engine
        scan(Path(f.name))


def scan(path: Path) -> str | None:
    """The malware ClamAV found in the file, or None if it is clean. Never guesses: no answer raises ScannerUnavailable."""
    try:
        with (
            socket.create_connection((settings.clamav_host, settings.clamav_port), timeout=TIMEOUT_SECONDS) as sock,
            path.open("rb") as f,
        ):
            sock.sendall(b"zINSTREAM\0")
            while chunk := f.read(CHUNK):
                sock.sendall(struct.pack(">I", len(chunk)) + chunk)
            sock.sendall(struct.pack(">I", 0))  # end of stream
            reply = b""
            while not reply.endswith(b"\0") and (part := sock.recv(4096)):
                reply += part
    except OSError as exc:
        raise ScannerUnavailable(str(exc)) from exc
    answer = reply.rstrip(b"\0").decode(errors="replace")
    if answer == "stream: OK":
        return None
    if answer.startswith("stream: ") and answer.endswith(" FOUND"):
        return answer.removeprefix("stream: ").removesuffix(" FOUND")
    raise ScannerUnavailable(answer or "no reply")  # e.g. "INSTREAM size limit exceeded. ERROR"
