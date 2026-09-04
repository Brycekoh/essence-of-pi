import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.services.store import PaperStore, get_store

from .pdf_fixture import make_pdf


@pytest.fixture
def settings(tmp_path) -> Settings:
    """Real Settings, but writing into a per-test temp directory."""
    return Settings(upload_dir=tmp_path / "uploads", max_upload_bytes=64 * 1024)


@pytest.fixture
def client(settings):
    """A TestClient with storage pointed at the temp directory.

    Overriding dependencies instead of monkeypatching globals is what keeps
    tests isolated from each other -- each one gets an empty store.
    """
    store = PaperStore(settings.upload_dir)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def sample_pdf() -> bytes:
    return make_pdf(["Essence of Pi page one", "second page here"])


def upload(client, data: bytes, filename: str = "paper.pdf"):
    return client.post(
        "/api/papers",
        files={"file": (filename, data, "application/pdf")},
    )
