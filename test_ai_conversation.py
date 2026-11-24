from unittest.mock import Mock

import pytest

from backend.api.ai_routes import ask_your_data
from backend.schemas import AiAskRequest
from backend.services import ai_service


@pytest.mark.parametrize("message", ["hello", "Hello!", "  HELLO there!!!  ", "hi", "Hey there", "good morning", "how are you?", "thanks", "what can you do?"])
def test_small_talk_needs_no_provider_or_dataset(monkeypatch, message):
    enabled = Mock(side_effect=AssertionError("Small talk must not call the provider"))
    monkeypatch.setattr(ai_service, "is_ai_enabled", enabled)
    response = ask_your_data(AiAskRequest(question=message, dataset_id="stale-dataset"))
    assert response.answer
    assert response.sql is None and response.used_ai is False
    enabled.assert_not_called()


@pytest.mark.parametrize("message", ["hello, show total sales", "Which products have 'hello' in their name?", "thanks, now show revenue", "What is the average amount?"])
def test_data_questions_still_reach_sql_generation(monkeypatch, message):
    from backend.api import database_routes
    monkeypatch.setattr(database_routes, "database_metadata", lambda: {"tables": [{"reference": "sales", "columns": []}]})
    monkeypatch.setattr(ai_service, "is_ai_enabled", lambda: True)
    generate = Mock(return_value={"sql": None, "explanation": "Query generation reached"})
    monkeypatch.setattr(ai_service, "generate_sql_from_question", generate)
    response = ask_your_data(AiAskRequest(question=message, table_name="sales"))
    generate.assert_called_once_with(message, "sales", {})
    assert response.answer == "Query generation reached"
