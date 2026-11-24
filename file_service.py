"""
backend/services/file_service.py

Handles file validation, reading (CSV/XLSX with encoding fallbacks) and an
in-process dataset registry keyed by dataset_id. Cleaned/raw DataFrames are
also persisted to disk (data/uploads, data/cleaned) so they survive a backend
restart during local development.
"""
from __future__ import annotations

import io
import uuid
import re
import json
import hashlib
from threading import RLock
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

from backend.config import get_settings
from backend.utils.validators import ValidationError, validate_file_extension, validate_file_size

ENCODING_FALLBACKS = ("utf-8", "utf-8-sig", "latin1", "cp1252")


@dataclass
class Dataset:
    dataset_id: str
    original_filename: str
    raw_df: pd.DataFrame
    cleaned_df: Optional[pd.DataFrame] = None
    column_mapping: dict[str, str] = field(default_factory=dict)
    column_roles: dict[str, str] = field(default_factory=dict)
    column_dtypes: dict[str, str] = field(default_factory=dict)
    profile_cache: dict = field(default_factory=dict)
    cleaning_result: dict = field(default_factory=dict)
    cleaning_options: dict = field(default_factory=dict)
    lock: object = field(default_factory=RLock, repr=False)


class DatasetRegistry:
    """Simple in-memory registry. Adequate for a localhost, single-user v1
    application; a future multi-user version would back this with a proper
    session/database-backed store."""

    def __init__(self) -> None:
        self._datasets: dict[str, Dataset] = {}

    def add(self, dataset: Dataset) -> None:
        self._datasets[dataset.dataset_id] = dataset

    def _try_hydrate_from_disk(self, dataset_id: str) -> Optional[Dataset]:
        settings = get_settings()
        matches = list(settings.upload_dir.glob(f"{dataset_id}_*"))
        if not matches:
            return None
        upload_path = matches[0]
        orig_filename = upload_path.name[len(dataset_id) + 1 :]
        try:
            raw_bytes = upload_path.read_bytes()
            raw_df = read_upload(orig_filename, raw_bytes, settings.upload_max_mb)
        except Exception:
            return None

        cleaned_df = None
        cleaned_path = settings.cleaned_dir / f"{dataset_id}_cleaned.csv"
        if cleaned_path.exists():
            try:
                cleaned_bytes = cleaned_path.read_bytes()
                cleaned_df = _read_csv_with_fallback(cleaned_bytes)
            except Exception:
                pass

        mapping: dict[str, str] = {}
        roles: dict[str, str] = {}
        dtypes: dict[str, str] = {}
        try:
            from backend.services.profiling_service import profile_dataset
            profile_res = profile_dataset(dataset_id, raw_df)
            mapping = profile_res["_column_mapping"]
            roles = profile_res["_column_roles"]
            dtypes = profile_res["_column_dtypes"]
        except Exception:
            pass

        dataset = Dataset(
            dataset_id=dataset_id,
            original_filename=orig_filename,
            raw_df=raw_df,
            cleaned_df=cleaned_df,
            column_mapping=mapping,
            column_roles=roles,
            column_dtypes=dtypes,
        )
        state_path = settings.cleaned_dir / f"{dataset_id}_cleaning.json"
        if state_path.exists() and cleaned_path.exists():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
                if state["sha256"] == hashlib.sha256(cleaned_path.read_bytes()).hexdigest():
                    dataset.cleaning_options = state["options"]
                    dataset.cleaning_result = state["result"]
            except (ValueError, KeyError, OSError):
                pass
        from backend.services import project_service
        project_service.hydrate(dataset)
        return dataset

    def get(self, dataset_id: str) -> Dataset:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", dataset_id):
            raise ValidationError("Invalid dataset identifier.")
        if dataset_id not in self._datasets:
            hydrated = self._try_hydrate_from_disk(dataset_id)
            if hydrated is not None:
                self._datasets[dataset_id] = hydrated
                return hydrated
            raise ValidationError(f"Unknown dataset_id '{dataset_id}'. Upload a file first.")
        return self._datasets[dataset_id]

    def update_cleaned(self, dataset_id: str, df: pd.DataFrame) -> None:
        self.get(dataset_id).cleaned_df = df

    def set_columns(self, dataset_id: str, mapping: dict[str, str], roles: dict[str, str], dtypes: dict[str, str]) -> None:
        ds = self.get(dataset_id)
        ds.column_mapping = mapping
        ds.column_roles = roles
        ds.column_dtypes = dtypes



registry = DatasetRegistry()


def _read_csv_with_fallback(raw_bytes: bytes) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in ENCODING_FALLBACKS:
        try:
            return pd.read_csv(io.BytesIO(raw_bytes), encoding=encoding)
        except (UnicodeDecodeError, pd.errors.ParserError) as exc:
            last_error = exc
            continue
    raise ValidationError(
        f"Could not parse the CSV file with common encodings ({', '.join(ENCODING_FALLBACKS)}). "
        f"Original error: {last_error}"
    )


def read_upload(filename: str, raw_bytes: bytes, max_mb: int) -> pd.DataFrame:
    validate_file_size(len(raw_bytes), max_mb)
    ext = validate_file_extension(filename)

    try:
        if ext == ".csv":
            if b"\x00" in raw_bytes or raw_bytes.lstrip().lower().startswith((b"<!doctype html", b"<html")):
                raise ValidationError("Expected CSV text; received binary or HTML content.")
            df = _read_csv_with_fallback(raw_bytes)
        else:
            df = pd.read_excel(io.BytesIO(raw_bytes))
    except ValidationError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ValidationError(f"Failed to read '{filename}': {exc}") from exc

    if df.empty or df.shape[1] == 0:
        raise ValidationError(f"'{filename}' does not contain any readable rows/columns.")

    return df


def store_new_dataset(filename: str, raw_bytes: bytes) -> Dataset:
    settings = get_settings()
    df = read_upload(filename, raw_bytes, settings.upload_max_mb)

    dataset_id = uuid.uuid4().hex[:12]
    upload_path = settings.upload_dir / f"{dataset_id}_{Path(filename).name}"
    upload_path.write_bytes(raw_bytes)

    dataset = Dataset(dataset_id=dataset_id, original_filename=filename, raw_df=df)
    registry.add(dataset)
    from backend.services import project_service
    project_service.save(dataset)
    return dataset


def persist_cleaned(dataset_id: str, df: pd.DataFrame) -> Path:
    settings = get_settings()
    path = settings.cleaned_dir / f"{dataset_id}_cleaned.csv"
    temporary = path.with_suffix(".tmp")
    df.to_csv(temporary, index=False)
    temporary.replace(path)
    return path


def persist_cleaning_state(path: Path, options: dict, result: dict) -> None:
    state = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "options": options, "result": result}
    destination = path.with_name(f"{result['dataset_id']}_cleaning.json")
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(state), encoding="utf-8")
    temporary.replace(destination)
