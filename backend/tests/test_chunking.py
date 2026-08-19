from app.core.config import Settings
from app.rag.chunking import split_text


def test_split_text_produces_bounded_chunks(tmp_path):
    settings = Settings(api_key="1234567890123456", metadata_db=tmp_path / "db.sqlite",
                        upload_dir=tmp_path / "uploads", chunk_size=80, chunk_overlap=10)
    chunks = split_text("paragraph one. " * 30, settings)
    assert len(chunks) > 1
    assert all(chunk.strip() for chunk in chunks)
    assert max(map(len, chunks)) <= 80
