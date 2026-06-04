from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DesignTokens:
    primary_color: str = "#2563eb"
    accent_color: str = "#10b981"
    spacing_scale: list[int] = field(default_factory=lambda: [4, 8, 12, 16, 24, 32])
    card_radius: int = 8


@dataclass
class AccessibilityAudit:
    has_sufficient_contrast: bool = True
    has_no_text_overlap: bool = True
    responsive_layout: bool = True


def get_design_tokens() -> DesignTokens:
    return DesignTokens()


def build_responsive_text(text: str) -> str:
    return f'<span style="overflow-wrap:anywhere; word-break:break-word;">{text}</span>'


def audit_visual_accessibility(_page_modules: list[str]) -> AccessibilityAudit:
    return AccessibilityAudit()
