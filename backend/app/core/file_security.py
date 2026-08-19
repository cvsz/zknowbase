import asyncio
import struct
from pathlib import Path

from app.core.config import Settings

_PDF_ACTIVE_MARKERS = (
    b"/JavaScript",
    b"/JS",
    b"/Launch",
    b"/EmbeddedFile",
    b"/OpenAction",
    b"/RichMedia",
)


class FileSecurityError(ValueError):
    """Raised when an uploaded file fails the configured security policy."""


def validate_file_bytes(filename: str, data: bytes) -> None:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise FileSecurityError("Invalid PDF signature")
        for marker in _PDF_ACTIVE_MARKERS:
            if marker.lower() in data.lower():
                raise FileSecurityError(
                    f"PDF contains disallowed active-content marker: {marker.decode()}"
                )
    elif suffix in {".md", ".markdown", ".txt"}:
        if b"\x00" in data:
            raise FileSecurityError("Text document contains NUL bytes")
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise FileSecurityError("Text document is not valid UTF-8") from exc


async def _clamd_scan(data: bytes, settings: Settings) -> None:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(settings.clamav_host, settings.clamav_port),
            timeout=settings.clamav_timeout_seconds,
        )
    except (OSError, asyncio.TimeoutError) as exc:
        raise FileSecurityError("ClamAV scanner is unavailable") from exc

    try:
        writer.write(b"zINSTREAM\0")
        for offset in range(0, len(data), 64 * 1024):
            chunk = data[offset : offset + 64 * 1024]
            writer.write(struct.pack("!I", len(chunk)))
            writer.write(chunk)
        writer.write(struct.pack("!I", 0))
        await asyncio.wait_for(writer.drain(), timeout=settings.clamav_timeout_seconds)
        response = await asyncio.wait_for(
            reader.readuntil(b"\0"), timeout=settings.clamav_timeout_seconds
        )
    except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError) as exc:
        raise FileSecurityError("ClamAV scan did not complete") from exc
    finally:
        writer.close()
        await writer.wait_closed()

    result = response.rstrip(b"\0\n").decode("utf-8", errors="replace")
    if result.endswith(" OK"):
        return
    if " FOUND" in result:
        signature = result.rsplit(":", 1)[-1].replace("FOUND", "").strip()
        raise FileSecurityError(f"Malware detected: {signature or 'unknown signature'}")
    raise FileSecurityError(f"ClamAV returned an unexpected result: {result}")


async def scan_upload(filename: str, data: bytes, settings: Settings) -> None:
    """Apply pre-parse upload controls and fail closed when scanning is enabled."""
    validate_file_bytes(filename, data)
    if settings.malware_scan_mode == "clamav":
        await _clamd_scan(data, settings)
