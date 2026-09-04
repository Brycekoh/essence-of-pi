from .conftest import upload
from .pdf_fixture import make_pdf


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_upload_extracts_text(client, sample_pdf):
    response = upload(client, sample_pdf)
    assert response.status_code == 201, response.text

    body = response.json()
    assert body["page_count"] == 2
    assert body["filename"] == "paper.pdf"
    assert body["size_bytes"] == len(sample_pdf)
    assert body["char_count"] > 0

    text = client.get(f"/api/papers/{body['id']}/text").json()
    assert "Essence of Pi page one" in text["pages"][0]["text"]
    assert "second page" in text["pages"][1]["text"]


def test_single_page_query(client, sample_pdf):
    paper_id = upload(client, sample_pdf).json()["id"]

    page_two = client.get(f"/api/papers/{paper_id}/text", params={"page": 2}).json()
    assert len(page_two["pages"]) == 1
    assert page_two["pages"][0]["page"] == 2
    assert page_two["page_count"] == 2, "page_count still reports the whole document"

    assert client.get(f"/api/papers/{paper_id}/text", params={"page": 99}).status_code == 404


def test_rejects_non_pdf(client):
    # A .pdf filename and a PDF content-type, but the bytes say otherwise.
    assert upload(client, b"I am definitely a PDF, trust me").status_code == 415


def test_rejects_empty_file(client):
    assert upload(client, b"").status_code == 400


def test_rejects_oversized_file(client, settings):
    too_big = make_pdf(["x"]) + b"\x00" * settings.max_upload_bytes
    assert upload(client, too_big).status_code == 413


def test_list_is_newest_first(client, sample_pdf):
    first = upload(client, sample_pdf, "first.pdf").json()["id"]
    second = upload(client, sample_pdf, "second.pdf").json()["id"]

    listed = [p["id"] for p in client.get("/api/papers").json()]
    assert listed == [second, first]


def test_pdf_round_trips(client, sample_pdf):
    paper_id = upload(client, sample_pdf).json()["id"]
    response = client.get(f"/api/papers/{paper_id}/pdf")
    assert response.status_code == 200
    assert response.content == sample_pdf


def test_delete_removes_paper_and_file(client, sample_pdf, settings):
    paper_id = upload(client, sample_pdf).json()["id"]
    stored = settings.upload_dir / f"{paper_id}.pdf"
    assert stored.exists()

    assert client.delete(f"/api/papers/{paper_id}").status_code == 204
    assert not stored.exists()
    assert client.get(f"/api/papers/{paper_id}").status_code == 404
    assert client.delete(f"/api/papers/{paper_id}").status_code == 404


def test_unknown_paper_is_404(client):
    assert client.get("/api/papers/nope").status_code == 404
    assert client.get("/api/papers/nope/text").status_code == 404
