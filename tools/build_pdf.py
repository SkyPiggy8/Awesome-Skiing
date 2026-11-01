#!/usr/bin/env python3
"""Build the downloadable Awesome-Skiing handbook from the Markdown sources."""

from __future__ import annotations

import argparse
import html
import re
from datetime import date
from pathlib import Path
from urllib.parse import quote

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "output/pdf/Awesome-Skiing-Handbook-CN.pdf"
REPO_BLOB = "https://github.com/SkyPiggy8/Awesome-Skiing/blob/main/"
REPO_URL = "https://github.com/SkyPiggy8/Awesome-Skiing"

SOURCE_FILES = [
    "docs/00-knowledge-map.md",
    "docs/10-ski-or-snowboard.md",
    "docs/01-first-day.md",
    "docs/03-equipment.md",
    "docs/07-lessons-and-travel.md",
    "docs/11-first-day-without-lessons.md",
    "docs/02-basics-and-safety.md",
    "docs/04-ski-learning.md",
    "docs/05-snowboard-learning.md",
    "docs/06-budget.md",
    "docs/12-tickets-and-stay.md",
    "docs/13-filming-and-progress.md",
    "docs/08-care-and-faq.md",
    "docs/09-glossary.md",
    "resorts/README.md",
    "resorts/transport.md",
    "resorts/guangzhou-indoor.md",
    "resorts/indoor-east-china.md",
    "resorts/nanshan.md",
    "resorts/wanlong.md",
    "resorts/thaiwoo.md",
    "resorts/fulong.md",
    "resorts/yunding.md",
    "resorts/songhua.md",
    "resorts/beidahu.md",
    "resorts/yabuli.md",
    "resorts/changbaishan-wanda.md",
    "resorts/changbaishan-huamei.md",
    "resorts/jiangjunshan.md",
    "resorts/keketuohai.md",
    "resorts/jikepulin.md",
    "resorts/xiling.md",
    "resources/videos.md",
    "resources/community-notes.md",
    "resources/sources.md",
    "templates/trip-checklist.md",
    "templates/budget-template.md",
    "templates/practice-log.md",
]


def register_fonts() -> tuple[str, str]:
    candidates = [
        Path("/System/Library/Fonts/STHeiti Light.ttc"),
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    ]
    regular = next((path for path in candidates if path.exists()), None)
    if not regular:
        raise SystemExit("未找到可用的中文字体，请安装 Noto Sans CJK 后重试。")

    bold_candidates = [
        Path("/System/Library/Fonts/STHeiti Medium.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
        regular,
    ]
    bold = next(path for path in bold_candidates if path and path.exists())
    pdfmetrics.registerFont(TTFont("GuideSans", str(regular), subfontIndex=0))
    pdfmetrics.registerFont(TTFont("GuideSansBold", str(bold), subfontIndex=0))
    pdfmetrics.registerFontFamily(
        "GuideSans", normal="GuideSans", bold="GuideSansBold",
        italic="GuideSans", boldItalic="GuideSansBold"
    )
    return "GuideSans", "GuideSansBold"


def resolve_url(url: str, source: Path) -> str:
    url = url.strip()
    if re.match(r"^(?:https?://|mailto:|#)", url):
        return url
    absolute = (source.parent / url).resolve()
    try:
        relative = absolute.relative_to(ROOT).as_posix()
    except ValueError:
        return url
    return REPO_BLOB + quote(relative, safe="/.-_~")


def inline_markup(text: str, source: Path) -> str:
    placeholders: dict[str, str] = {}

    def keep(value: str) -> str:
        key = f"@@TOKEN{len(placeholders)}@@"
        placeholders[key] = value
        return key

    def image_repl(match: re.Match[str]) -> str:
        label, url = match.group(1), resolve_url(match.group(2), source)
        return keep(f'<link href="{html.escape(url, quote=True)}">[图片：{html.escape(label)}]</link>')

    def link_repl(match: re.Match[str]) -> str:
        label, url = match.group(1), resolve_url(match.group(2), source)
        return keep(f'<link href="{html.escape(url, quote=True)}" color="#176B87">{html.escape(label)}</link>')

    text = re.sub(r"!\[([^]]*)\]\(([^)]+)\)", image_repl, text)
    text = re.sub(r"\[([^]]+)\]\(([^)]+)\)", link_repl, text)
    text = re.sub(
        r"`([^`]+)`",
        lambda m: keep(f'<font name="GuideSans" color="#44515C">{html.escape(m.group(1))}</font>'),
        text,
    )
    text = html.escape(text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__([^_]+)__", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"~~([^~]+)~~", r"\1", text)
    for key, value in placeholders.items():
        text = text.replace(key, value)
    return text


def strip_markup(text: str) -> str:
    text = re.sub(r"!\[([^]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", text)
    return re.sub(r"[*_`~]", "", text).strip()


def parse_table(lines: list[str], source: Path, styles: dict, width: float) -> Table:
    rows: list[list[Paragraph]] = []
    for row_index, line in enumerate(lines):
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if row_index == 1 and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        style = styles["table_head"] if row_index == 0 else styles["table_cell"]
        rows.append([Paragraph(inline_markup(cell, source), style) for cell in cells])
    col_count = max(len(row) for row in rows)
    for row in rows:
        row.extend(Paragraph("", styles["table_cell"]) for _ in range(col_count - len(row)))
    table = Table(rows, colWidths=[width / col_count] * col_count, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E9F4F7")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#123B4A")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B9CAD0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFB")]),
    ]))
    return table


