"""Printable shopping list (PDF) for one plan: a checklist per category plus the menu."""

from decimal import Decimal
from io import BytesIO

from django.template.defaultfilters import date as date_format
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .templatetags.planner_format import rupiah

INK = colors.HexColor("#172235")
MUTED = colors.HexColor("#5d6874")
GREEN = colors.HexColor("#0f3d2e")
LINE = colors.HexColor("#d5dee8")

TITLE = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=GREEN)
META = ParagraphStyle("meta", fontName="Helvetica", fontSize=9.5, leading=13, textColor=MUTED)
HEADING = ParagraphStyle(
    "heading", fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=INK
)
CELL = ParagraphStyle("cell", fontName="Helvetica", fontSize=9.5, leading=12, textColor=INK)
NOTE = ParagraphStyle("note", parent=CELL, fontSize=8, leading=10, textColor=MUTED)


def amount(item):
    """What to buy: whole fruit count, or grams still needed after pantry stock."""
    if item.get("purchase_units"):
        return f"{item['purchase_units']} {item['purchase_unit']}"
    grams = Decimal(str(item.get("to_buy") if item.get("in_pantry") else item["quantity"]))
    if grams >= 1000:
        return f"{grams / 1000:.2f}".rstrip("0").rstrip(".").replace(".", ",") + " kg"
    return f"{grams.normalize():f} g"


def shopping_list_pdf(plan, result, groups, schedule):
    """Return PDF bytes; `groups` are pantry-annotated shopping groups."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Daftar belanja - {plan.title}",
        author="TAKARKUY",
    )
    inputs = plan.inputs
    story = [
        Paragraph(f"Daftar Belanja — {plan.title}", TITLE),
        Spacer(0, 3 * mm),
        Paragraph(
            f"Mulai {date_format(plan.starts_on, 'd M Y')} · {inputs['days']} hari · {inputs['servings']} orang"
            f" · Budget {rupiah(inputs['budget'])}",
            META,
        ),
        Spacer(0, 6 * mm),
    ]
    width = doc.width
    for group in groups:
        rows = []
        for item in group["items"]:
            name = Paragraph(item["name"], CELL)
            if item.get("in_pantry"):
                name = [name, Paragraph(f"Sudah ada di Pantry {item['in_pantry']} g", NOTE)]
            rows.append(["", name, amount(item), rupiah(item["cost"])])
        rows.append(
            ["", Paragraph(f"<b>Subtotal {group['name']}</b>", CELL), "", rupiah(group["subtotal"])]
        )
        table = Table(rows, colWidths=[7 * mm, width - 62 * mm, 25 * mm, 30 * mm])
        style = [
            ("FONT", (2, 0), (-1, -1), "Helvetica", 9.5),
            ("FONT", (3, -1), (3, -1), "Helvetica-Bold", 9.5),
            ("TEXTCOLOR", (0, 0), (-1, -1), INK),
            ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        for row in range(len(rows) - 1):
            style.append(("BOX", (0, row), (0, row), 0.8, MUTED))
        table.setStyle(TableStyle(style))
        story += [
            Paragraph(f"{group['name']} ({len(group['items'])} bahan)", HEADING),
            Spacer(0, 2 * mm),
        ]
        story += [table, Spacer(0, 5 * mm)]

    total = Table(
        [["Total belanja", rupiah(result.get("net_total", result["total"]))]],
        colWidths=[width - 40 * mm, 40 * mm],
    )
    total.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), "Helvetica-Bold", 12),
                ("TEXTCOLOR", (0, 0), (-1, -1), GREEN),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("LINEABOVE", (0, 0), (-1, 0), 1, INK),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story += [total, Paragraph("Total belanja sudah melewati pembulatan.", NOTE), Spacer(0, 8 * mm)]

    story += [Paragraph("Jadwal menu", HEADING), Spacer(0, 2 * mm)]
    menu = [
        [f"Hari {day['number']}", Paragraph(f"{meal['label']}: {meal_name(meal)}", CELL)]
        for day in schedule
        for meal in day["meals"]
    ]
    menu_table = Table(menu, colWidths=[18 * mm, width - 18 * mm])
    menu_table.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9.5),
                ("TEXTCOLOR", (0, 0), (-1, -1), INK),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
            ]
        )
    )
    story.append(menu_table)
    doc.build(story)
    return buffer.getvalue()


def meal_name(meal):
    staple = "Nasi" if meal.get("with_rice") else (meal.get("staple") or {}).get("label")
    return meal["name"] + (f" + {staple}" if staple else "")
