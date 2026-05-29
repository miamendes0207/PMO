# ============================================================
# modules/export_pdf.py — ScopeSight v2.6 PROFESSIONAL
# PDF Export Utilities - Premium visual design
#
# IMPROVEMENTS:
# - Professional typography with custom font sizing
# - Generous whitespace and better spacing
# - Gradient-style KPI cards with shadows
# - Properly rendered Plotly charts with color
# - Clean section dividers
# - Better contrast and readability
# ============================================================

import io
import tempfile
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# -----------------------------
# Professional Color Palette
# -----------------------------
THEME = {
    "ink": colors.HexColor("#1e293b"),  # Darker, richer text
    "muted": colors.HexColor("#64748b"),
    "light": colors.HexColor("#94a3b8"),
    "border": colors.HexColor("#e2e8f0"),
    "border_strong": colors.HexColor("#cbd5e1"),
    "panel_bg": colors.white,
    "section_bg": colors.HexColor("#f8fafc"),
    "section_label": colors.HexColor("#475569"),
    "table_header_bg": colors.HexColor("#f1f5f9"),
    "zebra_a": colors.white,
    "zebra_b": colors.HexColor("#f8fafc"),
    # Alert colors
    "info_bg": colors.HexColor("#eff6ff"),
    "info_border": colors.HexColor("#3b82f6"),
    "warn_bg": colors.HexColor("#fffbeb"),
    "warn_border": colors.HexColor("#f59e0b"),
    "danger_bg": colors.HexColor("#fef2f2"),
    "danger_border": colors.HexColor("#ef4444"),
    "success_bg": colors.HexColor("#f0fdf4"),
    "success_border": colors.HexColor("#22c55e"),
    # KPI card colors
    "kpi_dark_blue": colors.HexColor("#1e3a8a"),
    "kpi_blue": colors.HexColor("#2563eb"),
    "kpi_green": colors.HexColor("#059669"),
    "kpi_teal": colors.HexColor("#0d9488"),
    "kpi_orange": colors.HexColor("#ea580c"),
    "kpi_amber": colors.HexColor("#d97706"),
}


