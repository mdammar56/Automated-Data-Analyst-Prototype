"""
backend/schemas.py

Pydantic request/response models shared across API routers.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class DatabaseSetupRequest(BaseModel):
    host: str = "localhost"
    port: int = 5432
    user: str = "postgres"
    password: str = ""
    database: str


class DatabaseTestResponse(BaseModel):
    success: bool
    message: str


class DatabaseSetupResponse(BaseModel):
    success: bool
    message: str
    database_created: bool = False
    database_name: str


class UploadResponse(BaseModel):
    dataset_id: str
    filename: str
    size_bytes: int
    rows: int
    columns: int


class ColumnProfile(BaseModel):
    original_name: str
    standardized_name: str
    detected_type: str
    detected_role: str
    missing_count: int
    missing_percent: float
    unique_count: int
    sample_values: list[Any] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)


class DatasetProfile(BaseModel):
    dataset_id: str
    rows: int
    columns: int
    duplicate_rows: int
    missing_cells: int
    missing_percent: float
    column_profiles: list[ColumnProfile]
    correlation: dict[str, dict[str, float]] = Field(default_factory=dict)


class CleaningOptions(BaseModel):
    confirm_destructive: bool = False
    handle_missing: bool = True
    remove_exact_duplicates: bool = True
    fix_invalid_values: bool = True
    flag_outliers: bool = True
    run_anomaly_detection: bool = True
    duplicate_subset: Optional[list[str]] = None


class CleaningPreviewResponse(BaseModel):
    dataset_id: str
    plan: list[dict[str, Any]]
    before_summary: dict[str, Any]
    estimated_after_summary: dict[str, Any]


class CleaningApplyResponse(BaseModel):
    dataset_id: str
    before: dict[str, Any]
    after: dict[str, Any]
    audit_log: list[dict[str, Any]]


class LoadToDbRequest(BaseModel):
    dataset_id: str
    table_name: Optional[str] = None


class LoadToDbResponse(BaseModel):
    table_name: str
    rows_loaded: int
    columns: list[str]
    database_name: Optional[str] = None
    total_table_rows: Optional[int] = None


class SqlQueryRequest(BaseModel):
    dataset_id: Optional[str] = None
    query: str
    limit: int = 500
    timeout_ms: int = Field(default=15000, ge=100, le=60000)


class SqlQueryResponse(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool


class AiAskRequest(BaseModel):
    scope: str = "auto"
    dataset_id: Optional[str] = None
    table_name: Optional[str] = None
    question: str


class AiAskResponse(BaseModel):
    answer: str
    sql: Optional[str] = None
    used_ai: bool
