"""Generate small CC0 synthetic PDF fixtures; no real papers or personal material."""

from pathlib import Path

import pymupdf


def generate(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as document:
        for number, text in enumerate(
            [
                "Synthetic Research A\nBaseline accuracy: 72%.\nThis sentence continues",
                "on the second page.\nTreatment accuracy: 81%.\nNot a scientific result.",
            ]
        ):
            page = document.new_page(width=400, height=500)
            page.insert_text((40, 60), text, fontsize=12)
            page.insert_text((40, 460), f"Page {number + 1}", fontsize=10)
        document.set_page_labels(
            [{"startpage": 0, "prefix": "S-", "style": "D", "firstpagenum": 1}]
        )
        document.save(directory / "two-pages.pdf")
        image = document[0].get_pixmap().tobytes("png")
        document.save(
            directory / "encrypted.pdf",
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            owner_pw="fixture-owner",
            user_pw="fixture-user",
        )
    with pymupdf.open() as scan:
        page = scan.new_page(width=400, height=500)
        page.insert_image(page.rect, stream=image)
        scan.save(directory / "image-only.pdf")
    (directory / "broken.pdf").write_bytes(b"%PDF-1.7\nnot a document\n")


if __name__ == "__main__":
    generate(Path(__file__).parent / "pdf")
