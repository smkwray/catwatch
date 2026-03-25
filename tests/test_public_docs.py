from pathlib import Path

from opencatwatch.hygiene import validate_public_docs


def test_docs_directory_stays_public_only() -> None:
    project_root = Path(__file__).resolve().parents[1]
    assert validate_public_docs(project_root) == []
