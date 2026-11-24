"""Portable PDF reports built from computed project evidence."""
import io
import json
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart
from backend.services.exploration_service import dictionary


def build_pdf(dataset, context):
    output = io.BytesIO()
    styles = getSampleStyleSheet()
    story = []
    def paragraph(text, style="BodyText"):
        story.append(Paragraph(escape(str(text)), styles[style]))
        story.append(Spacer(1, 8))
    def table(rows, widths):
        wrapped = [[Paragraph(escape(str(c)), styles["BodyText"]) for c in row] for row in rows]
        t = Table(wrapped, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#e5edf7")), ("VALIGN", (0,0), (-1,-1), "TOP"), ("BOTTOMPADDING", (0,0), (-1,-1), 8), ("LINEBELOW", (0,0), (-1,-1), .3, colors.lightgrey)]))
        story.extend([t, Spacer(1, 12)])
    paragraph("Analytical report", "Title")
    paragraph(f"{dataset.original_filename} — version {context['version']}")
    paragraph(f"Generated {context['at']}. Filters: {json.dumps(context['filters'])}")
    facts = {f["id"]: f["result"] for f in context["facts"]}
    paragraph("Executive summary", "Heading2")
    paragraph(f"The selected data contains {facts['profile']['rows']} rows and {facts['profile']['columns']} columns. Quality score: {facts['quality']['score']}. Missing cells: {facts['quality']['missing_cells']}; duplicate rows: {facts['quality']['duplicate_rows']}.")
    table([["Metric", "Value", "Source"]] + [[k["label"], k["value"], k.get("source_column") or "Dataset"] for k in facts["kpis"]], [190, 110, 180])
    paragraph("Quality components", "Heading2")
    components = facts["quality"]["components"]
    drawing = Drawing(480, 190)
    bars = VerticalBarChart()
    bars.x, bars.y, bars.width, bars.height = 40, 35, 400, 140
    bars.data = [list(components.values())]
    bars.categoryAxis.categoryNames = list(components)
    bars.valueAxis.valueMin, bars.valueAxis.valueMax = 0, 100
    bars.bars[0].fillColor = colors.HexColor("#2763a5")
    drawing.add(bars)
    story.append(drawing)
    paragraph(facts["quality"]["explanation"])
    paragraph("Cleaning", "Heading2")
    paragraph(json.dumps({k: v for k, v in facts["cleaning"].items() if k != "audit_log"}, default=str))
    paragraph("Computed findings", "Heading2")
    for finding in facts["insights"][:10]:
        paragraph(finding.get("message", str(finding)))
    paragraph("Data dictionary", "Heading2")
    table([["Column", "Role / unit", "Description"]] + [[d["column"], f"{d['role']} / {d['unit']}", d["description"] or d["inference"]] for d in dictionary(dataset)], [160, 140, 180])
    paragraph("Limitations", "Heading2")
    paragraph("Column meanings are inferred unless confirmed. Correlation does not establish causation. Quality checks do not establish business accuracy. Report figures use the dataset version and filters shown above; later edits do not update this PDF.")
    SimpleDocTemplate(output, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36).build(story)
    return output.getvalue()
