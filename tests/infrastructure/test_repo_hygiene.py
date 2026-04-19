"""Repository hygiene tests."""

from pathlib import Path


def test_no_whitespace_only_python_files() -> None:
    """Python source files should not be empty or whitespace-only."""
    project_root = Path(__file__).resolve().parents[2]
    candidates = [project_root / "src", project_root / "tests"]

    whitespace_only_files = []
    for base in candidates:
        for py_file in base.rglob("*.py"):
            if py_file.read_text(encoding="utf-8").strip() == "":
                whitespace_only_files.append(str(py_file.relative_to(project_root)))

    assert not whitespace_only_files, "Whitespace-only Python files found: " + ", ".join(sorted(whitespace_only_files))
