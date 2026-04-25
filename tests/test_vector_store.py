"""Тесты на логику чанкинга в ingest_to_qdrant (без реального Qdrant/Gemini)."""
from unittest.mock import MagicMock, patch
import pytest

SAMPLE_MD = """# Глава 1

Первый раздел про контакт.

## Контакт и граница

Контакт — это встреча организма со средой. Это основа гештальт-подхода.

### Типы контакта

Контакт может быть полным или прерванным.
"""


def test_ingest_returns_chunk_count():
    """ingest_to_qdrant должен вернуть количество чанков > 0 на валидном тексте."""
    mock_client = MagicMock()
    mock_client.get_collections.return_value = MagicMock(collections=[])

    with (
        patch("app.vector_store.get_client", return_value=mock_client),
        patch("app.vector_store.embed_texts", return_value=[[0.1] * 768] * 5),
    ):
        from app.vector_store import ingest_to_qdrant
        count = ingest_to_qdrant(SAMPLE_MD, "sample.txt", "my_collection")
        assert count > 0
        assert mock_client.upsert.called


def test_ingest_skips_short_chunks():
    """Чанки короче 50 символов не должны попадать в Qdrant."""
    short_text = "Короткий.\n\nЕщё короткий.\n\n" + "A" * 100
    mock_client = MagicMock()
    mock_client.get_collections.return_value = MagicMock(collections=[])

    with (
        patch("app.vector_store.get_client", return_value=mock_client),
        patch("app.vector_store.embed_texts", return_value=[[0.1] * 768]),
    ):
        from app.vector_store import ingest_to_qdrant
        count = ingest_to_qdrant(short_text, "sample.txt", "my_collection")
        # только длинный чанк должен пройти
        assert count == 1


def test_delete_collection_calls_qdrant():
    """delete_collection должен вызвать client.delete_collection."""
    mock_client = MagicMock()
    coll = MagicMock()
    coll.name = "my_collection"
    mock_client.get_collections.return_value = MagicMock(collections=[coll])

    with patch("app.vector_store.get_client", return_value=mock_client):
        from app.vector_store import delete_collection
        delete_collection("my_collection")
        mock_client.delete_collection.assert_called_once_with("my_collection")


def test_delete_collection_noop_if_missing():
    """delete_collection не падает если коллекция не существует."""
    mock_client = MagicMock()
    mock_client.get_collections.return_value = MagicMock(collections=[])

    with patch("app.vector_store.get_client", return_value=mock_client):
        from app.vector_store import delete_collection
        delete_collection("nonexistent")
        mock_client.delete_collection.assert_not_called()