class HandbookDocTemplate(BaseDocTemplate):
    def afterFlowable(self, flowable):
        if not isinstance(flowable, Paragraph) or not hasattr(flowable, "toc_level"):
            return
        level = flowable.toc_level
        text = flowable.bookmark_text
        key = flowable.bookmark_key
        self.canv.bookmarkPage(key)
        self.canv.addOutlineEntry(text, key, level=level, closed=level > 0)
        self.notify("TOCEntry", (level, text, self.page, key))


def make_styles(font: str, bold: str) -> dict:
    base = getSampleStyleSheet()
    return {
        "body": ParagraphStyle(
            "BodyCN", parent=base["BodyText"], fontName=font, fontSize=9.5,
            leading=15.2, textColor=colors.HexColor("#24343C"),
            spaceAfter=5.5, allowWidows=0, allowOrphans=0,
        ),
        "quote": ParagraphStyle(
            "QuoteCN", parent=base["BodyText"], fontName=font, fontSize=9,
            leading=14.5, textColor=colors.HexColor("#3B5966"),
            backColor=colors.HexColor("#EFF7F9"), borderColor=colors.HexColor("#80B8C7"),
            borderWidth=0, borderPadding=(6, 8, 6, 10), leftIndent=8, spaceAfter=7,
        ),
        "bullet": ParagraphStyle(
            "BulletCN", parent=base["BodyText"], fontName=font, fontSize=9.3,
            leading=14.8, leftIndent=14, firstLineIndent=-9, spaceAfter=3.5,
            textColor=colors.HexColor("#24343C"),
        ),
        "h1": ParagraphStyle(
            "H1CN", parent=base["Heading1"], fontName=bold, fontSize=20,
            leading=27, textColor=colors.HexColor("#0B536A"), spaceBefore=3,
            spaceAfter=12, keepWithNext=True,
        ),
        "h2": ParagraphStyle(
            "H2CN", parent=base["Heading2"], fontName=bold, fontSize=14,
            leading=20, textColor=colors.HexColor("#14738C"), spaceBefore=13,
            spaceAfter=7, keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "H3CN", parent=base["Heading3"], fontName=bold, fontSize=11.5,
            leading=17, textColor=colors.HexColor("#315C6A"), spaceBefore=9,
            spaceAfter=5, keepWithNext=True,
        ),
        "table_head": ParagraphStyle(
            "TableHeadCN", fontName=bold, fontSize=7.7, leading=10.5,
            textColor=colors.HexColor("#123B4A"),
        ),
        "table_cell": ParagraphStyle(
            "TableCellCN", fontName=font, fontSize=7.4, leading=10.5,
            textColor=colors.HexColor("#263840"),
        ),
        "code": ParagraphStyle(
            "CodeCN", fontName=font, fontSize=8, leading=12,
            textColor=colors.HexColor("#344A54"), backColor=colors.HexColor("#F1F4F5"),
            borderPadding=6, leftIndent=5, rightIndent=5, spaceAfter=6,
        ),
        "small": ParagraphStyle(
            "SmallCN", fontName=font, fontSize=8, leading=12,
            textColor=colors.HexColor("#61717A"),
        ),
        "cover_title": ParagraphStyle(
            "CoverTitle", fontName=bold, fontSize=31, leading=39,
            textColor=colors.HexColor("#064B61"), alignment=TA_LEFT,
        ),
        "cover_subtitle": ParagraphStyle(
            "CoverSubtitle", fontName=font, fontSize=15, leading=23,
            textColor=colors.HexColor("#3E6572"), alignment=TA_LEFT,
        ),
        "toc_title": ParagraphStyle(
            "TOCTitle", fontName=bold, fontSize=22, leading=28,
            textColor=colors.HexColor("#0B536A"), spaceAfter=12,
        ),
    }


