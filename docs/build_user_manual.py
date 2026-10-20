"""Render the user manual to PDF.

    python docs/build_user_manual.py

Kept in the repo rather than written ad hoc, so the manual can be
regenerated after a feature change instead of rebuilt from scratch.
Content lives in docs/user_manual_content.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, NextPageTemplate, PageBreak,
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)

from user_manual_content import CONTENT, SUBTITLE, TITLE, VERSION

OUT = Path(__file__).resolve().parent.parent / "Bid-Analyser-User-Manual.pdf"

INK = colors.HexColor("#17222e")
MUTED = colors.HexColor("#5a6775")
ACCENT = colors.HexColor("#12556b")
RULE = colors.HexColor("#d6dde4")
NOTE_BG = colors.HexColor("#f3f7f9")
HEAD_BG = colors.HexColor("#12556b")
ZEBRA = colors.HexColor("#f6f8fa")

ss = getSampleStyleSheet()
S = {
    "h1": ParagraphStyle("h1", parent=ss["Heading1"], fontName="Helvetica-Bold",
                         fontSize=17, leading=21, textColor=ACCENT, spaceBefore=0, spaceAfter=10),
    "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold",
                         fontSize=12, leading=15, textColor=INK, spaceBefore=13, spaceAfter=5),
    "h3": ParagraphStyle("h3", parent=ss["Heading3"], fontName="Helvetica-Bold",
                         fontSize=10, leading=13, textColor=MUTED, spaceBefore=10, spaceAfter=3),
    "p": ParagraphStyle("p", parent=ss["BodyText"], fontName="Helvetica", fontSize=9.6,
                        leading=14.4, textColor=INK, alignment=TA_LEFT, spaceAfter=7),
    "b": ParagraphStyle("b", parent=ss["BodyText"], fontName="Helvetica", fontSize=9.6,
                        leading=14.4, textColor=INK, leftIndent=13, bulletIndent=3, spaceAfter=4),
    "n": ParagraphStyle("n", parent=ss["BodyText"], fontName="Helvetica", fontSize=9.6,
                        leading=14.4, textColor=INK, leftIndent=16, bulletIndent=3, spaceAfter=4),
    "note": ParagraphStyle("note", parent=ss["BodyText"], fontName="Helvetica", fontSize=9.1,
                           leading=13.4, textColor=INK, leftIndent=8, rightIndent=8,
                           spaceBefore=3, spaceAfter=3),
    "cell": ParagraphStyle("cell", parent=ss["BodyText"], fontName="Helvetica", fontSize=8.7,
                           leading=12, textColor=INK, spaceAfter=0),
    "cellh": ParagraphStyle("cellh", parent=ss["BodyText"], fontName="Helvetica-Bold",
                            fontSize=8.7, leading=12, textColor=colors.white, spaceAfter=0),
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=31, leading=37,
                            textColor=ACCENT, spaceAfter=6),
    "sub": ParagraphStyle("sub", fontName="Helvetica", fontSize=16, leading=21,
                          textColor=INK, spaceAfter=22),
    "ver": ParagraphStyle("ver", fontName="Helvetica", fontSize=10, leading=14,
                          textColor=MUTED, spaceAfter=0),
    "toc": ParagraphStyle("toc", fontName="Helvetica", fontSize=10, leading=17,
                          textColor=INK, spaceAfter=0),
}

PAGE_W, PAGE_H = A4
M = 20 * mm
CONTENT_W = PAGE_W - 2 * M


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def note_block(text: str) -> Table:
    label, _, rest = text.partition(":")
    if rest and label.strip().startswith("Important"):
        body = f"<b>{esc(label.strip())}:</b>{esc(rest)}"
    else:
        body = esc(text)
    table = Table([[Paragraph(body, S["note"])]], colWidths=[CONTENT_W])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NOTE_BG),
        ("LINEBEFORE", (0, 0), (0, -1), 2.2, ACCENT),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table


def data_table(headers: list[str], rows: list[list[str]]) -> Table:
    if len(headers) == 2:
        widths = [CONTENT_W * 0.30, CONTENT_W * 0.70]
    elif headers[0] == "Priority":
        widths = [CONTENT_W * 0.11, CONTENT_W * 0.35, CONTENT_W * 0.54]
    elif headers[0] == "View":
        widths = [CONTENT_W * 0.16, CONTENT_W * 0.34, CONTENT_W * 0.50]
    elif headers[0] == "Route":
        widths = [CONTENT_W * 0.17, CONTENT_W * 0.60, CONTENT_W * 0.23]
    else:
        widths = [CONTENT_W * 0.22, CONTENT_W * 0.40, CONTENT_W * 0.38]

    data = [[Paragraph(esc(h), S["cellh"]) for h in headers]]
    data += [[Paragraph(esc(c), S["cell"]) for c in row] for row in rows]

    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
        ("BOX", (0, 0), (-1, -1), 0.4, RULE),
    ]
    style += [("BACKGROUND", (0, i), (-1, i), ZEBRA)
              for i in range(1, len(data)) if i % 2 == 0]
    table.setStyle(TableStyle(style))
    return table


def cover_page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(ACCENT)
    canvas.rect(0, PAGE_H - 13 * mm, PAGE_W, 13 * mm, stroke=0, fill=1)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(PAGE_W / 2, 14 * mm,
                             "Internal document. Reads from Maximo; never writes to it.")
    canvas.restoreState()


def body_page(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(M, PAGE_H - M + 6 * mm, PAGE_W - M, PAGE_H - M + 6 * mm)
    canvas.setFont("Helvetica", 7.6)
    canvas.setFillColor(MUTED)
    canvas.drawString(M, PAGE_H - M + 8 * mm, f"{TITLE}  |  {SUBTITLE}")
    canvas.line(M, 15 * mm, PAGE_W - M, 15 * mm)
    canvas.drawRightString(PAGE_W - M, 10 * mm, str(canvas.getPageNumber()))
    canvas.drawString(M, 10 * mm, VERSION)
    canvas.restoreState()


def build() -> Path:
    doc = BaseDocTemplate(
        str(OUT), pagesize=A4, leftMargin=M, rightMargin=M, topMargin=M, bottomMargin=22 * mm,
        title=f"{TITLE} {SUBTITLE}", author="Delivery team",
        subject="User manual for the TAQA Bid Analyser",
    )
    frame = Frame(M, 22 * mm, CONTENT_W, PAGE_H - M - 22 * mm, id="body")
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[frame], onPage=cover_page),
        PageTemplate(id="body", frames=[frame], onPage=body_page),
    ])

    story = [
        Spacer(1, 52 * mm),
        Paragraph(TITLE, S["title"]),
        Paragraph(SUBTITLE, S["sub"]),
        Paragraph(VERSION, S["ver"]),
        Spacer(1, 12 * mm),
        Paragraph("A complete guide to comparing vendor bids, reading the automated checks, "
                  "and recording your own findings.", S["p"]),
        NextPageTemplate("body"),
        PageBreak(),
        Paragraph("Contents", S["h1"]),
    ]
    story += [Paragraph(esc(text), S["toc"]) for kind, text in CONTENT if kind == "h1"]
    story.append(PageBreak())

    step = 0
    for kind, text in CONTENT:
        if kind == "pb":
            story.append(PageBreak())
            step = 0
        elif kind in ("h1", "h2", "h3"):
            story.append(Paragraph(esc(text), S[kind]))
            step = 0
        elif kind == "p":
            story.append(Paragraph(esc(text), S["p"]))
        elif kind == "b":
            story.append(Paragraph(esc(text), S["b"], bulletText="•"))
        elif kind == "n":
            step += 1
            story.append(Paragraph(esc(text), S["n"], bulletText=f"{step}."))
        elif kind == "note":
            story += [Spacer(1, 3), note_block(text), Spacer(1, 7)]
        elif kind == "table":
            headers, rows = text
            story += [Spacer(1, 3), data_table(headers, rows), Spacer(1, 9)]

    doc.build(story)
    return OUT


if __name__ == "__main__":
    path = build()
    print(f"wrote {path}")
