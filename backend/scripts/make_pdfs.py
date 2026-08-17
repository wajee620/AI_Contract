"""Generate PDF versions of the synthetic contracts, plus a scanned (image-only,
no text layer) variant of contract 01 to exercise the vision-OCR path.

Usage:  python scripts/make_pdfs.py [data_dir]
"""
import sys
from pathlib import Path

import fitz  # PyMuPDF
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def txt_to_pdf(txt_path: Path, pdf_path: Path) -> None:
    styles = getSampleStyleSheet()
    body = ParagraphStyle("Body", parent=styles["Normal"], fontName="Times-Roman",
                          fontSize=10.5, leading=14, spaceAfter=6)
    title = ParagraphStyle("Title2", parent=styles["Title"], fontName="Times-Bold", fontSize=14)

    doc = SimpleDocTemplate(str(pdf_path), pagesize=A4,
                            leftMargin=2.2 * cm, rightMargin=2.2 * cm,
                            topMargin=2 * cm, bottomMargin=2 * cm)
    flow = []
    for i, para in enumerate(txt_path.read_text(encoding="utf-8").split("\n\n")):
        para = para.strip()
        if not para:
            continue
        text = para.replace("\n", "<br/>")
        flow.append(Paragraph(text, title if i == 0 else body))
        flow.append(Spacer(1, 4))
    doc.build(flow)
    print(f"wrote {pdf_path}")


def pdf_to_scanned(pdf_path: Path, scanned_path: Path, dpi: int = 150) -> None:
    """Rasterize every page to an image-only PDF (no text layer) to simulate a scan."""
    src = fitz.open(str(pdf_path))
    dst = fitz.open()
    for page in src:
        pix = page.get_pixmap(dpi=dpi)
        new_page = dst.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(new_page.rect, pixmap=pix)
    dst.save(str(scanned_path))
    dst.close()
    src.close()
    print(f"wrote {scanned_path} (image-only)")


def main() -> None:
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2] / "data"
    contracts = data_dir / "contracts"
    for txt in sorted(contracts.glob("*.txt")):
        txt_to_pdf(txt, txt.with_suffix(".pdf"))
    first = contracts / "01_msa_orion_helix.pdf"
    if first.exists():
        pdf_to_scanned(first, contracts / "03_msa_orion_helix_scanned.pdf")


if __name__ == "__main__":
    main()
