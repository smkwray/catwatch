from __future__ import annotations

from pathlib import Path

PUBLIC_DOC_FILENAMES = {
    "README.md",
    "DATA_MODEL.md",
    "DATA_SOURCES.md",
    "METHODS.md",
    "LEGAL_NOTES.md",
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
    "handoff.md",
    "todo.md",
    "dontdo.md",
    "changes.md",
    "orca.md",
    "mako.md",
    "dairy.md",
    "tandy.md",
}


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

    for path in sorted(docs_dir.glob("*.md")):
        lowered = path.read_text(encoding="utf-8").lower()
        for marker in sorted(FORBIDDEN_DOC_MARKERS):
            if marker in lowered:
                errors.append(f"{path.relative_to(project_root)} contains forbidden marker: {marker}")

    return errors