def heading(text: str, level: int, styles: dict, counter: list[int]) -> Paragraph:
    clean = strip_markup(text)
    key = f"section-{counter[0]}"
    counter[0] += 1
    p = Paragraph(inline_markup(text, ROOT / "README.md"), styles[f"h{min(level, 3)}"])
    p.toc_level = min(level - 1, 2)
    p.bookmark_text = clean
    p.bookmark_key = key
    return p


def markdown_flowables(source: Path, styles: dict, content_width: float, counter: list[int]):
    raw_lines = source.read_text(encoding="utf-8").splitlines()
    story = []
    index = 0
    in_code = False
    code_lines: list[str] = []

    while index < len(raw_lines):
        line = raw_lines[index].rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code:
                story.append(Paragraph("<br/>".join(html.escape(x) for x in code_lines), styles["code"]))
                code_lines = []
                in_code = False
            else:
                in_code = True
            index += 1
            continue
        if in_code:
            code_lines.append(line)
            index += 1
            continue
        if not stripped:
            index += 1
            continue

        match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if match:
            level = len(match.group(1))
            story.append(heading(match.group(2), level, styles, counter))
            index += 1
            continue

        if stripped.startswith("|") and index + 1 < len(raw_lines) and re.match(r"^\s*\|?\s*:?-{3,}", raw_lines[index + 1]):
            table_lines = [line]
            index += 1
            while index < len(raw_lines) and raw_lines[index].strip().startswith("|"):
                table_lines.append(raw_lines[index].rstrip())
                index += 1
            story.extend([parse_table(table_lines, source, styles, content_width), Spacer(1, 7)])
            continue

        if re.fullmatch(r"[-*_]{3,}", stripped):
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#B8C9CE"), spaceBefore=4, spaceAfter=8))
            index += 1
            continue

        if stripped.startswith(">"):
            quote_lines = []
            while index < len(raw_lines) and raw_lines[index].strip().startswith(">"):
                quote_lines.append(raw_lines[index].strip().lstrip(">").strip())
                index += 1
            story.append(Paragraph(inline_markup(" ".join(quote_lines), source), styles["quote"]))
            continue

        bullet = re.match(r"^\s*[-*+]\s+(.+)$", line)
        numbered = re.match(r"^\s*(\d+)[.)]\s+(.+)$", line)
        if bullet or numbered:
            text = (bullet or numbered).group(1 if bullet else 2)
            text = re.sub(r"^\[([ xX])\]\s*", lambda m: "☑ " if m.group(1).lower() == "x" else "☐ ", text)
            marker = "•" if bullet else f"{numbered.group(1)}."
            story.append(Paragraph(f"{marker} {inline_markup(text, source)}", styles["bullet"]))
            index += 1
            continue

        paragraph = [stripped]
        index += 1
        while index < len(raw_lines):
            nxt = raw_lines[index].strip()
            if not nxt or re.match(r"^(#{1,6})\s+", nxt) or nxt.startswith(("|", ">", "```")):
                break
            if re.match(r"^\s*[-*+]\s+", raw_lines[index]) or re.match(r"^\s*\d+[.)]\s+", raw_lines[index]):
                break
            paragraph.append(nxt)
            index += 1
        story.append(Paragraph(inline_markup(" ".join(paragraph), source), styles["body"]))

    if code_lines:
        story.append(Paragraph("<br/>".join(html.escape(x) for x in code_lines), styles["code"]))
    return story


