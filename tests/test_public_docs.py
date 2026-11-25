from pathlib import Path

from opencatwatch.hygiene import PUBLIC_DOC_FILENAMES, validate_public_docs


def test_docs_directory_stays_public_only() -> None:
    project_root = Path(__file__).resolve().parents[1]
    assert validate_public_docs(project_root) == []


def _write_public_docs(root: Path) -> Path:
    docs = root / "docs"
    docs.mkdir()
    for name in PUBLIC_DOC_FILENAMES:
        (docs / name).write_text("# Doc\n\nSee [METHODS.md](METHODS.md).\n", encoding="utf-8")
    return docs


def test_release_check_rejects_links_to_private_working_notes(tmp_path: Path) -> None:
    # A public doc that points readers at a private note file would leak its name and a dead link.
    docs = _write_public_docs(tmp_path)
    (docs / "METHODS.md").write_text("Follow handoff-notes.md before editing.\n", encoding="utf-8")

    errors = validate_public_docs(tmp_path)

    assert errors == ["docs/METHODS.md names a non-public Markdown file: handoff-notes.md"]


def test_release_check_rejects_extra_docs_and_agent_markers(tmp_path: Path) -> None:
    docs = _write_public_docs(tmp_path)
    (docs / "PLAN.md").write_text("Next command: run the fetch.\n", encoding="utf-8")

    errors = validate_public_docs(tmp_path)

    assert "unexpected docs files: PLAN.md" in errors
    assert "docs/PLAN.md contains forbidden marker: next command" in errors
