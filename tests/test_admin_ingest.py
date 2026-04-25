"""Тест нового POST /files/ingest endpoint."""
import io
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app
    with patch("app.bot.handlers.startup"), patch("app.bot.handlers.shutdown"):
        return TestClient(app, headers={"X-API-Key": "test-key"})


@pytest.fixture(autouse=True)
def patch_api_key(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "test-key")
    import importlib, app.config as cfg
    importlib.reload(cfg)


def test_ingest_txt_file(client, tmp_path, monkeypatch):
    """POST /files/ingest с .txt файлом должен сохранить файл и вернуть chunks > 0."""
    monkeypatch.setattr("app.api.admin.DOCS_DIR", tmp_path)

    with (
        patch("app.api.admin.ingest_to_qdrant", return_value=42) as mock_ingest,
    ):
        content = b"# Gestalt\n\nText about gestalt therapy " * 20
        response = client.post(
            "/api/admin/files/ingest",
            files={"file": ("session_guides.txt", io.BytesIO(content), "text/plain")},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["collection"] == "session_guides"
    assert data["chunks"] == 42
    assert data["filename"] == "session_guides.txt"
    mock_ingest.assert_called_once()


def test_ingest_rejects_pdf(client):
    """POST /files/ingest должен вернуть 400 для PDF файлов."""
    response = client.post(
        "/api/admin/files/ingest",
        files={"file": ("book.pdf", io.BytesIO(b"fake pdf"), "application/pdf")},
    )
    assert response.status_code == 400


def test_ingest_rejects_unknown_extension(client):
    """POST /files/ingest отклоняет файлы с неподдерживаемым расширением."""
    response = client.post(
        "/api/admin/files/ingest",
        files={"file": ("book.docx", io.BytesIO(b"data"), "application/octet-stream")},
    )
    assert response.status_code == 400
