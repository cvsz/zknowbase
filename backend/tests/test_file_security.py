import asyncio
import struct

import pytest

from app.core.config import Settings
from app.core.file_security import FileSecurityError, scan_upload, validate_file_bytes


def test_validate_text_rejects_nul_bytes() -> None:
    with pytest.raises(FileSecurityError, match="NUL bytes"):
        validate_file_bytes("manual.txt", b"hello\x00world")


def test_validate_pdf_rejects_active_content() -> None:
    data = b"%PDF-1.7\n1 0 obj << /OpenAction 2 0 R >> endobj"
    with pytest.raises(FileSecurityError, match="active-content"):
        validate_file_bytes("policy.pdf", data)


def test_validate_pdf_rejects_spoofed_signature() -> None:
    with pytest.raises(FileSecurityError, match="Invalid PDF signature"):
        validate_file_bytes("policy.pdf", b"not-a-pdf")


@pytest.mark.asyncio
async def test_clamav_clean_stream_is_accepted() -> None:
    received = bytearray()

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        assert await reader.readexactly(10) == b"zINSTREAM\0"
        while True:
            size = struct.unpack("!I", await reader.readexactly(4))[0]
            if size == 0:
                break
            received.extend(await reader.readexactly(size))
        writer.write(b"stream: OK\0")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    settings = Settings(
        malware_scan_mode="clamav",
        clamav_host="127.0.0.1",
        clamav_port=port,
        clamav_timeout_seconds=2,
    )
    try:
        await scan_upload("manual.txt", b"safe knowledge", settings)
    finally:
        server.close()
        await server.wait_closed()
    assert received == b"safe knowledge"


@pytest.mark.asyncio
async def test_clamav_detection_fails_closed() -> None:
    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        assert await reader.readexactly(10) == b"zINSTREAM\0"
        while True:
            size = struct.unpack("!I", await reader.readexactly(4))[0]
            if size == 0:
                break
            await reader.readexactly(size)
        writer.write(b"stream: Eicar-Signature FOUND\0")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    settings = Settings(
        malware_scan_mode="clamav",
        clamav_host="127.0.0.1",
        clamav_port=port,
        clamav_timeout_seconds=2,
    )
    try:
        with pytest.raises(FileSecurityError, match="Malware detected: Eicar-Signature"):
            await scan_upload("manual.txt", b"test payload", settings)
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_clamav_unavailable_fails_closed() -> None:
    settings = Settings(
        malware_scan_mode="clamav",
        clamav_host="127.0.0.1",
        clamav_port=1,
        clamav_timeout_seconds=1,
    )
    with pytest.raises(FileSecurityError, match="scanner is unavailable"):
        await scan_upload("manual.txt", b"safe knowledge", settings)