# ============================================================
# Public API
# ============================================================
def export_dashboard_pdf(
        title: str,
        sections: list,
        *,
        subtitle: str = "",
        kpis: Optional[List[Dict[str, Any]]] = None,
        filename: Optional[str] = None,
        allow_emoji: bool = False,
):
    """
    Professional dashboard PDF export with premium visual design.

    Automatically filters:
    - Executive Summary sections
    - Risk Concentration tables

    Shows only top 4 KPIs in a 2x2 grid.
    """

    styles = getSampleStyleSheet()

    # Compact Typography for single page
    title_style = ParagraphStyle(
        "DashTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=18,
        leading=22,
        textColor=THEME["ink"],
        spaceAfter=2,
        fontName="Helvetica-Bold",
    )

    subtitle_style = ParagraphStyle(
        "DashSubtitle",
        parent=styles["BodyText"],
        alignment=TA_CENTER,
        fontSize=9,
        leading=12,
        textColor=THEME["muted"],
        spaceAfter=8,
    )

    section_style = ParagraphStyle(
        "DashSectionLabel",
        parent=styles["BodyText"],
        alignment=TA_LEFT,
        fontSize=8,
        leading=10,
        textColor=THEME["section_label"],
        spaceBefore=6,
        spaceAfter=3,
        fontName="Helvetica-Bold",
    )

    panel_header_style = ParagraphStyle(
        "DashPanelHeader",
        parent=styles["Heading3"],
        alignment=TA_LEFT,
        fontSize=10.5,
        leading=13,
        textColor=THEME["ink"],
        spaceAfter=4,
        fontName="Helvetica-Bold",
    )

    body_style = ParagraphStyle(
        "DashBody",
        parent=styles["BodyText"],
        alignment=TA_LEFT,
        fontSize=9,
        leading=12,
        textColor=THEME["ink"],
    )

    small_style = ParagraphStyle(
        "DashSmall",
        parent=styles["BodyText"],
        alignment=TA_LEFT,
        fontSize=8,
        leading=10,
        textColor=THEME["muted"],
    )

    caption_style = ParagraphStyle(
        "DashCaption",
        parent=styles["BodyText"],
        alignment=TA_LEFT,
        fontSize=7.5,
        leading=10,
        textColor=THEME["light"],
        fontName="Helvetica-Oblique",
    )

    table_cell_style = ParagraphStyle(
        "DashTableCell",
        parent=styles["BodyText"],
        alignment=TA_LEFT,
        fontSize=8,
        leading=10,
        textColor=THEME["ink"],
    )

    story: List[Any] = []

    # Title block - compact
    story.append(Spacer(1, 4))
    story.append(Paragraph(_escape(title), title_style))
    if subtitle:
        story.append(Paragraph(_escape(subtitle), subtitle_style))
    else:
        story.append(Spacer(1, 4))

    # Compact KPI tiles - Top 4 only
    if kpis:
        top_4_kpis = kpis[:4]
        story.append(_kpi_grid_compact(top_4_kpis, styles=styles, allow_emoji=allow_emoji))
        story.append(Spacer(1, 8))

    # Process blocks
    for block in (sections or []):
        # Legacy format - SKIP Executive Summary
        if isinstance(block, dict) and "type" not in block and ("header" in block or "text" in block):
            hdr = (block.get("header") or "Summary").strip()
            if "executive summary" in hdr.lower():
                continue
            txt = block.get("text") or ""
            story.append(_panel_text(hdr, txt, panel_header_style, body_style))
            story.append(Spacer(1, 6))
            continue

        if not isinstance(block, dict):
            continue

        btype = (block.get("type") or "").lower().strip()

        if btype == "section":
            label = (block.get("label") or "").strip()
            if label:
                story.append(_section_divider(label, section_style))
                story.append(Spacer(1, 2))

        elif btype == "text":
            hdr = (block.get("header") or "Summary").strip()
            if "executive summary" in hdr.lower():
                continue
            txt = block.get("text") or ""
            story.append(_panel_text(hdr, txt, panel_header_style, body_style))
            story.append(Spacer(1, 6))

        elif btype == "insight":
            kind = (block.get("kind") or "info").lower().strip()
            txt = block.get("text") or ""
            if not allow_emoji:
                txt = _strip_emojis(txt)
            story.append(_insight_box(txt, kind=kind, body_style=body_style))
            story.append(Spacer(1, 6))

        elif btype == "mini_kpis":
            items = block.get("items") or []
            story.append(_mini_kpi_row_compact(items, styles=styles))
            story.append(Spacer(1, 6))

        elif btype == "table":
            hdr = (block.get("header") or "Table").strip()
            if "risk concentration" in hdr.lower():
                continue
            data = block.get("data")
            cols = block.get("columns")
            rename = block.get("rename") or None
            story.append(_panel_table(hdr, data, cols, rename, panel_header_style, small_style, table_cell_style))
            story.append(Spacer(1, 6))

        elif btype == "plotly":
            hdr = (block.get("header") or "Chart").strip()
            fig = block.get("fig")
            caption = block.get("caption") or ""
            story.append(_panel_plotly_compact(hdr, fig, caption, panel_header_style, caption_style))
            story.append(Spacer(1, 6))

    # Build PDF in LANDSCAPE orientation
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        doc = SimpleDocTemplate(
            tmp.name,
            pagesize=landscape(A4),
            leftMargin=12 * mm,
            rightMargin=12 * mm,
            topMargin=10 * mm,
            bottomMargin=10 * mm,
            title=title,
        )
        doc.build(story)
        tmp.seek(0)
        pdf_data = tmp.read()

    st.download_button(
        label="📄 Export Dashboard to PDF",
        data=pdf_data,
        file_name=filename or f"{title.replace(' ', '_')}.pdf",
        mime="application/pdf",
        use_container_width=True,
    )


