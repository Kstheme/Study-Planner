from __future__ import annotations

from typing import Protocol

from study_planner.domain.models import LearningMaterial


ParsedPage = dict[str, str | int | None]


class MaterialParser(Protocol):
    def supports(self, material: LearningMaterial) -> bool:
        """Return whether this parser can handle the material."""

    def parse(self, material: LearningMaterial) -> list[ParsedPage]:
        """Parse a material into page-like text blocks."""
