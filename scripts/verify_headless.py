#!/usr/bin/env python3
"""
Verify "Headless" Architecture.
Checks that core modules do NOT import PySide6.
"""
import os
import sys
import ast


def check_imports(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        try:
            tree = ast.parse(f.read(), filename=file_path)
        except SyntaxError:
            return False  # Skip files with syntax errors (or report them)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if 'PySide6' in alias.name or 'PyQt' in alias.name:
                    return False
        elif isinstance(node, ast.ImportFrom):
            if node.module and ('PySide6' in node.module or 'PyQt' in node.module):
                # Allow TYPE_CHECKING blocks
                return False
    return True


def main():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../src/Synaptipy/core'))
    print(f"Scanning {root_dir}...")

    failures = []
    for root, dirs, files in os.walk(root_dir):
        for file in files:
            if file.endswith('.py'):
                path = os.path.join(root, file)
                if not check_imports(path):
                    failures.append(path)

    if failures:
        print("FAIL: The following core files import GUI libraries:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)

    print("PASS: No GUI imports found in Core.")
    sys.exit(0)


if __name__ == "__main__":
    main()