# ============================================================
# Compact KPI Grid - LANDSCAPE 1x4 layout
# ============================================================
def _kpi_grid_compact(kpis: List[Dict[str, Any]], styles, *, allow_emoji: bool) -> Table:
    """
    Creates a 1x4 horizontal grid of KPI cards for landscape layout.
    """
    kpis_to_show = kpis[:4]

    # Ensure we have exactly 4 items
    while len(kpis_to_show) < 4:
        kpis_to_show.append({"label": "", "value": "", "bg": "#f8fafc", "icon": "", "note": ""})

    def _tile_html(k: Dict[str, Any]) -> str:
        icon = (k.get("icon") or "").strip()
        if not allow_emoji:
            icon = ""
        label = (k.get("label") or "").strip()
        value = str(k.get("value") if k.get("value") is not None else "").strip()
        note = (k.get("note") or "").strip()

        # Compact styling
        note_line = f"<br/><font size='7.5' color='#cbd5e1'>{_escape(note)}</font>" if note else ""
        icon_line = f"<font size='11'><b>{_escape(icon)}</b></font><br/>" if icon else ""

        return (
            f"{icon_line}"
            f"<font size='22' color='white'><b>{_escape(value)}</b></font><br/>"
            f"<font size='8.5' color='#e0e7ff'><b>{_escape(label.upper())}</b></font>"
            f"{note_line}"
        )

    # Create single row with 4 columns
    row_data = []
    for k in kpis_to_show:
        bg = (k.get("bg") or "#2563eb").strip()
        cell = Paragraph(_tile_html(k), styles["BodyText"])
        row_data.append((cell, bg))

    data = [[c[0] for c in row_data]]
    t = Table(data, hAlign="LEFT")

    # Compact padding
    ts = TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("BOX", (0, 0), (-1, -1), 0.8, THEME["border_strong"]),
        ("INNERGRID", (0, 0), (-1, -1), 0.8, THEME["border_strong"]),
    ])

    # Apply background colors
    for c, (_, bg) in enumerate(row_data):
        ts.add("BACKGROUND", (c, 0), (c, 0), colors.HexColor(bg))

    t.setStyle(ts)
    return KeepTogether([t])


# ============================================================
# Professional KPI Grid - 2x2 layout with style (ORIGINAL - UNUSED)
# ============================================================
def _kpi_grid_professional(kpis: List[Dict[str, Any]], styles, *, allow_emoji: bool) -> Table:
    """
    Creates a professional 2x2 grid of KPI cards with proper styling.
    """
    kpis_to_show = kpis[:4]

    # Ensure we have exactly 4 items
    while len(kpis_to_show) < 4:
        kpis_to_show.append({"label": "", "value": "", "bg": "#f8fafc", "icon": "", "note": ""})

    def _tile_html(k: Dict[str, Any]) -> str:
        icon = (k.get("icon") or "").strip()
        if not allow_emoji:
            icon = ""
        label = (k.get("label") or "").strip()
        value = str(k.get("value") if k.get("value") is not None else "").strip()
        note = (k.get("note") or "").strip()

        # Professional styling with better hierarchy
        note_line = f"<br/><font size='9.5' color='#cbd5e1'>{_escape(note)}</font>" if note else ""
        icon_line = f"<font size='16'><b>{_escape(icon)}</b></font><br/>" if icon else ""

        return (
            f"{icon_line}"
            f"<font size='32' color='white'><b>{_escape(value)}</b></font><br/>"
            f"<font size='10' color='#e0e7ff'><b>{_escape(label.upper())}</b></font>"
            f"{note_line}"
        )

    # Create 2x2 grid
    rows = []
    for i in range(0, 4, 2):
        row_kpis = kpis_to_show[i:i + 2]
        row_data = []
        for k in row_kpis:
            bg = (k.get("bg") or "#2563eb").strip()
            cell = Paragraph(_tile_html(k), styles["BodyText"])
            row_data.append((cell, bg))
        rows.append(row_data)

    data = [[c[0] for c in r] for r in rows]
    t = Table(data, hAlign="LEFT")

    # Professional styling with more padding
    ts = TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 20),
        ("RIGHTPADDING", (0, 0), (-1, -1), 20),
        ("TOPPADDING", (0, 0), (-1, -1), 22),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 22),
        ("BOX", (0, 0), (-1, -1), 1, THEME["border_strong"]),
        ("INNERGRID", (0, 0), (-1, -1), 1, THEME["border_strong"]),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
    ])

    # Apply background colors
    for r, row in enumerate(rows):
        for c, (_, bg) in enumerate(row):
            ts.add("BACKGROUND", (c, r), (c, r), colors.HexColor(bg))

    t.setStyle(ts)
    return KeepTogether([t])


