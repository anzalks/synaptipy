#!/usr/bin/env python3
"""
Local CI Verification Script for Synaptipy.
Runs the same checks as the GitHub Actions workflow to ensure cross-platform compatibility.
"""

import argparse
import os
import platform
import re
import subprocess
import sys
from typing import List, Tuple


def run_command(command: List[str], description: str) -> Tuple[bool, str]:
    """Run a shell command and return (success, output)."""
    print(f"Running: {description}...")
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, check=False  # We want to handle the return code manually
        )
        if result.returncode == 0:
            print(f"[PASS] {description} Passed")
            return True, result.stdout
        else:
            print(f"[FAIL] {description} Failed")
            print(result.stdout)
            print(result.stderr)
            return False, result.stdout + result.stderr
    except FileNotFoundError:
        print(f"[FAIL] {description} Failed: Command not found")
        return False, "Command not found"


def check_dependencies():
    """Check if required tools are installed, install if missing."""
    tools = ["flake8", "pytest"]
    for tool in tools:
        print(f"Checking for {tool}...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "show", tool], capture_output=True, check=True)
        except subprocess.CalledProcessError:
            print(f"[WARN] {tool} not found. Installing...")
            try:
                subprocess.run([sys.executable, "-m", "pip", "install", tool, "pytest-qt", "pytest-mock"], check=True)
            except subprocess.CalledProcessError:
                print("[WARN] Standard install failed (PEP 668?). Retrying with --break-system-packages...")
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pip",
                        "install",
                        tool,
                        "pytest-qt",
                        "pytest-mock",
                        "--break-system-packages",
                    ],
                    check=True,
                )


def check_flake8() -> bool:
    """Run flake8 linting with strict settings."""
    # Matches GitHub Actions: flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
    success_critical, _ = run_command(
        [sys.executable, "-m", "flake8", ".", "--count", "--select=E9,F63,F7,F82", "--show-source", "--statistics"],
        "Critical Syntax Check",
    )

    # Matches GitHub Actions (Strict Mode requested by User):
    # flake8 . --count --max-complexity=10 --max-line-length=127 --statistics
    # Removed --exit-zero to enforce strictness
    success_style, _ = run_command(
        [
            sys.executable,
            "-m",
            "flake8",
            ".",
            "--count",
            "--max-complexity=10",
            "--max-line-length=127",
            "--statistics",
        ],
        "Style & Complexity Check",
    )

    return success_critical and success_style


def check_tests() -> bool:
    """Run pytest with offscreen platform."""
    import os

    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"

    print("Running: Pytest (Headless)...")
    try:
        # Check if pytest exists first to avoid crash
        subprocess.run([sys.executable, "-m", "pytest", "--version"], capture_output=True, check=True)

        result = subprocess.run(
            [sys.executable, "-m", "pytest"],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,  # Overall timeout of 2 minutes for all tests
        )
        if result.returncode == 0:
            print("[PASS] Pytest Passed")
            return True
        else:
            print("[FAIL] Pytest Failed")
            # print(result.stdout)  # Can be too long, maybe summarize?
            # For now print last 20 lines
            lines = (result.stdout + result.stderr).splitlines()
            print("\n".join(lines[-30:]))
            return False
    except subprocess.TimeoutExpired:
        print("[FAIL] Pytest timed out after 120 seconds. A test may be blocking/hanging.")
        return False
    except Exception as e:
        print(f"[FAIL] Pytest Execution Failed: {e}")
        return False


