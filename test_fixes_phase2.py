"""
tests/test_fixes_phase2.py

Tests for Phase 2 fixes:
- Health endpoint (GET /health) returns expected structure
- Gemini AI service behavior when AI is disabled, enabled, and on error
- Config defaults: debug=False, CORS origins exclude 'null', configurable model
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from backend.main import app
from backend.config import Settings
from backend.services import ai_service


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("backend.database.is_connected", lambda: False)
    return TestClient(app)


def test_health_endpoint_structure(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "app" in data
    assert "database_connected" in data
    assert "database_configured" in data
    assert "ai_configured" in data
    assert "ai_enabled" in data
    assert "ai_model" in data
    assert data["debug"] is False


def test_api_health_and_status_aliases(client):
    res_health = client.get("/api/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "healthy"

    res_status = client.get("/api/status")
    assert res_status.status_code == 200
    assert res_status.json()["status"] == "healthy"


def test_cors_origins_excludes_null():
    s = Settings(allowed_origins="http://localhost:8000, null, http://example.com ,")
    origins = s.cors_origins
    assert "null" not in origins
    assert "http://localhost:8000" in origins
    assert "http://example.com" in origins


def test_ai_service_disabled_by_default(monkeypatch):
    monkeypatch.setattr(ai_service, "is_ai_enabled", lambda: False)
    result = ai_service.generate_sql_from_question("How many orders?", "sales", {"id": "int"})
    assert result["used_ai"] is False
    assert result["sql"] is None
    assert "AI mode is disabled" in result["explanation"]

    summary = ai_service.generate_executive_summary([{"label": "Revenue", "value": "100"}], [])
    assert "AI mode is disabled" in summary

    explanation = ai_service.explain_result_in_natural_language("Count", 5)
    assert "AI mode is disabled" in explanation


def test_ai_service_handles_invalid_key_or_model(monkeypatch):
    # Mock settings with enabled AI and a mock client that raises an API error
    mock_settings = MagicMock()
    mock_settings.ai_enabled = True
    mock_settings.gemini_api_key = "fake_invalid_key"
    mock_settings.gemini_model = "invalid-model-name"
    monkeypatch.setattr("backend.services.ai_service.get_settings", lambda: mock_settings)

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception("403 API key not valid or model not found")
    monkeypatch.setattr(ai_service, "_get_client_and_model", lambda: (mock_client, "invalid-model-name"))

    result = ai_service.generate_sql_from_question("What is total revenue?", "sales", {"revenue": "float"})
    assert result["used_ai"] is True
    assert result["sql"] is None
    assert "AI service unavailable" in result["explanation"]
    assert "403" not in result["explanation"]

    summary = ai_service.generate_executive_summary([{"label": "Total", "value": "10"}], [])
    assert "AI summary unavailable" in summary


def test_ai_service_groq_success(monkeypatch):
    mock_settings = MagicMock()
    mock_settings.ai_enabled = True
    mock_settings.groq_api_key = "gsk_test12345"
    mock_settings.groq_model = "llama-3.3-70b-versatile"
    mock_settings.gemini_api_key = ""
    monkeypatch.setattr("backend.services.ai_service.get_settings", lambda: mock_settings)

    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "SELECT * FROM sales LIMIT 10;"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response
    monkeypatch.setattr(ai_service, "_get_client_and_model", lambda: (mock_client, "llama-3.3-70b-versatile"))

    result = ai_service.generate_sql_from_question("Show 10 sales", "sales", {"id": "int"})
    assert result["used_ai"] is True
    assert result["sql"] == "SELECT * FROM sales LIMIT 10;"
    assert result["explanation"] is None
