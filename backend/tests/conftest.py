import pytest
from fastapi.testclient import TestClient

from app.api.concepts import provide_llm
from app.config import Settings, get_settings
from app.main import app
from app.services.llm import StubLLM
from app.services.store import PaperStore, get_store

from .pdf_fixture import make_pdf


@pytest.fixture
def settings(tmp_path) -> Settings:
    """Real Settings, but writing into a per-test temp directory."""
    return Settings(upload_dir=tmp_path / "uploads", max_upload_bytes=64 * 1024)


@pytest.fixture
def stub_llm() -> StubLLM:
    """A scripted LLM. Queue responses on it before hitting an endpoint."""
    return StubLLM()


@pytest.fixture
def client(settings, stub_llm):
    """A TestClient with storage and the LLM pointed at test doubles.

    Overriding dependencies instead of monkeypatching globals is what keeps
    tests isolated from each other -- each one gets an empty store and a fresh
    stub, and no test can reach the network by accident.
    """
    store = PaperStore(settings.upload_dir)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[provide_llm] = lambda: stub_llm
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
