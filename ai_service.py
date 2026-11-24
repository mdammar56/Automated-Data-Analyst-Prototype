"""
backend/services/ai_service.py

Optional AI Layer (Groq / Gemini) â€” "Ask Your Data" (Section 29). AI is strictly
optional: the core application works without an API key, and this
module reads the key only from the server-side environment, never from the
frontend. Only minimal, aggregated/structured context is sent to the LLM â€”
never raw datasets or credentials (Sections 10.2, 32).
"""
from __future__ import annotations

from typing import Any, Optional
import re

from backend.config import get_settings
from backend.utils.logger import get_logger
from backend.utils.validators import is_select_only

logger = get_logger()


def conversational_reply(message: str) -> Optional[str]:
    """Handle standalone small talk without SQL, credentials, or dataset access.

    Match the complete message so 'hello, show total sales' still reaches
    the analytics flow.
    """
    normalized = re.sub(r"[.!?,]+", " ", message.casefold())
    normalized = " ".join(normalized.split())
    if re.fullmatch(r"(?:hi|hello|hey|good morning|good afternoon|good evening)(?: there| assistant)?", normalized):
        return "Hello there! How can I help you? You can ask me questions about your data."
    if normalized in {"how are you", "how are you doing"}:
        return "I'm ready to help! What would you like to explore in your data?"
    if normalized in {"thanks", "thank you", "thanks a lot", "thank you very much"}:
        return "You're welcome! Let me know if you'd like to explore anything else in your data."
    if normalized in {"help", "what can you do", "how can you help me"}:
        return ("I can help you explore your data with totals, averages, comparisons, and trends. "
                "For data questions, load your dataset into PostgreSQL and select its table, "
                "then ask something like 'What are the top categories by sales?'")
    return None


def _is_str_and_filled(val: Any) -> bool:
    return isinstance(val, str) and bool(val.strip())


def is_ai_enabled() -> bool:
    return get_settings().ai_enabled


def _get_client_and_model():
    """Lazily import and configure Groq or Google GenAI client only when needed, so
    the rest of the application works fully without the optional dependency
    being installed or configured."""
    if not is_ai_enabled():
        return None, None
    settings = get_settings()

    # Prioritize Groq
    if _is_str_and_filled(getattr(settings, "groq_api_key", None)):
        try:
            from groq import Groq

            client = Groq(api_key=settings.groq_api_key.strip(), timeout=30.0, max_retries=1)
            model_name = settings.groq_model.strip() or "openai/gpt-oss-120b"
            return client, model_name
        except Exception as exc:
            logger.error("Failed to initialize Groq client (%s)", type(exc).__name__)
            return None, None

    # Fallback to Gemini
    if _is_str_and_filled(getattr(settings, "gemini_api_key", None)):
        try:
            from google import genai

            client = genai.Client(api_key=settings.gemini_api_key)
            model_name = settings.gemini_model or "gemini-2.5-flash"
            return client, model_name
        except Exception as exc:
            logger.error("Failed to initialize Google GenAI client (%s)", type(exc).__name__)
            return None, None

    return None, None


def _generate_text(client: Any, model_name: str, prompt: str) -> str:
    """Invokes chat completion on Groq or generate_content on Gemini/mock client."""
    settings = get_settings()

    # Prioritize Groq if Groq API key is explicitly configured
    if _is_str_and_filled(getattr(settings, "groq_api_key", None)):
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        return (response.choices[0].message.content or "").strip()

    # If Gemini is configured (or default)
    if hasattr(client, "models") and hasattr(client.models, "generate_content"):
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
        )
        return (getattr(response, "text", "") or "").strip()

    # If duck-typed Groq client
    if hasattr(client, "chat") and hasattr(client.chat, "completions"):
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        return (response.choices[0].message.content or "").strip()

    raise ValueError(f"Unsupported AI client type: {type(client)}")


def build_schema_context(table_name: Optional[str], column_dtypes: dict[str, str]) -> str:
    lines = [f"Table: {table_name}" if table_name else "Dataset (not yet loaded to a table)"]
    for col, dtype in column_dtypes.items():
        lines.append(f"- {col} ({dtype})")
    return "\n".join(lines)