# ============================================================
# Compact Mini KPI Row
# ============================================================
def _mini_kpi_row_compact(items: List[Dict[str, Any]], styles) -> KeepTogether:
    """Compact mini KPI row for single page layout."""
    per_row = 3
    chunk = (items or [])[:3]
    while len(chunk) < per_row:
        chunk.append({"label": "", "value": "", "bg": "#f8fafc"})

    def _mini_html(k: Dict[str, Any]) -> str:
        label = _escape((k.get("label") or "").strip().upper())
        value = _escape(str(k.get("value") if k.get("value") is not None else "").strip())
        note = (k.get("note") or "").strip()
        note_line = f"<br/><font size='7' color='#cbd5e1'>{_escape(note)}</font>" if note else ""
        return (
            f"<font size='16' color='white'><b>{value}</b></font><br/>"
            f"<font size='8' color='#e0e7ff'><b>{label}</b></font>"
            f"{note_line}"
        )

    row = []
    bgs = []
    for k in chunk:
        bg = (k.get("bg") or "#475569").strip()
        bgs.append(bg)
        row.append(Paragraph(_mini_html(k), styles["BodyText"]))

    t = Table([row], hAlign="LEFT")
    ts = TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("BOX", (0, 0), (-1, -1), 0.8, THEME["border_strong"]),
        ("INNERGRID", (0, 0), (-1, -1), 0.8, THEME["border_strong"]),
    ])
    for c, bg in enumerate(bgs):
        ts.add("BACKGROUND", (c, 0), (c, 0), colors.HexColor(bg))
    t.setStyle(ts)

    return KeepTogether([t])


# ============================================================
# Professional Mini KPI Row (ORIGINAL - UNUSED)
# ============================================================
def _mini_kpi_row_professional(items: List[Dict[str, Any]], styles) -> KeepTogether:
    """Enhanced mini KPI row with better styling."""
    per_row = 3
    chunk = (items or [])[:3]
    while len(chunk) < per_row:
        chunk.append({"label": "", "value": "", "bg": "#f8fafc"})

    def _mini_html(k: Dict[str, Any]) -> str:
        label = _escape((k.get("label") or "").strip().upper())
        value = _escape(str(k.get("value") if k.get("value") is not None else "").strip())
        note = (k.get("note") or "").strip()
        note_line = f"<br/><font size='9' color='#cbd5e1'>{_escape(note)}</font>" if note else ""
        return (
            f"<font size='20' color='white'><b>{value}</b></font><br/>"
            f"<font size='9.5' color='#e0e7ff'><b>{label}</b></font>"
            f"{note_line}"
        )

    row = []
    bgs = []
    for k in chunk:
        bg = (k.get("bg") or "#475569").strip()
        bgs.append(bg)
        row.append(Paragraph(_mini_html(k), styles["BodyText"]))

    t = Table([row], hAlign="LEFT")
    ts = TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("BOX", (0, 0), (-1, -1), 1, THEME["border_strong"]),
        ("INNERGRID", (0, 0), (-1, -1), 1, THEME["border_strong"]),
    ])
    for c, bg in enumerate(bgs):
        ts.add("BACKGROUND", (c, 0), (c, 0), colors.HexColor(bg))
    t.setStyle(ts)

    return KeepTogether([t])


# ============================================================
# Compact Section Divider
# ============================================================
def _section_divider(label: str, section_style) -> KeepTogether:
    """Compact section divider."""
    return KeepTogether([
        Paragraph(_escape(label.upper()), section_style),
        HRFlowable(
            width="100%",
            thickness=0.8,
            color=THEME["border_strong"],
            spaceBefore=2,
            spaceAfter=4,
        )
    ])


# ============================================================
# Panel Components
# ============================================================
def _panel_text(header: str, text: str, header_style, body_style) -> KeepTogether:
    safe = _escape_multiline(text or "")
    return KeepTogether([
        Paragraph(_escape(header), header_style),
        Spacer(1, 2),
        _panel_box([Paragraph(safe, body_style)], compact=True),
    ])


