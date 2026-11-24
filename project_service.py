"""Transactional local project storage. No executable serialization or credentials."""
from __future__ import annotations

import io
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

import pandas as pd

from backend.config import get_settings


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connection():
    from backend.services.file_service import get_settings as storage_settings
    path = storage_settings().cleaned_dir / "projects.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=15) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, document TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS snapshots (id INTEGER PRIMARY KEY, project TEXT NOT NULL, document TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, project TEXT NOT NULL, kind TEXT NOT NULL, document TEXT NOT NULL)")
        yield conn


def encode(value):
    return json.dumps(value, default=str, allow_nan=False)


def get(dataset):
    with connection() as conn:
        row = conn.execute("SELECT document FROM projects WHERE id=?", (dataset.dataset_id,)).fetchone()
    if row:
        doc = json.loads(row[0])
        if doc.get("schema_version") != 1:
            raise ValueError("Unsupported saved project version. Restore a compatible backup.")
        return doc
    return {"schema_version": 1, "dataset_id": dataset.dataset_id,
            "name": dataset.original_filename, "version": 1, "updated_at": now(),
            "overrides": {}, "dashboard": {}, "table": None, "undo": [], "audit": []}


def frame_state(dataset):
    return {"frame": dataset.cleaned_df.to_json(orient="table", date_format="iso", double_precision=15) if dataset.cleaned_df is not None else None,
            "roles": dataset.column_roles, "dtypes": dataset.column_dtypes,
            "mapping": dataset.column_mapping, "options": dataset.cleaning_options,
            "cleaning": dataset.cleaning_result}


def restore(dataset, state):
    dataset.cleaned_df = pd.read_json(io.StringIO(state["frame"]), orient="table") if state.get("frame") else None
    dataset.column_roles = state.get("roles", {})
    dataset.column_dtypes = state.get("dtypes", {})
    dataset.column_mapping = state.get("mapping", {})
    dataset.cleaning_options = state.get("options", {})
    dataset.cleaning_result = state.get("cleaning", {})


def save(dataset, doc=None, previous=None, action=None):
    doc = doc or get(dataset)
    doc["state"] = frame_state(dataset)
    doc["updated_at"] = now()
    with connection() as conn:
        if previous is not None:
            cursor = conn.execute("INSERT INTO snapshots(project, document) VALUES (?,?)", (dataset.dataset_id, encode(previous)))
            doc.setdefault("undo", []).append(cursor.lastrowid)
        if action:
            doc["version"] += 1
            doc.setdefault("audit", []).append({"action": action, "version": doc["version"], "at": now()})
        conn.execute("INSERT OR REPLACE INTO projects VALUES (?,?)", (dataset.dataset_id, encode(doc)))
    return doc


def hydrate(dataset):
    doc = get(dataset)
    if "state" in doc:
        restore(dataset, doc["state"])
    return doc


def checkpoint(dataset):
    return {"state": frame_state(dataset), "overrides": get(dataset).get("overrides", {})}


def undo(dataset):
    doc = get(dataset)
    if not doc["undo"]:
        raise ValueError("No cleaning or dictionary change to undo.")
    with connection() as conn:
        row = conn.execute("SELECT document FROM snapshots WHERE id=? AND project=?", (doc["undo"][-1], dataset.dataset_id)).fetchone()
    if not row:
        raise ValueError("The saved undo snapshot is missing.")
    previous = json.loads(row[0])
    restore(dataset, previous["state"])
    doc["overrides"] = previous["overrides"]
    doc["undo"].pop()
    return save(dataset, doc, action="undo")


def event(dataset, kind, result):
    doc = get(dataset)
    payload = {"version": doc["version"], "at": now(), **result}
    with connection() as conn:
        conn.execute("INSERT INTO events(project,kind,document) VALUES (?,?,?)", (dataset.dataset_id, kind, encode(payload)))


def events(dataset, kind=None):
    with connection() as conn:
        rows = conn.execute("SELECT id,kind,document FROM events WHERE project=? AND (? IS NULL OR kind=?) ORDER BY id DESC LIMIT 100", (dataset.dataset_id, kind, kind)).fetchall()
    version = get(dataset)["version"]
    return [{"id": key, "kind": category, **json.loads(doc), "stale": json.loads(doc)["version"] != version} for key, category, doc in rows]


def list_projects():
    with connection() as conn:
        docs = [json.loads(row[0]) for row in conn.execute("SELECT document FROM projects")]
    return sorted([{k: d[k] for k in ("dataset_id", "name", "version", "updated_at")} for d in docs], key=lambda d: d["updated_at"], reverse=True)
