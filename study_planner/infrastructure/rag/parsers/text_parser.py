from __future__ import annotations

from pathlib import Path

from study_planner.domain.models import LearningMaterial
from study_planner.infrastructure.rag.parsers.base import ParsedPage


class NoteMaterialParser:
    def supports(self, material: LearningMaterial) -> bool:
        return material.file_type == "note"

    def parse(self, material: LearningMaterial) -> list[ParsedPage]:
        return [{"text": material.raw_text, "page_number": None}]


class TextMaterialParser:
    def supports(self, material: LearningMaterial) -> bool:
        return material.file_type == "txt"

    def parse(self, material: LearningMaterial) -> list[ParsedPage]:
        return [{"text": Path(material.source_path).read_text(encoding="utf-8"), "page_number": None}]


class MarkdownMaterialParser:
    def supports(self, material: LearningMaterial) -> bool:
        return material.file_type == "markdown"

    def parse(self, material: LearningMaterial) -> list[ParsedPage]:
        return [{"text": Path(material.source_path).read_text(encoding="utf-8"), "page_number": None}]
