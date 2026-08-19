import base64
import binascii
import os
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAGIC = b"ZKB-AESGCM-v1\x00"
NONCE_SIZE = 12
TAG_SIZE = 16
CHUNK_SIZE = 1024 * 1024
AAD = b"zknowbase-backup-envelope-v1"


class BackupCryptoError(RuntimeError):
    pass


def load_key_file(path: Path) -> bytes:
    if not path.is_file():
        raise BackupCryptoError(f"Backup encryption key file not found: {path}")
    if os.name != "nt" and path.stat().st_mode & 0o077:
        raise BackupCryptoError("Backup encryption key file must not be group/world accessible")
    encoded = path.read_bytes().strip()
    try:
        key = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise BackupCryptoError("Backup encryption key file must contain strict base64") from exc
    if len(key) != 32:
        raise BackupCryptoError("Backup encryption key must decode to exactly 32 bytes")
    return key


def is_encrypted_archive(path: Path) -> bool:
    with path.open("rb") as handle:
        return handle.read(len(MAGIC)) == MAGIC


def encrypt_archive(source: Path, output: Path, key: bytes) -> None:
    if len(key) != 32:
        raise BackupCryptoError("AES-256-GCM requires a 32-byte key")
    nonce = os.urandom(NONCE_SIZE)
    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(AAD)
    try:
        with source.open("rb") as src, output.open("xb") as dst:
            dst.write(MAGIC)
            dst.write(nonce)
            for chunk in iter(lambda: src.read(CHUNK_SIZE), b""):
                dst.write(encryptor.update(chunk))
            dst.write(encryptor.finalize())
            dst.write(encryptor.tag)
        os.chmod(output, 0o600)
    except Exception:
        output.unlink(missing_ok=True)
        raise


def decrypt_archive(source: Path, output: Path, key: bytes) -> None:
    if len(key) != 32:
        raise BackupCryptoError("AES-256-GCM requires a 32-byte key")
    minimum = len(MAGIC) + NONCE_SIZE + TAG_SIZE
    size = source.stat().st_size
    if size < minimum:
        raise BackupCryptoError("Encrypted backup envelope is truncated")
    try:
        with source.open("rb") as src:
            if src.read(len(MAGIC)) != MAGIC:
                raise BackupCryptoError("Backup archive is not a supported encrypted envelope")
            nonce = src.read(NONCE_SIZE)
            src.seek(-TAG_SIZE, os.SEEK_END)
            tag = src.read(TAG_SIZE)
            ciphertext_end = size - TAG_SIZE
            src.seek(len(MAGIC) + NONCE_SIZE)
            decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
            decryptor.authenticate_additional_data(AAD)
            with output.open("xb") as dst:
                remaining = ciphertext_end - src.tell()
                while remaining:
                    chunk = src.read(min(CHUNK_SIZE, remaining))
                    if not chunk:
                        raise BackupCryptoError("Encrypted backup envelope is truncated")
                    remaining -= len(chunk)
                    dst.write(decryptor.update(chunk))
                dst.write(decryptor.finalize())
    except InvalidTag as exc:
        output.unlink(missing_ok=True)
        raise BackupCryptoError("Backup authentication failed; key or archive is invalid") from exc
    except Exception:
        output.unlink(missing_ok=True)
        raise