def draw_page(canvas, doc, font: str):
    canvas.saveState()
    page = canvas.getPageNumber()
    if page > 1:
        canvas.setFont(font, 7.5)
        canvas.setFillColor(colors.HexColor("#68818B"))
        canvas.drawString(20 * mm, 12 * mm, "Awesome-Skiing · 开源滑雪指南")
        canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, str(page))
        canvas.setStrokeColor(colors.HexColor("#D5E0E3"))
        canvas.setLineWidth(0.35)
        canvas.line(20 * mm, 17 * mm, A4[0] - 20 * mm, 17 * mm)
        # Use a fixed pale color instead of PDF transparency: some renderers
        # ignore alpha values and would otherwise make the watermark too dark.
        canvas.setFillColor(colors.HexColor("#E5EFF2"))
        canvas.setFont("Helvetica-Bold", 42)
        canvas.saveState()
        canvas.translate(105 * mm, 148 * mm)
        canvas.rotate(32)
        canvas.drawCentredString(0, 0, "Awesome-Skiing")
        canvas.restoreState()
    canvas.restoreState()


def build(output: Path):
    font, bold = register_fonts()
    styles = make_styles(font, bold)
    output.parent.mkdir(parents=True, exist_ok=True)

    doc = HandbookDocTemplate(
        str(output), pagesize=A4, title="Awesome-Skiing 中文滑雪入门指南",
        author="Awesome-Skiing contributors", subject="中文滑雪开源指南",
        leftMargin=20 * mm, rightMargin=20 * mm, topMargin=19 * mm, bottomMargin=22 * mm,
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates(PageTemplate(id="handbook", frames=frame, onPage=lambda c, d: draw_page(c, d, font)))

    story = [Spacer(1, 25 * mm)]
    story.append(Paragraph("Awesome-Skiing", styles["cover_title"]))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("中文滑雪入门与雪场指南", styles["cover_title"]))
    story.append(Spacer(1, 9 * mm))
    story.append(Paragraph("从第一次想去滑雪，到能自己安排一趟雪旅。", styles["cover_subtitle"]))
    story.append(Spacer(1, 42 * mm))
    story.append(HRFlowable(width="36%", thickness=3, color=colors.HexColor("#31A6C2"), hAlign="LEFT"))
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(
        f"版本日期：{date.today().isoformat()}<br/>覆盖单板、双板、装备、教学、安全、预算、交通与 17 个代表性雪场。",
        styles["body"],
    ))
    story.append(Spacer(1, 12 * mm))
    story.append(Paragraph(
        f'<link href="{REPO_URL}" color="#176B87">{REPO_URL}</link><br/>'
        "本 PDF 由仓库 Markdown 内容生成。价格、开放雪道和交通班次可能变化，出行前请以官方信息为准。",
        styles["small"],
    ))
    story.append(PageBreak())

    story.append(Paragraph("目录", styles["toc_title"]))
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle("TOC1", fontName=bold, fontSize=9.5, leading=14, leftIndent=0, firstLineIndent=0, textColor=colors.HexColor("#164F61"), spaceBefore=4),
        ParagraphStyle("TOC2", fontName=font, fontSize=8.2, leading=12, leftIndent=12, firstLineIndent=0, textColor=colors.HexColor("#425E68")),
        ParagraphStyle("TOC3", fontName=font, fontSize=7.8, leading=11, leftIndent=24, firstLineIndent=0, textColor=colors.HexColor("#62747B")),
    ]
    story.append(toc)
    story.append(PageBreak())

    counter = [0]
    for file_index, relative in enumerate(SOURCE_FILES):
        source = ROOT / relative
        if not source.exists():
            raise SystemExit(f"缺少源文件：{relative}")
        if file_index:
            story.append(PageBreak())
        story.extend(markdown_flowables(source, styles, doc.width, counter))

    story.append(PageBreak())
    story.append(Paragraph("继续更新这份指南", styles["h1"]))
    story.append(Paragraph(
        f'最新版、勘误与贡献入口：<link href="{REPO_URL}" color="#176B87">{REPO_URL}</link><br/>'
        "欢迎通过 Issue 提供来源、纠错，也欢迎通过 Pull Request 补充雪场与教程。",
        styles["body"],
    ))
    doc.multiBuild(story)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    build(args.output.resolve())
    print(args.output.resolve())


if __name__ == "__main__":
    main()
