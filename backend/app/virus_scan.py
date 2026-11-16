"""Malware scan for uploads: streams a file to ClamAV's clamd (the clamav service) over its INSTREAM protocol."""

import socket
import struct
from pathlib import Path

from app.config import settings

CHUNK = 1024 * 1024
# A 20 MB PDF scans in seconds; this only stops a hung scanner from hanging the upload forever.
TIMEOUT_SECONDS = 60


class ScannerUnavailable(Exception):
    """clamd couldn't give an answer (down, still loading signatures, or refused the file)."""


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