def _panel_table(
        header: str,
        data: Any,
        columns: Optional[Sequence[str]],
        rename: Optional[Dict[str, str]],
        header_style,
        small_style,
        cell_style,
) -> KeepTogether:
    df = _to_dataframe(data, columns)

    if df is None or df.empty:
        return KeepTogether([
            Paragraph(_escape(header), header_style),
            Spacer(1, 2),
            _panel_box([Paragraph("No data available.", small_style)], compact=True),
        ])

    out = df.copy()

    if rename:
        out = out.rename(columns=rename)
    else:
        out = out.rename(columns={c: _prettify_header(c) for c in out.columns})

    max_cols = 8
    if out.shape[1] > max_cols:
        out = out.iloc[:, :max_cols]

    for c in out.columns:
        if pd.api.types.is_numeric_dtype(out[c]):
            continue
        out[c] = out[c].astype(str).replace({"nan": "", "NaT": ""})

    table_data: List[List[Any]] = []
    table_data.append([Paragraph(f"<b>{_escape(str(c))}</b>", cell_style) for c in out.columns])

    for _, row in out.iterrows():
        cells = []
        for c in out.columns:
            v = row[c]
            s = "" if pd.isna(v) else str(v)
            cells.append(Paragraph(_escape(s), cell_style))
        table_data.append(cells)

    col_widths = _estimate_col_widths(out, page_width_mm=297, left_right_margin_mm=24, max_cols=max_cols)

    t = Table(table_data, hAlign="LEFT", colWidths=col_widths)
    ts = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), THEME["table_header_bg"]),
        ("TEXTCOLOR", (0, 0), (-1, 0), THEME["ink"]),
        ("GRID", (0, 0), (-1, -1), 0.6, THEME["border"]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ])

    for r in range(1, len(table_data)):
        bg = THEME["zebra_a"] if (r % 2 == 1) else THEME["zebra_b"]
        ts.add("BACKGROUND", (0, r), (-1, r), bg)

    for i, c in enumerate(df.columns[: out.shape[1]]):
        if pd.api.types.is_numeric_dtype(df[c]):
            ts.add("ALIGN", (i, 1), (i, -1), "RIGHT")

    t.setStyle(ts)

    return KeepTogether([
        Paragraph(_escape(header), header_style),
        Spacer(1, 3),
        _panel_box([t], compact=True),
    ])


def _insight_box(text: str, *, kind: str, body_style) -> KeepTogether:
    kind = (kind or "info").lower().strip()
    if kind == "warn":
        bg, border = THEME["warn_bg"], THEME["warn_border"]
    elif kind == "danger":
        bg, border = THEME["danger_bg"], THEME["danger_border"]
    elif kind == "success":
        bg, border = THEME["success_bg"], THEME["success_border"]
    else:
        bg, border = THEME["info_bg"], THEME["info_border"]

    p = Paragraph(_escape_multiline(text or ""), body_style)
    box = _panel_box([p], bg=bg, border=border, border_w=1, compact=True)
    return KeepTogether([box])