def generate_sql_from_question(question: str, table_name: str, column_dtypes: dict[str, str]) -> dict[str, Any]:
    if not is_ai_enabled():
        return {"sql": None, "explanation": "AI mode is disabled (no API key configured).", "used_ai": False}
    client, model_name = _get_client_and_model()
    if client is None:
        return {"sql": None, "explanation": "AI client initialization failed. Verify the installed provider package and server configuration, then restart the backend.", "used_ai": False}

    schema_context = build_schema_context(table_name, column_dtypes)
    prompt = (
        "You are a careful SQL assistant for a PostgreSQL analytics tool. "
        "Given the schema below and a user question, respond with ONLY a single "
        "read-only SELECT statement (no explanations, no markdown fences, no semicolons chained). "
        "Never use INSERT, UPDATE, DELETE, DROP, TRUNCATE, ALTER, GRANT, REVOKE, or COPY.\n\n"
        f"Schema:\n{schema_context}\n\nQuestion: {question}\n\nSQL:"
    )
    try:
        raw_text = _generate_text(client, model_name, prompt)
        sql_text = raw_text.strip().strip("`").strip()
        if sql_text.lower().startswith("sql"):
            sql_text = sql_text[3:].strip()

        if not is_select_only(sql_text):
            return {
                "sql": None,
                "explanation": "The AI-generated statement did not pass the read-only SQL safety check and was blocked.",
                "used_ai": True,
            }

        return {"sql": sql_text, "explanation": None, "used_ai": True}
    except Exception as exc:
        logger.error("AI query generation failed (%s)", type(exc).__name__)
        return {
            "sql": None,
            "explanation": _provider_error(exc),
            "used_ai": True,
        }


def explain_result_in_natural_language(question: str, result_preview: Any) -> str:
    if not is_ai_enabled():
        return "AI mode is disabled (no API key configured). Showing raw results only."
    client, model_name = _get_client_and_model()
    if client is None:
        return "AI mode is disabled (no API key configured). Showing raw results only."

    prompt = (
        "Explain the following query result in one or two clear sentences for a "
        "business user. Do not restate raw SQL. Question was: "
        f"{question}\n\nResult summary: {result_preview}"
    )
    try:
        return _generate_text(client, model_name, prompt)
    except Exception as exc:
        logger.error("AI explanation generation failed (%s)", type(exc).__name__)
        return _provider_error(exc)


def generate_executive_summary(kpis: list[dict[str, Any]], insights: list[dict[str, Any]]) -> str:
    if not is_ai_enabled():
        kpi_text = "; ".join(f"{k['label']}: {k['value']}" for k in kpis[:5])
        return f"AI mode is disabled. Key figures â€” {kpi_text}."
    client, model_name = _get_client_and_model()
    if client is None:
        kpi_text = "; ".join(f"{k['label']}: {k['value']}" for k in kpis[:5])
        return f"AI mode is disabled. Key figures â€” {kpi_text}."

    prompt = (
        "Write a concise 3-4 sentence executive summary for a business stakeholder "
        f"based on these KPIs: {kpis}\nand these insights: {insights}"
    )
    try:
        return _generate_text(client, model_name, prompt)
    except Exception as exc:
        logger.error("AI executive summary failed (%s)", type(exc).__name__)
        kpi_text = "; ".join(f"{k['label']}: {k['value']}" for k in kpis[:5])
        return f"AI summary unavailable ({exc}). Key figures â€” {kpi_text}."


def _provider_error(exc: Exception) -> str:
    status = getattr(exc, "status_code", None)
    if status in (401, 403):
        return "AI authentication failed. Verify GROQ_API_KEY and account access, then restart the backend."
    if status in (400, 404):
        return "AI request or model unavailable. Verify GROQ_MODEL and access to that model."
    if status == 429:
        return "AI rate limit reached. Wait and retry, or check your provider quota."
    return "AI service unavailable. Check network access and provider status, then retry."
