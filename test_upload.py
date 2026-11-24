"""Tests for CSV/XLSX upload validation and parsing (Section 12)."""
import io

import pandas as pd
import pytest

from backend.services.file_service import read_upload
from backend.utils.validators import ValidationError


def _csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def test_read_valid_csv():
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    result = read_upload("sample.csv", _csv_bytes(df), max_mb=10)
    assert result.shape == (2, 2)


def test_read_valid_xlsx():
    df = pd.DataFrame({"a": [1, 2, 3]})
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False)
    result = read_upload("sample.xlsx", buffer.getvalue(), max_mb=10)
    assert result.shape == (3, 1)


def test_reject_unsupported_extension():
    with pytest.raises(ValidationError):
        read_upload("sample.txt", b"a,b\n1,2", max_mb=10)


def test_reject_empty_file():
    with pytest.raises(ValidationError):
        read_upload("empty.csv", b"", max_mb=10)


def test_reject_oversized_file():
    with pytest.raises(ValidationError):
        read_upload("sample.csv", b"a,b\n1,2\n" * 1000, max_mb=0)


def test_reject_malformed_csv_falls_back_gracefully():
    # A file that isn't really tabular should still raise a clean validation
    # error rather than an unhandled stack trace.
    with pytest.raises(ValidationError):
        read_upload("bad.xlsx", b"not a real xlsx file", max_mb=10)
