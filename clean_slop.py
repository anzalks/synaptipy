import os
import re

FILES = ["README.md", "docs/user_guide.md", "docs/developer_guide.md", "docs/algorithmic_definitions.md"]


def clean_slop(text):
    # It is important to note that -> remove and capitalize
    def repl_important(m):
        next_char = m.group(1)
        return next_char.upper()

    text = re.sub(r"(?i)It is important to note that\s+([a-z])", repl_important, text)
    text = re.sub(r"(?i)It is important to note that\s*", "", text)

    # Seamlessly integrates -> Integrates
    text = re.sub(r"(?i)Seamlessly integrates", "Integrates", text)
    text = re.sub(r"(?i)seamlessly integrates", "integrates", text)

    # Empowers users to -> Allows users to
    text = re.sub(r"(?i)Empowers users to", "Allows users to", text)
    text = re.sub(r"(?i)empowers users to", "allows users to", text)

    # In conclusion, -> remove
    def repl_conclusion(m):
        next_char = m.group(1)
        return next_char.upper()

    text = re.sub(r"(?i)In conclusion,\s+([a-z])", repl_conclusion, text)
    text = re.sub(r"(?i)In conclusion,\s*", "", text)

    # Replace em-dashes
    # usually surrounded by spaces: ` — ` -> ` - `
    text = text.replace(" — ", " - ")
    # sometimes not: `word—word` -> `word - word`
    text = text.replace("—", " - ")

    return text


for fpath in FILES:
    if os.path.exists(fpath):
        with open(fpath, "r") as f:
            content = f.read()
        new_content = clean_slop(content)
        if content != new_content:
            with open(fpath, "w") as f:
                f.write(new_content)
            print(f"Cleaned {fpath}")
    else:
        print(f"File not found: {fpath}")
