"""Static publication-readiness checks.

These tests deliberately avoid AllenSDK, Qt rendering, and large data downloads.
They guard the lightweight paths reviewers should be able to run immediately
after cloning the repository.
"""

import json
import re
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def test_package_metadata_uses_canonical_lowercase_package() -> None:
    pyproject = _read("pyproject.toml")

    assert 'synaptipy = "synaptipy.application.__main__:run_gui"' in pyproject
    assert 'synaptipy-batch = "synaptipy.application.cli.main:main"' in pyproject
    assert "[tool.setuptools.package-data]\nsynaptipy = [" in pyproject
    assert 'known_first_party = ["synaptipy"]' in pyproject
    assert 'source = ["src/synaptipy"]' in pyproject


def test_python_sources_do_not_import_capitalized_package_name() -> None:
    roots = ["src", "tests", "scripts", "examples", "validation", "paper/scripts"]
    forbidden = re.compile(
        r"(?m)^\s*(from|import)\s+Synaptipy\b"
        r"|\bSynaptipy\.(application|core|infrastructure|shared|templates)\b"
        r"|\bsrc/Synaptipy\b"
        r"|\bpython -m Synaptipy\b"
    )
    offenders = []

    for root in roots:
        for path in (PROJECT_ROOT / root).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            if forbidden.search(text):
                offenders.append(str(path.relative_to(PROJECT_ROOT)))

    assert not offenders, "Capitalized package imports found: " + ", ".join(sorted(offenders))


def test_paper_orchestrator_references_existing_scripts() -> None:
    script = PROJECT_ROOT / "paper" / "scripts" / "paper_figures" / "generate_paper_figures.py"
    text = script.read_text(encoding="utf-8")

    assert "benchmark_rendering.py" not in text
    assert "benchmark_e2e.py" not in text
    assert "benchmark_rendering_e2e.py" in text

    required = [
        "paper/scripts/generate_benchmarks.py",
        "paper/scripts/benchmark_rendering_e2e.py",
        "paper/scripts/generate_paper_tables.py",
        "paper/scripts/paper_figures/figure_01.py",
        "paper/scripts/paper_figures/figure_02.py",
        "paper/scripts/paper_figures/figure_03.py",
        "paper/data_manifest.json",
    ]
    missing = [path for path in required if not (PROJECT_ROOT / path).exists()]
    assert not missing, "Missing paper reproduction files: " + ", ".join(missing)


def test_paper_validation_cohort_is_manifest_driven() -> None:
    manifest = json.loads(_read("paper/data_manifest.json"))
    cells = manifest.get("cells", [])
    assert len(cells) == manifest["selection"]["target_cell_count"]
    assert all("cell_id" in cell and "structure" in cell for cell in cells)

    table_script = _read("paper/scripts/generate_paper_tables.py")
    assert "requested_cells = [" not in table_script
    assert "load_data_manifest" in table_script


def test_basic_example_uses_current_public_api() -> None:
    example = _read("examples/basic_usage.py")
    stale_patterns = [
        "synaptipy.analysis",
        "trial_t_starts=",
        ".add_channel(",
        ".get_channel_by_name(",
    ]
    offenders = [pattern for pattern in stale_patterns if pattern in example]
    assert not offenders, "Stale basic_usage.py API patterns: " + ", ".join(offenders)


def test_paper_requirements_are_pinned() -> None:
    requirements = PROJECT_ROOT / "paper" / "envs" / "requirements_paper.txt"
    floating = []
    for raw_line in requirements.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line == "-e .":
            continue
        if "==" not in line:
            floating.append(line)

    assert not floating, "Unpinned paper requirements: " + ", ".join(floating)


def test_dockerfile_copies_validation_and_paper_inputs() -> None:
    dockerfile = _read("Dockerfile")
    for expected in [
        "COPY tests/ tests/",
        "COPY validation/ validation/",
        "COPY examples/ examples/",
        "COPY paper/ paper/",
    ]:
        assert expected in dockerfile


def test_no_literal_workspace_root_artifacts_are_tracked() -> None:
    result = subprocess.run(["git", "ls-files"], cwd=PROJECT_ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    offenders = [path for path in result.stdout.splitlines() if "$WORKSPACE_ROOT" in Path(path).parts]
    assert not offenders, "Literal $WORKSPACE_ROOT artifacts found: " + ", ".join(offenders)
