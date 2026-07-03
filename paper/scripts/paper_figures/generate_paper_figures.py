import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def run_script(script_path: Path, args=None):
    """Run a Python script via subprocess and stream output."""
    args = args or []
    print(f"\n{'='*60}\nRunning: {script_path.name}\n{'='*60}")
    if not script_path.exists():
        print(f"Error: Script {script_path} does not exist.", file=sys.stderr)
        sys.exit(1)

    res = subprocess.run([sys.executable, str(script_path), *args], check=False)
    if res.returncode != 0:
        print(f"\nError: Script {script_path.name} failed with exit code {res.returncode}.", file=sys.stderr)
        sys.exit(res.returncode)


def validate_inputs(repo_root: Path, scripts_dir: Path, paper_figures_dir: Path, manifest_path: Path) -> None:
    """Fail fast when a reviewer cannot reproduce the paper from the checked-out tree."""
    required = [
        scripts_dir / "generate_benchmarks.py",
        scripts_dir / "benchmark_rendering_e2e.py",
        scripts_dir / "generate_paper_tables.py",
        paper_figures_dir / "figure_01.py",
        paper_figures_dir / "figure_02.py",
        paper_figures_dir / "figure_03.py",
        manifest_path,
        repo_root / "paper" / "paper.md",
    ]
    missing = [path for path in required if not path.exists()]
    if missing:
        for path in missing:
            print(f"Missing required paper artifact: {path}", file=sys.stderr)
        raise SystemExit(1)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("cells"):
        raise SystemExit(f"Manifest has no cells: {manifest_path}")


def write_orchestrator_provenance(repo_root: Path, args: argparse.Namespace) -> None:
    out_dir = repo_root / "paper" / "analysis_results"
    out_dir.mkdir(parents=True, exist_ok=True)
    serializable_args = {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()}
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "arguments": serializable_args,
    }
    (out_dir / "reproduction_orchestrator_provenance.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Orchestrator for SynaptiPy paper figures.")
    parser.add_argument(
        "--run-analysis", action="store_true", help="Run analysis scripts (benchmarks, tables) before plotting figures."
    )
    parser.add_argument("--force", action="store_true", help="Force regeneration of cached table outputs.")
    parser.add_argument("--check-only", action="store_true", help="Validate script paths and manifest, then exit.")
    parser.add_argument(
        "--skip-rendering-benchmark",
        action="store_true",
        help="Skip GUI rendering benchmarks; useful on headless machines without xvfb.",
    )
    parser.add_argument("--skip-raw-plots", action="store_true", help="Pass --skip-plots to generate_paper_tables.py.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Dataset manifest JSON. Defaults to paper/data_manifest.json.",
    )
    parser.add_argument(
        "--figures",
        nargs="+",
        type=int,
        default=[1, 2, 3],
        help="List of figure numbers to plot (e.g., --figures 1 2). Default is all (1-3).",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    scripts_dir = repo_root / "paper" / "scripts"
    paper_figures_dir = scripts_dir / "paper_figures"
    manifest_path = args.manifest or (repo_root / "paper" / "data_manifest.json")

    validate_inputs(repo_root, scripts_dir, paper_figures_dir, manifest_path)
    if args.check_only:
        print("Paper reproduction check passed.")
        return 0

    # 1. Run Analysis Scripts (if requested)
    if args.run_analysis:
        analysis_scripts = [
            (scripts_dir / "generate_benchmarks.py", []),
        ]
        if not args.skip_rendering_benchmark:
            analysis_scripts.append((scripts_dir / "benchmark_rendering_e2e.py", []))
        table_args = ["--manifest", str(manifest_path)]
        if args.force:
            table_args.append("--force")
        if args.skip_raw_plots:
            table_args.append("--skip-plots")
        analysis_scripts.append((scripts_dir / "generate_paper_tables.py", table_args))

        print("\n" + "#" * 60)
        print("PHASE 1: RUNNING ANALYSIS SCRIPTS")
        print("#" * 60)
        for script, script_args in analysis_scripts:
            run_script(script, script_args)

    # 2. Run Figure Scripts
    print("\n" + "#" * 60)
    print("PHASE 2: RUNNING FIGURE PLOTTING SCRIPTS")
    print("#" * 60)

    for fig_num in args.figures:
        fig_script = paper_figures_dir / f"figure_{fig_num:02d}.py"
        run_script(fig_script)

    write_orchestrator_provenance(repo_root, args)
    print(f"\nSuccessfully generated requested figures: {args.figures}")
    print("All figures are saved in paper/figures/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
