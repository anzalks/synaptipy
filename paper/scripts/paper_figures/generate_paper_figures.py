import argparse
import subprocess
import sys
from pathlib import Path


def run_script(script_path: Path):
    """Run a Python script via subprocess and stream output."""
    print(f"\n{'='*60}\nRunning: {script_path.name}\n{'='*60}")
    if not script_path.exists():
        print(f"Error: Script {script_path} does not exist.", file=sys.stderr)
        sys.exit(1)

    res = subprocess.run([sys.executable, str(script_path)], check=False)
    if res.returncode not in (0, -6):  # Ignore Qt Abort
        print(f"\nError: Script {script_path.name} failed with exit code {res.returncode}.", file=sys.stderr)
        sys.exit(res.returncode)


def main():
    parser = argparse.ArgumentParser(description="Orchestrator for SynaptiPy paper figures.")
    parser.add_argument(
        "--run-analysis", action="store_true", help="Run analysis scripts (benchmarks, tables) before plotting figures."
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

    # 1. Run Analysis Scripts (if requested)
    if args.run_analysis:
        analysis_scripts = [
            scripts_dir / "generate_benchmarks.py",
            scripts_dir / "benchmark_rendering.py",
            scripts_dir / "benchmark_e2e.py",
            scripts_dir / "generate_paper_tables.py",
        ]
        print("\n" + "#" * 60)
        print("PHASE 1: RUNNING ANALYSIS SCRIPTS")
        print("#" * 60)
        for script in analysis_scripts:
            run_script(script)

    # 2. Run Figure Scripts
    print("\n" + "#" * 60)
    print("PHASE 2: RUNNING FIGURE PLOTTING SCRIPTS")
    print("#" * 60)

    for fig_num in args.figures:
        fig_script = paper_figures_dir / f"figure_{fig_num:02d}.py"
        run_script(fig_script)

    print(f"\nSuccessfully generated requested figures: {args.figures}")
    print("All figures are saved in paper/figures/")


if __name__ == "__main__":
    main()
