import os

import pytest
from fastapi.testclient import TestClient

from ved_backend.documents import DocumentLibrary
from ved_backend.main import app

pytestmark = pytest.mark.skipif(
    not os.environ.get("VED_TEST_DATABASE_URL"),
    reason="Set VED_TEST_DATABASE_URL to run database-backed tests",
)

MAX_UPLOAD_BYTES = 10_000


class RecordingIndexer:
    def __init__(self) -> None:
        self.triggered = 0

    def trigger(self) -> None:
        self.triggered += 1


@pytest.fixture
def client(session_factory, tmp_path):
    indexer = RecordingIndexer()
    app.state.documents = DocumentLibrary(
        session_factory, tmp_path, max_upload_bytes=MAX_UPLOAD_BYTES
    )
    app.state.document_indexer = indexer
    yield TestClient(app), indexer, tmp_path
    app.state.documents = None
    app.state.document_indexer = None


def send(test_client, content: bytes, filename: str = "notes.txt"):
    return test_client.post("/documents", files={"file": (filename, content)})


def test_upload_answers_pending_at_once_and_nudges_the_indexer(client):
    test_client, indexer, _ = client

    response = send(test_client, b"the deposit clause", "lease.md")

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["filename"] == "lease.md"
    assert body["media_type"] == "text/markdown"
    assert indexer.triggered == 1


def test_reupload_returns_the_existing_document_with_200(client):
    test_client, indexer, _ = client
    first = send(test_client, b"same").json()

    second = send(test_client, b"same", "other.txt")

    assert second.status_code == 200
    assert second.json()["id"] == first["id"]
    assert indexer.triggered == 1


def test_an_unsupported_type_is_415(client):
    test_client, _, _ = client

    response = send(test_client, b"\x89PNG\r\n\x1a\n\x00\x00\x00\x00", "photo.pdf")

    assert response.status_code == 415


def test_an_oversized_upload_is_413(client):
    test_client, _, directory = client

    response = send(test_client, b"x" * (MAX_UPLOAD_BYTES + 1))

    assert response.status_code == 413
    assert list(directory.iterdir()) == []


def test_a_body_without_a_file_is_400(client):
    test_client, _, _ = client

    response = test_client.post("/documents", data={"note": "hi"})

    assert response.status_code == 400


def test_list_read_and_delete(client):
    test_client, _, directory = client
    created = send(test_client, b"notes").json()

    assert [row["id"] for row in test_client.get("/documents").json()["documents"]] == [
        created["id"]
    ]
    assert test_client.get(f"/documents/{created['id']}").json()["id"] == created["id"]
    assert test_client.delete(f"/documents/{created['id']}").status_code == 204
    assert test_client.get(f"/documents/{created['id']}").status_code == 404
    assert test_client.delete(f"/documents/{created['id']}").status_code == 404
    assert list(directory.iterdir()) == []
