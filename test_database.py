"""
Tests for safe-identifier handling and schema generation (Sections 14, 21).
These tests do not require a live PostgreSQL server; connection-dependent
behavior is covered by manual testing per the Windows 11 setup checklist.
"""
import pytest

from backend.services.schema_service import build_create_table_sql, build_table_name
from backend.utils.validators import to_safe_sql_identifier, dedupe_identifiers, is_select_only


def test_safe_identifier_lowercases_and_replaces_spaces():
    assert to_safe_sql_identifier("Customer Name") == "customer_name"


def test_safe_identifier_strips_unsafe_characters():
    assert to_safe_sql_identifier("Total Sales ($)") == "total_sales"


def test_safe_identifier_handles_leading_digit():
    assert to_safe_sql_identifier("2024_revenue").startswith("col_")


def test_dedupe_identifiers_resolves_collisions():
    result = dedupe_identifiers(["customer_name", "customer_name", "age"])
    assert result == ["customer_name", "customer_name_1", "age"]


def test_build_table_name_from_filename():
    assert build_table_name("Sales Report 2024.csv") == "sales_report_2024"


def test_create_table_sql_contains_all_columns():
    sql = build_create_table_sql("sales_data", {"customer_name": "text", "total_sales": "float"})
    assert 'CREATE TABLE IF NOT EXISTS "sales_data"' in sql
    assert '"customer_name" TEXT' in sql
    assert '"total_sales" DOUBLE PRECISION' in sql


def test_create_table_sql_rejects_unsafe_table_name_by_sanitizing():
    sql = build_create_table_sql("sales; DROP TABLE users;--", {"a": "text"})
    assert "DROP TABLE" not in sql


@pytest.mark.parametrize("sql,expected", [
    ("SELECT * FROM sales", True),
    ("select id from customers where age > 30", True),
    ("DROP TABLE sales", False),
    ("DELETE FROM sales", False),
    ("SELECT * FROM sales; DROP TABLE sales;", False),
])
def test_is_select_only(sql, expected):
    assert is_select_only(sql) is expected
