from __future__ import annotations

from pathlib import Path

from study_planner.domain.models import LearningMaterial
from study_planner.infrastructure.rag.parsers.base import ParsedPage


class PyMuPDFParser:
    def supports(self, material: LearningMaterial) -> bool:
        return material.file_type == "pdf"

    def parse(self, material: LearningMaterial) -> list[ParsedPage]:
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError("Parsing PDF files requires installing PyMuPDF.") from exc

        path = Path(material.source_path)
        document = fitz.open(str(path))
        try:
            return [
                {"text": page.get_text("text") or "", "page_number": index + 1}
                for index, page in enumerate(document)
            ]
        finally:
            document.close()
