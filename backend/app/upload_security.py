import asyncio
import io
import struct
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from app.core.config import Settings
from app.observability import UPLOAD_SCAN_DURATION, UPLOAD_SCAN_FAILURES, timed, tracer
from app.rag.loaders import ALLOWED_SUFFIXES


class UploadSecurityError(ValueError):
    pass


class MalwareDetectedError(UploadSecurityError):
    pass


DANGEROUS_PDF_KEYS = {
    "/AA",
    "/EmbeddedFiles",
    "/JavaScript",
    "/JS",
    "/Launch",
    "/OpenAction",
    "/RichMedia",
    "/XFA",
}
DANGEROUS_PDF_SUBTYPES = {"/FileAttachment", "/RichMedia"}


def _resolve_pdf_object(value: Any) -> Any:
    getter = getattr(value, "get_object", None)
    if callable(getter):
        try:
            return getter()
        except Exception as exc:
            raise UploadSecurityError("PDF contains an unreadable indirect object") from exc
    return value


def _reject_active_pdf_content(value: Any, visited: set[int], depth: int = 0) -> None:
    if depth > 32:
        raise UploadSecurityError("PDF object graph exceeds safe inspection depth")
    value = _resolve_pdf_object(value)
    identity = id(value)
    if identity in visited:
        return
    visited.add(identity)

    if isinstance(value, dict):
        subtype = value.get("/Subtype")
        if subtype is not None and str(_resolve_pdf_object(subtype)) in DANGEROUS_PDF_SUBTYPES:
            raise UploadSecurityError("PDF contains an active or embedded-file annotation")
        for key, child in value.items():
            if str(key) in DANGEROUS_PDF_KEYS:
                raise UploadSecurityError(f"PDF active-content key is not allowed: {key}")
            _reject_active_pdf_content(child, visited, depth + 1)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _reject_active_pdf_content(child, visited, depth + 1)


def validate_document_bytes(filename: str, data: bytes) -> None:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise UploadSecurityError(f"Unsupported file type: {suffix or 'unknown'}")
    if not data:
        raise UploadSecurityError("Empty documents are not allowed")

    if suffix == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise UploadSecurityError("File extension is PDF but magic bytes are invalid")
        try:
            reader = PdfReader(io.BytesIO(data), strict=False)
            root = reader.trailer.get("/Root")
            if root is None:
                raise UploadSecurityError("PDF document catalog is missing")
            _reject_active_pdf_content(root, set())
        except UploadSecurityError:
            raise
        except Exception as exc:
            raise UploadSecurityError("PDF failed structural security validation") from exc
    elif b"\x00" in data:
        raise UploadSecurityError("Text document contains NUL bytes")


class ClamAVClient:
    def __init__(self, host: str, port: int, timeout_seconds: float):
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds

    async def _read_reply(self, reader: asyncio.StreamReader) -> str:
        reply = bytearray()
        while len(reply) < 65_536:
            chunk = await reader.read(4096)
            if not chunk:
                break
            reply.extend(chunk)
            if b"\0" in chunk or b"\n" in chunk:
                break
        if len(reply) >= 65_536:
            raise UploadSecurityError("ClamAV returned an oversized reply")
        return bytes(reply).replace(b"\0", b"").decode("utf-8", "replace").strip()

    async def _scan(self, data: bytes) -> None:
        try:
            reader, writer = await asyncio.open_connection(self.host, self.port)
        except OSError as exc:
            raise UploadSecurityError("ClamAV scanner is unavailable") from exc
        try:
            writer.write(b"zINSTREAM\0")
            for offset in range(0, len(data), 64 * 1024):
                chunk = data[offset : offset + 64 * 1024]
                writer.write(struct.pack(">I", len(chunk)))
                writer.write(chunk)
                await writer.drain()
            writer.write(struct.pack(">I", 0))
            await writer.drain()
            reply = await self._read_reply(reader)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

        if reply.endswith(" OK") or reply == "stream: OK":
            return
        if " FOUND" in reply:
            signature = reply.rsplit(" FOUND", 1)[0].split(":", 1)[-1].strip()
            raise MalwareDetectedError(f"Malware detected: {signature[:200]}")
        raise UploadSecurityError(f"ClamAV scan failed closed: {reply[:300] or 'empty response'}")

    async def scan(self, data: bytes) -> None:
        try:
            await asyncio.wait_for(self._scan(data), timeout=self.timeout_seconds)
        except asyncio.TimeoutError as exc:
            raise UploadSecurityError("ClamAV scan timed out") from exc

    async def ping(self) -> bool:
        async def _ping() -> bool:
            try:
                reader, writer = await asyncio.open_connection(self.host, self.port)
            except OSError:
                return False
            try:
                writer.write(b"zPING\0")
                await writer.drain()
                reply = await self._read_reply(reader)
                return reply == "PONG"
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except OSError:
                    pass

        try:
            return await asyncio.wait_for(_ping(), timeout=min(self.timeout_seconds, 5.0))
        except asyncio.TimeoutError:
            return False


class UploadSecurity:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def inspect(self, filename: str, data: bytes) -> None:
        mode = self.settings.malware_scan_mode
        try:
            with tracer("zknowbase.upload").start_as_current_span("upload.inspect"), timed(
                UPLOAD_SCAN_DURATION, {"mode": mode}
            ):
                if mode == "clamav":
                    await ClamAVClient(
                        self.settings.clamav_host,
                        self.settings.clamav_port,
                        self.settings.clamav_timeout_seconds,
                    ).scan(data)
                validate_document_bytes(filename, data)
        except Exception:
            UPLOAD_SCAN_FAILURES.labels(mode=mode).inc()
            raise

    async def scanner_status(self) -> str:
        if self.settings.malware_scan_mode != "clamav":
            return "validation-only"
        healthy = await ClamAVClient(
            self.settings.clamav_host,
            self.settings.clamav_port,
            self.settings.clamav_timeout_seconds,
        ).ping()
        return "ok" if healthy else "error"
