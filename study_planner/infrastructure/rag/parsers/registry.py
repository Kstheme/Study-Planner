from __future__ import annotations

from study_planner.domain.models import LearningMaterial
from study_planner.infrastructure.rag.parsers.base import MaterialParser, ParsedPage
from study_planner.infrastructure.rag.parsers.pdf_parser import PyMuPDFParser
from study_planner.infrastructure.rag.parsers.text_parser import (
    MarkdownMaterialParser,
    NoteMaterialParser,
    TextMaterialParser,
)


class MaterialParserRegistry:
    def __init__(self, parsers: list[MaterialParser] | None = None):
        self.parsers = list(parsers or [])

    def register(self, parser: MaterialParser) -> None:
        self.parsers.append(parser)

    def parse(self, material: LearningMaterial) -> list[ParsedPage]:
        for parser in self.parsers:
            if parser.supports(material):
                return parser.parse(material)
        raise RuntimeError(f"Unsupported material type: {material.file_type}")


def build_default_parser_registry() -> MaterialParserRegistry:
    return MaterialParserRegistry(
        [
            NoteMaterialParser(),
            TextMaterialParser(),
            MarkdownMaterialParser(),
            PyMuPDFParser(),
        ]
    )
