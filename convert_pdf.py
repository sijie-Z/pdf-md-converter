#!/usr/bin/env python3
"""
convert_pdf.py — PDF to Markdown + structured blocks converter.

Extracts text, tables, and metadata from a PDF; outputs:
  - outputs/document.md      — Markdown with page markers, tables, image-page flags
  - outputs/blocks.json      — Structured blocks for RAG / retrieval / human review
  - outputs/qa_report.md     — Parsing quality report with issues and review guidance

Usage:
    python convert_pdf.py <input_pdf>
    python convert_pdf.py sample_pdf_to_markdown_note.pdf
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import fitz  # PyMuPDF
import pdfplumber

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("convert_pdf")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
IMAGE_PAGE_TEXT_THRESHOLD = 30       # chars or fewer → image/scan page
HEADING_FONT_SIZE_MIN = 11.0         # fonts >= this → potential heading
PAGE_NUMBER_Y_THRESHOLD_RATIO = 0.9  # bottom 10% of page → page number


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------
@dataclass
class BBox:
    x0: float
    y0: float
    x1: float
    y1: float

    def to_dict(self) -> dict[str, float]:
        return {"x0": self.x0, "y0": self.y0, "x1": self.x1, "y1": self.y1}


@dataclass
class ImagePageBlock:
    page: int
    block_id: str
    type: str = "image_page"
    needs_ocr: bool = True
    source: dict[str, Any] = field(default_factory=dict)
    text_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def get_text_blocks_with_font_info(
    page: fitz.Page,
) -> list[dict[str, Any]]:
    """Extract text blocks from a page with font size and position info.

    Returns list of dicts with keys: text, bbox, max_font_size.
    Uses PyMuPDF's dict mode to get font information.
    """
    raw = page.get_text("dict")
    blocks_raw = raw["blocks"]
    page_height = page.rect.height

    results: list[dict[str, Any]] = []
    for block in blocks_raw:
        if block.get("type") != 0:  # skip non-text blocks
            continue

        # Reconstruct text and find max font size
        full_text = ""
        max_font_size = 0.0
        for line in block.get("lines", []):
            line_text = ""
            for span in line.get("spans", []):
                span_text = span.get("text", "")
                span_size = span.get("size", 0)
                line_text += span_text
                if span_size > max_font_size:
                    max_font_size = span_size
            if line_text:
                full_text += line_text + "\n"

        full_text = full_text.strip()

        if not full_text:
            continue

        bbox_raw = block.get("bbox", (0, 0, 0, 0))
        results.append(
            {
                "text": full_text,
                "bbox": {
                    "x0": bbox_raw[0],
                    "y0": bbox_raw[1],
                    "x1": bbox_raw[2],
                    "y1": bbox_raw[3],
                },
                "max_font_size": max_font_size,
                "page_height": page_height,
            }
        )

    return results


def classify_block_type(
    info: dict[str, Any],
    table_y_range: tuple[float, float] | None,
) -> str:
    """Classify a text block into one of: heading, table_caption, paragraph,
    footnote, page_header, page_number, table_content."""
    text = info["text"]
    font_size = info["max_font_size"]
    bbox = info["bbox"]
    page_height = info["page_height"]

    # Page number (near bottom of page, short text)
    if bbox["y0"] > page_height * PAGE_NUMBER_Y_THRESHOLD_RATIO:
        return "page_number"

    # Page header (company name, report title)
    if re.match(r"^XX公司", text) or re.match(r"^XX集团", text):
        return "page_header"
    if "半年度报告" in text and font_size < 11:
        return "page_header"

    # Table content (inside table bounding box)
    if table_y_range and bbox["y0"] >= table_y_range[0] and bbox["y1"] <= table_y_range[1]:
        return "table_content"

    # Table caption (matches 表 N-N pattern) — check before generic heading
    if re.match(r"^表\d+", text):
        return "table_caption"

    # Footnote (starts with 注： or 脚注：)
    if text.startswith("注：") or text.startswith("注:") or text.startswith("脚注："):
        return "footnote"

    # Heading (large font, or matches 附注 pattern)
    if font_size >= HEADING_FONT_SIZE_MIN:
        return "heading"
    if re.match(r"^附注\d+", text):
        return "heading"

    # Paragraph (default)
    return "paragraph"


def is_image_page(page: fitz.Page) -> bool:
    """Check if a page is likely an image/scan page with no useful text."""
    text = page.get_text().strip()
    images = page.get_images()
    if len(text) < IMAGE_PAGE_TEXT_THRESHOLD and len(images) > 0:
        return True
    return False


def check_sum_consistency(
    header: list[str], rows: list[list[str]]
) -> list[dict[str, Any]]:
    """Check if 合计 (total) rows match sum of detail rows for numeric columns."""
    issues: list[dict[str, Any]] = []
    total_row_idx = None
    detail_rows: list[int] = []

    for i, row in enumerate(rows):
        if row and row[0] and "合计" in row[0]:
            total_row_idx = i
        elif row and row[0] and row[0].strip():
            detail_rows.append(i)

    if total_row_idx is None or not detail_rows:
        return issues

    total_row = rows[total_row_idx]
    for col in range(1, len(total_row)):
        total_val = _parse_number(total_row[col])
        if total_val is None:
            continue
        detail_sum = 0.0
        all_valid = True
        for ri in detail_rows:
            if col < len(rows[ri]):
                v = _parse_number(rows[ri][col])
                if v is not None:
                    detail_sum += v
                else:
                    all_valid = False
        if all_valid:
            diff = abs(total_val - detail_sum)
            if diff > 0.01:
                issues.append(
                    {
                        "type": "sum_mismatch",
                        "detail": (
                            f"Column '{header[col] if col < len(header) else col}': "
                            f"合计={total_val}, sum_of_details={detail_sum:.2f}, "
                            f"diff={diff:.2f}"
                        ),
                        "severity": "error",
                    }
                )
    return issues


def _parse_number(s: str) -> Optional[float]:
    """Parse a number string that may contain commas."""
    if not s:
        return None
    s = s.strip().replace(",", "").replace(" ", "")
    try:
        return float(s)
    except ValueError:
        return None


def clean_table_cell(cell: Optional[str]) -> str:
    """Clean up a table cell value."""
    if cell is None:
        return ""
    return cell.strip()


def get_table_y_range(
    pdf_path: str, page_num: int
) -> Optional[tuple[float, float]]:
    """Get the y-range (top, bottom) of the table on a page, if any."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[page_num]
            tables = page.find_tables()
            if tables:
                bbox = tables[0].bbox
                return (bbox[1], bbox[3])  # (y0, y1)
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Main converter
# ---------------------------------------------------------------------------
class PDFToMarkdownConverter:
    """Main converter: reads PDF → generates markdown, blocks, QA report."""

    def __init__(self, pdf_path: str, output_dir: str = "outputs"):
        self.pdf_path = Path(pdf_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.blocks: list[dict[str, Any]] = []
        self.qa_issues: list[dict[str, Any]] = []
        self.page_count = 0
        self.image_pages: list[int] = []

        # Runtime state
        self._table_counter = 0

    def run(self) -> None:
        """Execute the full conversion pipeline."""
        start = datetime.now()
        logger.info("Starting conversion: %s", self.pdf_path)

        if not self.pdf_path.exists():
            logger.error("Input PDF not found: %s", self.pdf_path)
            sys.exit(1)

        with fitz.open(str(self.pdf_path)) as doc:
            self.page_count = len(doc)
            logger.info("PDF loaded: %d pages", self.page_count)

            # Phase 1: Gather per-page data
            pages_data = []
            for page_num in range(self.page_count):
                page = doc[page_num]
                logger.info("Processing page %d/%d", page_num + 1, self.page_count)

                if is_image_page(page):
                    self._handle_image_page(page, page_num)
                    pages_data.append(
                        {"type": "image", "text_blocks": [], "table": None}
                    )
                else:
                    table_y = get_table_y_range(str(self.pdf_path), page_num)
                    text_blocks = self._extract_text_blocks(page, page_num, table_y)
                    table = self._extract_table(page_num)
                    pages_data.append(
                        {
                            "type": "text",
                            "text_blocks": text_blocks,
                            "table": table,
                        }
                    )

            # Phase 2: Write outputs
            self._write_markdown(pages_data)
            self._write_blocks_json()
            self._write_qa_report(start)

        logger.info("Conversion complete. Outputs → %s", self.output_dir)

    # -- Image page handling ------------------------------------------------

    def _handle_image_page(self, page: fitz.Page, page_num: int) -> None:
        """Register an image-only page."""
        self.image_pages.append(page_num + 1)
        text = page.get_text().strip()
        block = ImagePageBlock(
            page=page_num + 1,
            block_id=f"img_{page_num + 1}",
            text_hint=text,
            source={
                "page": page_num + 1,
                "method": "image_detection",
                "text_length": len(text),
            },
        )
        self.blocks.append(block.to_dict())
        self.qa_issues.append(
            {
                "page": page_num + 1,
                "type": "image_page_no_ocr",
                "detail": "Page detected as image-only; no OCR applied.",
                "severity": "warning",
            }
        )
        logger.info("  → Image page, needs OCR")

    # -- Text extraction ----------------------------------------------------

    def _extract_text_blocks(
        self,
        page: fitz.Page,
        page_num: int,
        table_y_range: tuple[float, float] | None,
    ) -> list[dict[str, Any]]:
        """Extract text blocks, classify them, skip table content."""
        infos = get_text_blocks_with_font_info(page)
        extracted: list[dict[str, Any]] = []
        block_idx = 0

        for info in infos:
            btype = classify_block_type(info, table_y_range)

            # Skip noise
            if btype in ("page_header", "page_number", "table_content"):
                continue

            block_idx += 1
            block_id = f"p{page_num + 1}_b{block_idx}"
            text = info["text"]

            entry = {
                "page": page_num + 1,
                "block_id": block_id,
                "type": btype,
                "text": text,
                "source": {
                    "page": page_num + 1,
                    "bbox": info["bbox"],
                    "method": "pymupdf_text_extraction",
                    "max_font_size": info["max_font_size"],
                },
            }
            extracted.append(entry)
            self.blocks.append(entry)
            logger.debug("  %s (%s): %s", block_id, btype, text[:60])

        return extracted

    # -- Table extraction ---------------------------------------------------

    def _extract_table(self, page_num: int) -> Optional[dict[str, Any]]:
        """Extract tables from a page using pdfplumber."""
        try:
            with pdfplumber.open(str(self.pdf_path)) as pdf:
                page = pdf.pages[page_num]
                tables = page.extract_tables()
        except Exception as exc:
            logger.warning(
                "pdfplumber failed on page %d: %s", page_num + 1, exc
            )
            self.qa_issues.append(
                {
                    "page": page_num + 1,
                    "type": "table_extraction_error",
                    "detail": f"pdfplumber error: {exc}",
                    "severity": "warning",
                }
            )
            return None

        if not tables:
            return None

        raw_table = tables[0]
        if not raw_table or len(raw_table) < 2:
            return None

        self._table_counter += 1
        table_id = f"t{self._table_counter}"

        header = [clean_table_cell(c) for c in raw_table[0]]
        data_rows = [
            [clean_table_cell(c) for c in row] for row in raw_table[1:]
        ]

        table_data = {
            "page": page_num + 1,
            "block_id": f"tbl_{page_num + 1}",
            "type": "table",
            "table_id": table_id,
            "header": header,
            "rows": data_rows,
            "row_count": len(data_rows),
            "col_count": len(header),
            "source": {
                "page": page_num + 1,
                "method": "pdfplumber_table_extraction",
                "table_index": 0,
            },
        }
        self.blocks.append(table_data)

        # Sum consistency check
        sum_issues = check_sum_consistency(header, data_rows)
        for iss in sum_issues:
            iss["page"] = page_num + 1
            self.qa_issues.append(iss)

        return table_data

    # -- Markdown output ----------------------------------------------------

    def _write_markdown(self, pages_data: list[dict[str, Any]]) -> None:
        """Write document.md with page markers."""
        lines: list[str] = []
        lines.append(
            f"<!-- PDF: {self.pdf_path.name} | "
            f"Generated: {datetime.now().isoformat()} -->\n"
        )

        for page_num, data in enumerate(pages_data):
            lines.append(f"\n<!-- page: {page_num + 1} -->\n")

            if data["type"] == "image":
                lines.append(
                    f"> ⚠️ **Page {page_num + 1} is an image/scan page — "
                    f"text layer not available. OCR required.**\n"
                )
                continue

            # Write text blocks
            for block in data["text_blocks"]:
                self._write_markdown_block(lines, block)

            # Write table
            if data["table"]:
                self._write_markdown_table(lines, data["table"])

        md_content = "\n".join(lines)
        output_path = self.output_dir / "document.md"
        output_path.write_text(md_content, encoding="utf-8")
        logger.info("Written: %s", output_path)

    def _write_markdown_block(
        self, lines: list[str], block: dict[str, Any]
    ) -> None:
        """Write a single text block as markdown."""
        text = block["text"]
        btype = block["type"]

        if btype == "heading":
            lines.append(f"## {text}\n")
        elif btype == "table_caption":
            lines.append(f"**{text}**\n")
        elif btype == "footnote":
            lines.append(f"_{text}_\n")
        elif btype == "paragraph":
            lines.append(f"{text}\n")

    def _write_markdown_table(
        self, lines: list[str], table: dict[str, Any]
    ) -> None:
        """Write a table as GitHub-flavored markdown."""
        header = table["header"]
        rows = table["rows"]
        table_id = table["table_id"]

        sep = "| " + " | ".join("---" for _ in header) + " |"
        header_line = "| " + " | ".join(header) + " |"

        lines.append(f"<!-- {table_id} -->")
        lines.append(header_line)
        lines.append(sep)
        for row in rows:
            padded = row + [""] * (len(header) - len(row))
            lines.append("| " + " | ".join(padded) + " |")
        lines.append("")

    # -- Blocks JSON output -------------------------------------------------

    def _write_blocks_json(self) -> None:
        """Write structured blocks.json."""
        output = {
            "metadata": {
                "source_pdf": self.pdf_path.name,
                "generated_at": datetime.now().isoformat(),
                "total_pages": self.page_count,
                "total_blocks": len(self.blocks),
            },
            "blocks": self.blocks,
        }
        output_path = self.output_dir / "blocks.json"
        output_path.write_text(
            json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info("Written: %s", output_path)

    # -- QA report ----------------------------------------------------------

    def _write_qa_report(self, start: datetime) -> None:
        """Write QA report with parsing quality assessment."""
        elapsed = datetime.now() - start
        text_pages = self.page_count - len(self.image_pages)

        # Gather stats
        heading_count = sum(
            1 for b in self.blocks if b.get("type") == "heading"
        )
        table_count = sum(1 for b in self.blocks if b.get("type") == "table")
        paragraph_count = sum(
            1 for b in self.blocks if b.get("type") == "paragraph"
        )
        footnote_count = sum(
            1 for b in self.blocks if b.get("type") == "footnote"
        )
        caption_count = sum(
            1 for b in self.blocks if b.get("type") == "table_caption"
        )
        image_count = len(self.image_pages)

        errors = [i for i in self.qa_issues if i.get("severity") == "error"]
        warnings = [i for i in self.qa_issues if i.get("severity") == "warning"]

        lines: list[str] = []
        lines.append("# PDF Parse QA Report\n")
        lines.append(f"- **Source**: `{self.pdf_path.name}`")
        lines.append(f"- **Generated**: {datetime.now().isoformat()}")
        lines.append(f"- **Elapsed**: {elapsed.total_seconds():.1f}s\n")

        lines.append("## Summary\n")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Total pages | {self.page_count} |")
        lines.append(f"| Text pages | {text_pages} |")
        lines.append(f"| Image pages | {image_count} |")
        lines.append(f"| Headings detected | {heading_count} |")
        lines.append(f"| Paragraphs | {paragraph_count} |")
        lines.append(f"| Table captions | {caption_count} |")
        lines.append(f"| Footnotes | {footnote_count} |")
        lines.append(f"| Tables extracted | {table_count} |")
        lines.append(f"| Total blocks | {len(self.blocks)} |")
        lines.append(f"| Issues (error) | {len(errors)} |")
        lines.append(f"| Issues (warning) | {len(warnings)} |\n")

        # Per-page breakdown
        lines.append("## Per-Page Breakdown\n")
        lines.append("| Page | Type | Blocks | Table | Issues | Notes |")
        lines.append("|------|------|--------|-------|--------|-------|")
        for page_num in range(1, self.page_count + 1):
            page_blocks = [b for b in self.blocks if b.get("page") == page_num]
            page_issues = [
                i for i in self.qa_issues if i.get("page") == page_num
            ]
            has_table = any(b.get("type") == "table" for b in page_blocks)

            if page_num in self.image_pages:
                ptype = "🖼️ Image"
                notes = "Needs OCR"
            else:
                ptype = "📄 Text"
                notes = ""

            lines.append(
                f"| {page_num} | {ptype} | {len(page_blocks)} | "
                f"{'✅' if has_table else '—'} | {len(page_issues)} | "
                f"{notes} |"
            )
        lines.append("")

        # Issues
        lines.append("## Issues Found\n")
        if not self.qa_issues:
            lines.append("_No issues detected._\n")
        else:
            for iss in self.qa_issues:
                sev = iss.get("severity", "info")
                icon_map = {
                    "error": "🔴",
                    "warning": "🟡",
                    "info": "🔵",
                }
                icon = icon_map.get(sev, "🔵")
                lines.append(f"### {icon} Page {iss['page']}: {iss['type']}")
                lines.append("")
                lines.append(f"- **Severity**: {sev}")
                lines.append(f"- **Detail**: {iss['detail']}")
                lines.append("")

        # Human review checklist
        lines.append("---\n")
        lines.append("## Human Review Checklist\n")
        lines.append(
            "The following items **cannot be fully automated** and require "
            "human verification:\n"
        )

        # Image pages
        if self.image_pages:
            lines.append(
                "### 🖼️ Image / Scan Pages\n"
                f"- **Pages**: {', '.join(str(p) for p in self.image_pages)}\n"
                "- **Note**: No OCR applied — manual transcription or OCR "
                "engine needed.\n"
            )
        else:
            lines.append(
                "### 🖼️ Image / Scan Pages\n- **Status**: No image pages "
                "detected.\n"
            )

        # Sum mismatch
        sum_pages = sorted(
            set(
                i["page"]
                for i in self.qa_issues
                if i.get("type") == "sum_mismatch"
            )
        )
        if sum_pages:
            lines.append(
                "### 🔢 Numeric Totals (合计)\n"
                f"- **Pages**: {', '.join(str(p) for p in sum_pages)}\n"
                "- **Note**: Sum of detail rows != 合计 value. "
                "Investigate before use.\n"
            )
        else:
            lines.append(
                "### 🔢 Numeric Totals (合计)\n- **Status**: All totals "
                "verified.\n"
            )

        # Table structure review
        lines.append(
            "### 📊 Table Structure\n"
            "- **Note**: Verify column alignment, merged cells, and "
            "multi-line cells manually.\n"
            "- **Cross-page tables**: Check if tables split across pages "
            "are reconstructed correctly.\n"
        )

        # Source locator check
        lines.append(
            "### 📍 Source Traceability\n"
            "- **Note**: Each block includes page number and bounding box "
            "in `blocks.json`.\n"
            "- **Verification**: Spot-check 2-3 blocks to confirm "
            "page/bbox match the original PDF.\n"
        )

        lines.append("---\n")
        lines.append(
            "## Recommendations\n\n"
            "1. **OCR**: Page 3 (image page) needs OCR; consider using "
            "PaddleOCR / Tesseract.\n"
            "2. **Table review**: Verify column alignment in extracted "
            "tables, especially for multi-line cells.\n"
            "3. **Footnote mapping**: Ensure footnotes are linked to their "
            "respective tables.\n"
            "4. **Cross-page elements**: Check for headers/footers that "
            "may have been skipped incorrectly.\n"
            "5. **Numerical accuracy**: Spot-check total amounts against "
            "source documents.\n"
        )

        content = "\n".join(lines)
        output_path = self.output_dir / "qa_report.md"
        output_path.write_text(content, encoding="utf-8")
        logger.info("Written: %s", output_path)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: python {Path(__file__).name} <input_pdf>")
        print(
            f"   eg: python {Path(__file__).name} "
            "sample_pdf_to_markdown_note.pdf"
        )
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_dir = os.environ.get("OUTPUT_DIR", "outputs")

    converter = PDFToMarkdownConverter(pdf_path, output_dir)
    try:
        converter.run()
    except Exception:
        logger.error("Fatal error during conversion:\n%s", traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