def check_no_emojis() -> bool:  # noqa: C901
    """Scan codebase for emojis.

    Covers both supplementary-plane emoji (U+10000-U+10FFFF) and the common
    BMP blocks that host decorative emoji used in markdown files:
    - U+2600-U+26FF: Miscellaneous Symbols (e.g. warning sign U+26A0, checkmark
      U+2705 falls nearby)
    - U+2700-U+27BF: Dingbats (e.g. heavy check mark U+2714, cross mark U+274C,
      sparkles U+2728)
    - U+2B50, U+2B55: star and circle symbols used as emoji
    - U+FE00-U+FE0F: Unicode variation selectors (e.g. U+FE0F appended to
      U+26A0 to produce the full-colour warning emoji)

    Excluded intentionally to avoid false positives:
    - U+2300-U+25FF: Misc Technical, Box Drawing, Block Elements, Geometric
      Shapes -- all legitimately used in code comments and YAML as structural
      visual separators (e.g. the section-divider pattern # -- Name --).
    """
    print("Running: Emoji Scanner...")
    # Combined pattern: supplementary-plane emoji AND true BMP emoji blocks.
    # Range U+2600-U+27BF covers Miscellaneous Symbols and Dingbats.
    # Range U+2B50-U+2B55 covers star/circle emoji.
    # Range U+FE00-U+FE0F covers variation selectors (tone/colour modifiers).
    emoji_pattern = re.compile(
        r"[\u2600-\u27BF"  # Misc Symbols (warning ⚠, checkmark ✅) + Dingbats (❌ ✨)
        r"\u2B50\u2B55"  # star and circle emoji
        r"\uFE00-\uFE0F"  # variation selectors (e.g. \uFE0F after ⚠)
        r"\U00010000-\U0010ffff]",  # supplementary plane (😀 🎉 etc.)
        flags=re.UNICODE,
    )

    found_emojis = False
    affected_files = []

    for root, dirs, files in os.walk("."):
        if ".git" in dirs:
            dirs.remove(".git")
        if "__pycache__" in dirs:
            dirs.remove("__pycache__")
        if ".idea" in dirs:
            dirs.remove(".idea")

        for file in files:
            if file.endswith((".py", ".md", ".txt", ".yml", ".yaml")):
                path = os.path.join(root, file)
                # Skip the verification script itself
                if "verify_ci.py" in path:
                    continue
                # Skip the rules file (as it contains the example prohibited emojis)
                if ".agent/rules.md" in path:
                    continue
                # Skip virtual environment directories and docs
                if any(
                    x in path
                    for x in [
                        "site-packages",
                        "dist-packages",
                        "venv",
                        ".env",
                        ".verify_venv_temp",
                        "lib/python",
                        "docs/",
                    ]
                ):
                    continue

                try:
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                        if emoji_pattern.search(content):
                            found_emojis = True
                            affected_files.append(path)
                except UnicodeDecodeError:
                    pass  # Skip binary files

    if found_emojis:
        print("[FAIL] Emoji Check Failed: Emojis found in the following files:")
        for f in affected_files:
            print(f"  - {f}")
        return False
    else:
        print("[PASS] Emoji Check Passed")
        return True


def check_screenshots() -> bool:
    """Regenerate documentation screenshots headlessly and verify exit code."""
    script = os.path.join(os.path.dirname(__file__), "capture_screenshots.py")
    if not os.path.exists(script):
        print("[FAIL] capture_screenshots.py not found")
        return False

    print("Running: Screenshot Capture (headless)...")
    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")

    try:
        result = subprocess.run(
            [sys.executable, script],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            print("[PASS] Screenshot Capture Passed")
            return True
        else:
            print("[FAIL] Screenshot Capture Failed")
            print(result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
            print(result.stderr[-1000:] if len(result.stderr) > 1000 else result.stderr)
            return False
    except subprocess.TimeoutExpired:
        print("[FAIL] Screenshot Capture timed out after 60 seconds")
        return False
    except Exception as exc:
        print(f"[FAIL] Screenshot Capture raised: {exc}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Local CI verification for Synaptipy.")
    parser.add_argument(
        "--with-screenshots",
        action="store_true",
        help="Also regenerate docs screenshots (headless; adds ~20 s).",
    )
    args, _ = parser.parse_known_args()

    print(f"[INFO] Starting Local CI Verification on {platform.system()}...")

    # Ensure dependencies are present
    try:
        check_dependencies()
    except Exception as e:
        print(f"[WARN] Dependency Check Failed: {e}")
        print("Proceeding with checks anyway...")

    checks = [
        check_flake8(),
        check_tests(),
        check_no_emojis(),
    ]

    if args.with_screenshots:
        checks.append(check_screenshots())

    if all(checks):
        print("\n[SUCCESS] All CI Checks Passed! You are ready to push.")
        sys.exit(0)
    else:
        print("\n[FAIL] Some checks failed. Please fix them before pushing.")
        sys.exit(1)


if __name__ == "__main__":
    main()
