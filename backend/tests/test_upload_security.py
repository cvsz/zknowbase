import asyncio
import io
import struct

import pytest
from pypdf import PdfWriter

from app.core.config import Settings
from app.upload_security import (
    ClamAVClient,
    MalwareDetectedError,
    UploadSecurity,
    UploadSecurityError,
    validate_document_bytes,
)


def _pdf_bytes(*, javascript: bool = False, attachment: bool = False) -> bytes:
    output = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    if javascript:
        writer.add_js("app.alert('x')")
    if attachment:
        writer.add_attachment("payload.txt", b"payload")
    writer.write(output)
    return output.getvalue()


def test_validate_document_accepts_plain_pdf_and_text():
    validate_document_bytes("plain.pdf", _pdf_bytes())
    validate_document_bytes("policy.md", b"# Policy\nSafe text")
    validate_document_bytes("manual.txt", b"safe text")


def test_validate_document_rejects_magic_mismatch_and_nul_text():
    with pytest.raises(UploadSecurityError, match="magic bytes"):
        validate_document_bytes("fake.pdf", b"not a pdf")
    with pytest.raises(UploadSecurityError, match="NUL"):
        validate_document_bytes("bad.txt", b"abc\x00def")


def test_validate_document_rejects_pdf_javascript_and_embedded_files():
    with pytest.raises(UploadSecurityError):
        validate_document_bytes("script.pdf", _pdf_bytes(javascript=True))
    with pytest.raises(UploadSecurityError):
        validate_document_bytes("attachment.pdf", _pdf_bytes(attachment=True))


async def _start_clamd(reply: bytes):
    received = bytearray()

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        command = await reader.readuntil(b"\0")
        assert command == b"zINSTREAM\0"
        while True:
            size_bytes = await reader.readexactly(4)
            size = struct.unpack(">I", size_bytes)[0]
            if size == 0:
                break
            received.extend(await reader.readexactly(size))
        writer.write(reply)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    return server, port, received


@pytest.mark.asyncio
async def test_clamav_instream_sends_bytes_and_accepts_clean_reply():
    server, port, received = await _start_clamd(b"stream: OK\0")
    try:
        await ClamAVClient("127.0.0.1", port, 5).scan(b"hello")
    finally:
        server.close()
        await server.wait_closed()
    assert bytes(received) == b"hello"


@pytest.mark.asyncio
async def test_clamav_rejects_detection():
    server, port, _received = await _start_clamd(b"stream: Eicar-Test-Signature FOUND\0")
    try:
        with pytest.raises(MalwareDetectedError, match="Eicar-Test-Signature"):
            await ClamAVClient("127.0.0.1", port, 5).scan(b"sample")
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_clamav_mode_fails_closed_when_daemon_unavailable(tmp_path):
    settings = Settings(
        api_key="this-is-a-test-secret-key",
        metadata_db=tmp_path / "db.sqlite",
        upload_dir=tmp_path / "uploads",
        malware_scan_mode="clamav",
        clamav_host="127.0.0.1",
        clamav_port=1,
        clamav_timeout_seconds=1,
    )
    with pytest.raises(UploadSecurityError, match="unavailable"):
        await UploadSecurity(settings).inspect("safe.txt", b"safe")
