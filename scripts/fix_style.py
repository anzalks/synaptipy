
from pathlib import Path


def fix_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        print(f"Skipping binary/non-utf8 file: {filepath}")
        return

    new_lines = []
    for line in lines:
        # Fix W293: Blank line contains whitespace
        if line.strip() == '' and len(line) > 1:
            new_lines.append('\n')
        else:
            new_lines.append(line)

    # Reconstruct content
    content = "".join(new_lines)

    # Fix W391: Blank line at end of file (and ensure exactly one newline)
    content = content.rstrip() + '\n'

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Fixed: {filepath}")


def main():
    root_dir = Path.cwd()
    dirs_to_check = ['src', 'tests', 'scripts']
    files_to_check = ['conftest.py']

    # Process directories
    for d in dirs_to_check:
        p = root_dir / d
        if p.exists():
            for filepath in p.rglob('*.py'):
                fix_file(filepath)

    # Process individual files
    for f in files_to_check:
        p = root_dir / f
        if p.exists():
            fix_file(p)


if __name__ == "__main__":
    main()
