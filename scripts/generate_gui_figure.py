import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

def main():
    repo_root = Path(__file__).resolve().parent.parent
    screenshots_dir = repo_root / "docs" / "tutorial" / "screenshots"
    out_path = repo_root / "paper" / "results" / "gui_workflow.png"

    # Define the panel images
    img_a_path = screenshots_dir / "explorer_tab_multichannel.png"
    img_b_path = screenshots_dir / "analyser_spike_analysis_phase_plane.png"
    img_c_path = screenshots_dir / "exporter_tab.png"

    for path in [img_a_path, img_b_path, img_c_path]:
        if not path.exists():
            print(f"Missing screenshot: {path}")
            return

    img_a = Image.open(img_a_path)
    img_b = Image.open(img_b_path)
    img_c = Image.open(img_c_path)

    # We want a 2-column, 2-row layout or just a vertical stack.
    # Given standard page width, vertical stacking or a 2x2 grid is best.
    # Let's do:
    # A (full width top)
    # B (bottom left) | C (bottom right)
    
    # Calculate dimensions
    # Resize A to width = 1600
    target_width = 1600
    a_ratio = target_width / img_a.width
    a_height = int(img_a.height * a_ratio)
    img_a = img_a.resize((target_width, a_height), Image.Resampling.LANCZOS)

    # Resize B and C to width = target_width // 2 - padding
    padding = 20
    bottom_width = (target_width - padding) // 2
    
    b_ratio = bottom_width / img_b.width
    b_height = int(img_b.height * b_ratio)
    img_b = img_b.resize((bottom_width, b_height), Image.Resampling.LANCZOS)

    c_ratio = bottom_width / img_c.width
    c_height = int(img_c.height * c_ratio)
    img_c = img_c.resize((bottom_width, c_height), Image.Resampling.LANCZOS)

    # Canvas height = A_height + padding + max(B_height, C_height)
    canvas_height = a_height + padding + max(b_height, c_height)

    # Create white canvas
    canvas = Image.new("RGB", (target_width, canvas_height), "white")

    # Paste A
    canvas.paste(img_a, (0, 0))
    # Paste B
    canvas.paste(img_b, (0, a_height + padding))
    # Paste C
    canvas.paste(img_c, (bottom_width + padding, a_height + padding))

    # Add eNeuro Panel Labels (A, B, C)
    draw = ImageDraw.Draw(canvas)
    
    # Attempt to load a generic sans-serif font
    try:
        # On macOS, Arial bold is usually here:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 60)
    except IOError:
        font = ImageFont.load_default()

    # Draw bold letters with a slight white shadow for visibility
    labels = [
        ("A", (20, 20)),
        ("B", (20, a_height + padding + 20)),
        ("C", (bottom_width + padding + 20, a_height + padding + 20)),
    ]

    for text, (x, y) in labels:
        # shadow/outline
        draw.text((x-2, y-2), text, fill="white", font=font)
        draw.text((x+2, y+2), text, fill="white", font=font)
        # main text
        draw.text((x, y), text, fill="black", font=font)

    canvas.save(out_path)
    print(f"Composite GUI workflow figure saved to {out_path}")

if __name__ == "__main__":
    main()