def _panel_plotly_compact(header: str, fig: Any, caption: str, header_style, caption_style) -> KeepTogether:
    """
    COMPACT: Embeds Plotly charts optimized for single page.
    """
    content: List[Any] = [Paragraph(_escape(header), header_style)]
    content.append(Spacer(1, 3))

    if fig is None:
        content.append(_panel_box([Paragraph("No chart provided.", caption_style)], compact=True))
        return KeepTogether(content)

    try:
        # Create a copy to avoid modifying the original
        import plotly.graph_objects as go
        fig_copy = go.Figure(fig)

        # COMPACT CHART STYLING
        fig_copy.update_layout(
            # Clean backgrounds
            plot_bgcolor='white',
            paper_bgcolor='white',

            # Compact fonts
            font=dict(
                family="Helvetica, Arial, sans-serif",
                size=10,
                color='#1e293b'
            ),

            # X-axis styling
            xaxis=dict(
                showgrid=True,
                gridcolor='#e2e8f0',
                gridwidth=0.6,
                showline=True,
                linewidth=1.5,
                linecolor='#64748b',
                mirror=True,
                ticks='outside',
                tickwidth=1,
                ticklen=4,
                tickcolor='#64748b',
                tickfont=dict(size=9, color='#1e293b', family="Helvetica"),
                title_font=dict(size=10, color='#1e293b', family="Helvetica Bold"),
            ),

            # Y-axis styling
            yaxis=dict(
                showgrid=True,
                gridcolor='#e2e8f0',
                gridwidth=0.6,
                showline=True,
                linewidth=1.5,
                linecolor='#64748b',
                mirror=True,
                ticks='outside',
                tickwidth=1,
                ticklen=4,
                tickcolor='#64748b',
                tickfont=dict(size=9, color='#1e293b', family="Helvetica"),
                title_font=dict(size=10, color='#1e293b', family="Helvetica Bold"),
            ),

            # Legend styling
            showlegend=True,
            legend=dict(
                font=dict(size=8, color='#1e293b', family="Helvetica"),
                bgcolor='rgba(255,255,255,0.95)',
                bordercolor='#cbd5e1',
                borderwidth=1,
                x=1.01,
                y=1,
                xanchor='left',
                yanchor='top',
            ),

            # Compact margins
            margin=dict(l=60, r=40, t=30, b=60),

            # Title if present
            title=dict(
                font=dict(size=11, color='#1e293b', family="Helvetica Bold"),
                x=0.5,
                xanchor='center',
            ),
        )

        # LANDSCAPE OPTIMIZED EXPORT - wider aspect ratio
        png_bytes = fig_copy.to_image(
            format="png",
            width=2800,  # Wider for landscape
            height=900,  # Same height
            scale=3,  # Good quality
        )

        img = Image(io.BytesIO(png_bytes))
        img.hAlign = "LEFT"

        # Calculate available width for LANDSCAPE
        available_w = (landscape(A4)[0] - (12 * mm) - (12 * mm))
        img.drawWidth = available_w
        img.drawHeight = available_w * (900 / 2800)

        items: List[Any] = [img]

        if caption:
            items.append(Spacer(1, 3))
            items.append(Paragraph(_escape(caption), caption_style))

        content.append(_panel_box(items, bg=colors.white, border=THEME["border_strong"], border_w=0.8, compact=True))
        return KeepTogether(content)

    except Exception as e:
        msg = f"Chart rendering failed.\n{type(e).__name__}: {e}"
        if caption:
            msg += f"\n{caption}"
        content.append(_panel_box([Paragraph(_escape_multiline(msg), caption_style)], compact=True))
        return KeepTogether(content)


def _panel_plotly_professional(header: str, fig: Any, caption: str, header_style, caption_style) -> KeepTogether:
    """
    PROFESSIONAL: Embeds Plotly charts with excellent visual quality.

    Key improvements:
    - Extremely large export (3000x1500) for crystal-clear rendering
    - Professional color scheme maintained
    - Visible, styled axes with proper fonts
    - Clean white background
    - High DPI (scale=4)
    """
    content: List[Any] = [Paragraph(_escape(header), header_style)]
    content.append(Spacer(1, 6))

    if fig is None:
        content.append(_panel_box([Paragraph("No chart provided.", caption_style)]))
        return KeepTogether(content)

    try:
        # Create a copy to avoid modifying the original
        import plotly.graph_objects as go
        fig_copy = go.Figure(fig)

        # PROFESSIONAL CHART STYLING
        fig_copy.update_layout(
            # Clean backgrounds
            plot_bgcolor='white',
            paper_bgcolor='white',

            # Professional fonts
            font=dict(
                family="Helvetica, Arial, sans-serif",
                size=14,
                color='#1e293b'
            ),

            # X-axis styling
            xaxis=dict(
                showgrid=True,
                gridcolor='#e2e8f0',
                gridwidth=0.8,
                showline=True,
                linewidth=2,
                linecolor='#64748b',
                mirror=True,
                ticks='outside',
                tickwidth=1.5,
                ticklen=6,
                tickcolor='#64748b',
                tickfont=dict(size=13, color='#1e293b', family="Helvetica"),
                title_font=dict(size=14, color='#1e293b', family="Helvetica Bold"),
            ),

            # Y-axis styling
            yaxis=dict(
                showgrid=True,
                gridcolor='#e2e8f0',
                gridwidth=0.8,
                showline=True,
                linewidth=2,
                linecolor='#64748b',
                mirror=True,
                ticks='outside',
                tickwidth=1.5,
                ticklen=6,
                tickcolor='#64748b',
                tickfont=dict(size=13, color='#1e293b', family="Helvetica"),
                title_font=dict(size=14, color='#1e293b', family="Helvetica Bold"),
            ),

            # Legend styling
            showlegend=True,
            legend=dict(
                font=dict(size=12, color='#1e293b', family="Helvetica"),
                bgcolor='rgba(255,255,255,0.95)',
                bordercolor='#cbd5e1',
                borderwidth=1,
                x=1.02,
                y=1,
                xanchor='left',
                yanchor='top',
            ),

            # Generous margins to prevent cutoff
            margin=dict(l=100, r=60, t=50, b=100),

            # Professional title if present
            title=dict(
                font=dict(size=16, color='#1e293b', family="Helvetica Bold"),
                x=0.5,
                xanchor='center',
            ),
        )

        # ULTRA-HIGH QUALITY EXPORT
        png_bytes = fig_copy.to_image(
            format="png",
            width=3000,  # Very large for crisp detail
            height=1500,  # Proper aspect ratio
            scale=4,  # Maximum quality
        )

        img = Image(io.BytesIO(png_bytes))
        img.hAlign = "LEFT"

        # Calculate available width
        available_w = (A4[0] - (18 * mm) - (18 * mm))
        img.drawWidth = available_w
        img.drawHeight = available_w * (1500 / 3000)

        items: List[Any] = [img]

        if caption:
            items.append(Spacer(1, 8))
            items.append(Paragraph(_escape(caption), caption_style))

        content.append(_panel_box(items, bg=colors.white, border=THEME["border_strong"], border_w=1))
        return KeepTogether(content)

    except Exception as e:
        msg = f"Chart rendering failed.\n{type(e).__name__}: {e}"
        if caption:
            msg += f"\n{caption}"
        content.append(_panel_box([Paragraph(_escape_multiline(msg), caption_style)]))
        return KeepTogether(content)


