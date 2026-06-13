# PDF Parse QA Report

- **Source**: `sample_pdf_to_markdown_note.pdf`
- **Generated**: 2026-06-13T16:19:05.641279
- **Elapsed**: 0.8s

## Summary

| Metric | Value |
|--------|-------|
| Total pages | 3 |
| Text pages | 2 |
| Image pages | 1 |
| Headings detected | 2 |
| Paragraphs | 3 |
| Table captions | 2 |
| Footnotes | 2 |
| Tables extracted | 2 |
| Total blocks | 12 |
| Issues (error) | 0 |
| Issues (warning) | 1 |

## Per-Page Breakdown

| Page | Type | Blocks | Table | Issues | Notes |
|------|------|--------|-------|--------|-------|
| 1 | 📄 Text | 6 | ✅ | 0 |  |
| 2 | 📄 Text | 5 | ✅ | 0 |  |
| 3 | 🖼️ Image | 1 | — | 1 | Needs OCR |

## Issues Found

### 🟡 Page 3: image_page_no_ocr

- **Severity**: warning
- **Detail**: Page detected as image-only; no OCR applied.

---

## Human Review Checklist

The following items **cannot be fully automated** and require human verification:

### 🖼️ Image / Scan Pages
- **Pages**: 3
- **Note**: No OCR applied — manual transcription or OCR engine needed.

### 🔢 Numeric Totals (合计)
- **Status**: All totals verified.

### 📊 Table Structure
- **Note**: Verify column alignment, merged cells, and multi-line cells manually.
- **Cross-page tables**: Check if tables split across pages are reconstructed correctly.

### 📍 Source Traceability
- **Note**: Each block includes page number and bounding box in `blocks.json`.
- **Verification**: Spot-check 2-3 blocks to confirm page/bbox match the original PDF.

---

## Recommendations

1. **OCR**: Page 3 (image page) needs OCR; consider using PaddleOCR / Tesseract.
2. **Table review**: Verify column alignment in extracted tables, especially for multi-line cells.
3. **Footnote mapping**: Ensure footnotes are linked to their respective tables.
4. **Cross-page elements**: Check for headers/footers that may have been skipped incorrectly.
5. **Numerical accuracy**: Spot-check total amounts against source documents.
