"""
backend/services/powerbi_service.py

Generates downloadable Power BI files for the interactive dashboard:
1. Complete Power BI Project package (.pbip format with TMDL model, visuals,
   KPI cards, and cleaned data).
2. Standalone Power BI Data Source connector (.pbids) for 1-click import.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import tempfile
import zipfile
from typing import Any, Optional

import pandas as pd


from backend.config import get_settings
from backend.utils.logger import get_logger

logger = get_logger()


def _sanitize_name(name: str) -> str:
    """Sanitizes names for Power BI files, folders, and TMDL identifiers."""
    clean = re.sub(r"[^a-zA-Z0-9_]", "_", str(name)).strip("_")
    return clean or "Dataset"


def generate_pbids(dataset_id: str, local_csv_path: Optional[str] = None) -> bytes:
    """Generates a standalone .pbids (Power BI Data Source) file in JSON format."""
    settings = get_settings()
    connections = []

    # If PostgreSQL is configured and has database, include postgres connection
    if settings.has_database_name:
        connections.append({
            "details": {
                "protocol": "postgresql",
                "address": {
                    "server": f"{settings.database_host}:{settings.database_port}",
                    "database": settings.database_name,
                },
            },
            "options": {},
            "mode": "Import",
        })

    # If local CSV path is provided or can be resolved
    resolved_path = local_csv_path
    if not resolved_path:
        cleaned_file = settings.cleaned_dir / f"{dataset_id}_cleaned.csv"
        if cleaned_file.exists():
            resolved_path = str(cleaned_file.resolve())

    if resolved_path:
        connections.append({
            "details": {
                "protocol": "file",
                "address": {
                    "path": resolved_path,
                },
            },
            "options": {},
        })

    # Fallback generic connection if none resolved
    if not connections:
        connections.append({
            "details": {
                "protocol": "text",
                "address": {
                    "path": f"C:\\data\\{dataset_id}_cleaned.csv",
                },
            },
            "options": {},
        })

    pbids_data = {
        "version": "0.1",
        "connections": connections,
    }

    return json.dumps(pbids_data, indent=2).encode("utf-8")


def generate_powerbi_package(
    dataset_id: str,
    df: pd.DataFrame,
    column_roles: dict[str, str],
    charts: list[dict[str, Any]],
    kpis: list[dict[str, Any]] | None = None,
) -> bytes:
    """Generates a zipped Power BI Project (.pbip) bundle containing:
    - <Report_Name>.pbip (Project definition)
    - <Report_Name>.Report/ (Visual containers, layouts, themes)
    - <Report_Name>.SemanticModel/ (TMDL model schema & Power Query M code)
    - <Table_Name>.csv (Underlying cleaned dataset)
    - <Report_Name>.pbids (Power BI Data Source connector)
    - README.txt (Usage guide)
    """
    import PBI_dashboard_creator as pbi
    clean_id = _sanitize_name(dataset_id)
    report_name = f"Dashboard_{clean_id}"
    table_name = f"{clean_id}_data"

    temp_root = tempfile.mkdtemp()
    try:
        # 1. Export cleaned CSV for Power BI to read
        csv_file_path = os.path.join(temp_root, f"{table_name}.csv")
        df.to_csv(csv_file_path, index=False)

        # 2. Create blank Power BI Project
        pbi.create_new_dashboard(temp_root, report_name)
        dash_path = os.path.join(temp_root, report_name)

        # 3. Add the dataset and generate TMDL model
        pbi.add_csv(dash_path, os.path.abspath(csv_file_path))

        # 4. Add KPI cards (top 3 KPIs if available)
        numeric_columns = [c for c, r in column_roles.items() if r in ("numeric", "currency_amount", "percentage_rate")]
        card_y = 20
        card_w = 260
        card_h = 90
        chart_start_y = 20

        if kpis and numeric_columns:
            card_count = min(3, len(kpis), len(numeric_columns))
            for i in range(card_count):
                kpi_col = numeric_columns[i] if i < len(numeric_columns) else numeric_columns[0]
                kpi_title = kpis[i].get("label", kpi_col.replace("_", " ").title())
                try:
                    pbi.add_card(
                        data_source=table_name,
                        measure_name=kpi_col,
                        dashboard_path=dash_path,
                        page_id="page1",
                        card_id=f"kpi_card_{i}",
                        height=card_h,
                        width=card_w,
                        x_position=20 + i * (card_w + 20),
                        y_position=card_y,
                        title=kpi_title,
                    )
                except Exception as exc:
                    logger.warning("Failed to add Power BI KPI card %s: %s", kpi_title, exc)
            chart_start_y = card_y + card_h + 30

        # 5. Add recommended charts in a responsive 2-column grid
        chart_w = 580
        chart_h = 320
        chart_cols = 2
        added_charts = 0

        for idx, spec in enumerate(charts[:6]):
            ctype = spec.get("chart_type", "bar")
            x_col = spec.get("x") or spec.get("category")
            y_col = spec.get("y") or spec.get("value")

            # Fallback to detected columns if not directly on spec
            if not x_col and column_roles:
                cats = [c for c, r in column_roles.items() if r in ("categorical", "date_time")]
                if cats:
                    x_col = cats[0]

            if not y_col and numeric_columns:
                y_col = numeric_columns[0]

            if not x_col or not y_col or x_col not in df.columns or y_col not in df.columns:
                continue

            # Map chart type to Power BI visual type
            if ctype in ("line", "time_series"):
                pbi_type = "lineChart"
            elif ctype in ("donut", "pie"):
                pbi_type = "pieChart"
            elif ctype in ("horizontal_bar_top_n", "bar"):
                pbi_type = "barChart"
            else:
                pbi_type = "columnChart"

            title = spec.get("title") or f"{y_col.replace('_', ' ').title()} by {x_col.replace('_', ' ').title()}"
            col_idx = added_charts % chart_cols
            row_idx = added_charts // chart_cols

            x_pos = 20 + col_idx * (chart_w + 20)
            y_pos = chart_start_y + row_idx * (chart_h + 20)

            try:
                pbi.add_chart(
                    dashboard_path=dash_path,
                    page_id="page1",
                    chart_id=f"chart_{added_charts}",
                    chart_type=pbi_type,
                    data_source=table_name,
                    chart_title=title,
                    x_axis_title=x_col.replace("_", " ").title(),
                    y_axis_title=y_col.replace("_", " ").title(),
                    x_axis_var=x_col,
                    y_axis_var=y_col,
                    y_axis_var_aggregation_type="Sum",
                    x_position=x_pos,
                    y_position=y_pos,
                    height=chart_h,
                    width=chart_w,
                )
                added_charts += 1
            except Exception as exc:
                logger.warning("Failed to add Power BI chart '%s': %s", title, exc)

        # 6. Copy CSV into report folder so the project is portable
        csv_dest = os.path.join(dash_path, f"{table_name}.csv")
        shutil.copy2(csv_file_path, csv_dest)

        # 7. Add .pbids connector file inside project folder
        pbids_bytes = generate_pbids(dataset_id, local_csv_path=csv_dest)
        pbids_file = os.path.join(dash_path, f"{report_name}.pbids")
        with open(pbids_file, "wb") as f:
            f.write(pbids_bytes)

        # 8. Add README.txt
        readme_content = f"""=============================================================================
Automated Data Analyst — Power BI Dashboard Package
=============================================================================

This archive contains your interactive dashboard exported for Microsoft Power BI:

HOW TO OPEN:
Option 1 (Full Report with Visuals):
  1. Extract this entire ZIP folder to your computer.
  2. Double-click '{report_name}.pbip'.
  3. Microsoft Power BI Desktop will open with your KPI cards and charts pre-configured!

Option 2 (Direct Data Connector):
  1. Double-click '{report_name}.pbids'.
  2. Power BI Desktop will connect directly to '{table_name}.csv'.

Generated for dataset: {dataset_id}
=============================================================================
"""
        with open(os.path.join(dash_path, "README.txt"), "w", encoding="utf-8") as f:
            f.write(readme_content)

        # 9. Zip everything into memory buffer
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(dash_path):
                for file_name in files:
                    full_path = os.path.join(root, file_name)
                    arc_path = os.path.relpath(full_path, temp_root)
                    zf.write(full_path, arc_path)

        zip_buffer.seek(0)
        return zip_buffer.getvalue()

    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

