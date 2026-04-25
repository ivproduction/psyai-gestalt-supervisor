"""Тест: search() принимает collection напрямую и передаёт в Qdrant."""
from unittest.mock import MagicMock, patch
import pytest


def test_search_uses_collection_param():
    """search() должен запрашивать именно переданную коллекцию."""
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value = MagicMock(points=[])

    mock_genai = MagicMock()
    mock_genai.models.embed_content.return_value = MagicMock(
        embeddings=[MagicMock(values=[0.1] * 768)]
    )

    with (
        patch("app.services.search._qdrant", mock_qdrant),
        patch("app.services.search._genai", mock_genai),
    ):
        from app.services.search import search
        search(query="тест", collection="my_collection", top_k=3)

        call_kwargs = mock_qdrant.query_points.call_args
        assert call_kwargs.kwargs["collection_name"] == "my_collection"
        assert call_kwargs.kwargs["limit"] == 3
