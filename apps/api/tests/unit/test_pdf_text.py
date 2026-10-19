"""Page text with pypdfium2 (ARCHITECTURE §3 / D1)."""

import pytest

from seedoc.ai.pdf_text import PdfReadError, clean_text, extract_page_texts
from tests.pdfs import make_pdf


def test_extract_gives_one_text_per_page() -> None:
    data = make_pdf(["Sicherheitshinweise für Bediener\nGefahr durch Laserstrahlung", "", "Wartung (täglich)"])

    pages = extract_page_texts(data)

    assert pages == ["Sicherheitshinweise für Bediener\nGefahr durch Laserstrahlung", "", "Wartung (täglich)"]


@pytest.mark.parametrize(
    "data", [b"%PDF-1.7\nnot really a pdf\n%%EOF\n", b"", b"\x00" * 64], ids=["garbage", "empty", "zeros"]
)
def test_unreadable_file_raises(data: bytes) -> None:
    with pytest.raises(PdfReadError):
        extract_page_texts(data)


def test_clean_text_normalises_what_pdfium_returns() -> None:
    raw = "\N{REPLACEMENT CHARACTER}  Erste\N{NO-BREAK SPACE} Zeile \r\n\r\n\tzweite\N{SOFT HYPHEN}Zeile\x00\rdritte "

    assert clean_text(raw) == "Erste Zeile\nzweiteZeile\ndritte"
