from __future__ import annotations

import re
from pathlib import Path

PUBLIC_DOC_FILENAMES = {
    "README.md",
    "METHODS.md",
}

FORBIDDEN_DOC_MARKERS = {
    "codex",
    "gpt",
    "claude",
    "bootstrap guide",
    "read order",
    "first tasks",
    "next command",
    "resume snapshot",
}

# Public docs may name only the public doc files; any other Markdown file name
# (handoff notes, to-do lists, agent instructions) points at private working files.
MARKDOWN_NAME = re.compile(r"[a-z0-9_.-]+\.md\b")


def validate_public_docs(project_root: Path) -> list[str]:
    docs_dir = project_root / "docs"
    if not docs_dir.exists():
        return [f"missing docs directory: {docs_dir}"]

    errors: list[str] = []
    actual_files = {path.name for path in docs_dir.glob("*.md")}
    unexpected_files = sorted(actual_files - PUBLIC_DOC_FILENAMES)
    missing_files = sorted(PUBLIC_DOC_FILENAMES - actual_files)

    if unexpected_files:
        errors.append(f"unexpected docs files: {', '.join(unexpected_files)}")
    if missing_files:
        errors.append(f"missing public docs files: {', '.join(missing_files)}")

    allowed_names = {name.lower() for name in PUBLIC_DOC_FILENAMES}
    for path in sorted(docs_dir.glob("*.md")):
        rel = path.relative_to(project_root).as_posix()
        lowered = path.read_text(encoding="utf-8").lower()
        for marker in sorted(FORBIDDEN_DOC_MARKERS):
            if marker in lowered:
                errors.append(f"{rel} contains forbidden marker: {marker}")
        for name in sorted(set(MARKDOWN_NAME.findall(lowered)) - allowed_names):
            errors.append(f"{rel} names a non-public Markdown file: {name}")

    return errors
