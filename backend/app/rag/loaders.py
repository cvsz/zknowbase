import io
import ipaddress
import socket
from pathlib import Path
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

from app.core.config import Settings

ALLOWED_SUFFIXES = {".pdf", ".md", ".markdown", ".txt"}


def parse_bytes(filename: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError(f"Unsupported file type: {suffix or 'unknown'}")
    if suffix == ".pdf":
        reader = PdfReader(io.BytesIO(data))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages).strip()
    return data.decode("utf-8", errors="replace").strip()


def _assert_public_host(hostname: str) -> None:
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, None)}
    except socket.gaierror as exc:
        raise ValueError("URL hostname could not be resolved") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ValueError("URL resolves to a non-public address")


async def fetch_url_text(url: str, settings: Settings) -> tuple[str, str]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only public http/https URLs are allowed")
    _assert_public_host(parsed.hostname)

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
        response = await client.get(url, headers={"User-Agent": "zknowbase/1.0"})
        if 300 <= response.status_code < 400:
            raise ValueError("Redirecting URLs are rejected; provide the final canonical URL")
        response.raise_for_status()
        if len(response.content) > settings.max_url_bytes:
            raise ValueError("URL response exceeds configured size limit")
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type:
            soup = BeautifulSoup(response.text, "html.parser")
            for element in soup(["script", "style", "noscript"]):
                element.decompose()
            text = "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())
        elif content_type.startswith("text/") or not content_type:
            text = response.text
        else:
            raise ValueError(f"Unsupported URL content type: {content_type}")
        return text.strip(), content_type
