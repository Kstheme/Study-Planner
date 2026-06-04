from __future__ import annotations

import re


SENSITIVE_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]+"),
    re.compile(r"(?i)(api[_-]?key\s*=\s*)[^\s;]+"),
    re.compile(r"(?i)(password\s*=\s*)[^\s;]+"),
    re.compile(r"(?i)(token\s*=\s*)[^\s;]+"),
]


def sanitize_error_message(message: object) -> str:
    text = str(message)
    for pattern in SENSITIVE_PATTERNS:
        text = pattern.sub(lambda match: match.group(1) + "[redacted]" if match.groups() else "[redacted]", text)
    return text.replace("Traceback:", "").strip()


def render_user_error(error: Exception | str) -> str:
    return sanitize_error_message(error)