def _panel_box(flowables: List[Any], *, bg=THEME["panel_bg"], border=THEME["border"], border_w=0.8,
               compact=False) -> Table:
    """Panel box with optional compact mode."""
    padding = 8 if compact else 14
    t = Table([[flowables]], colWidths="*")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("BOX", (0, 0), (-1, -1), border_w, border),
        ("LEFTPADDING", (0, 0), (-1, -1), padding),
        ("RIGHTPADDING", (0, 0), (-1, -1), padding),
        ("TOPPADDING", (0, 0), (-1, -1), padding),
        ("BOTTOMPADDING", (0, 0), (-1, -1), padding),
    ]))
    return t


# ============================================================
# Helpers
# ============================================================
def _to_dataframe(data: Any, columns: Optional[Sequence[str]] = None) -> pd.DataFrame:
    if data is None:
        return pd.DataFrame()
    if isinstance(data, pd.DataFrame):
        df = data.copy()
    elif isinstance(data, list) and data and isinstance(data[0], dict):
        df = pd.DataFrame(data)
    else:
        return pd.DataFrame()

    if columns:
        cols = [c for c in columns if c in df.columns]
        if cols:
            df = df[cols]
    return df


def _escape(s: str) -> str:
    if s is None:
        return ""
    s = str(s)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _escape_multiline(s: str) -> str:
    return "<br/>".join(_escape(line) for line in str(s or "").splitlines())


def _prettify_header(name: str) -> str:
    s = str(name or "")
    s = s.replace("_", " ").strip()
    return (s[:1].upper() + s[1:]) if s else ""


def _strip_emojis(text: str) -> str:
    bad = ["✅", "⚠️", "⛔", "📆", "🏢", "📁", "📈", "🧯", "🔔", "🔺", "🔥"]
    out = text or ""
    for b in bad:
        out = out.replace(b, "").strip()
    return out


def _estimate_col_widths(
        df: pd.DataFrame,
        *,
        page_width_mm: float,
        left_right_margin_mm: float,
        max_cols: int,
) -> List[float]:
    # For LANDSCAPE, use the wider dimension
    usable_mm = page_width_mm - left_right_margin_mm
    usable_pts = usable_mm * mm

    cols = list(df.columns)[:max_cols]
    weights: List[float] = []

    for c in cols:
        header_len = len(str(c))
        sample = df[c].astype(str).head(8).tolist()
        sample_len = max([len(x) for x in sample] + [header_len])
        weights.append(min(sample_len, 28))

    total = sum(weights) if weights else 1.0
    widths = [(w / total) * usable_pts for w in weights]

    min_w = 20 * mm
    widths = [max(w, min_w) for w in widths]

    s = sum(widths)
    if s > usable_pts:
        scale = usable_pts / s
        widths = [w * scale for w in widths]

    return widths