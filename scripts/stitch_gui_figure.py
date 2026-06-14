from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import shutil

def main():
    repo_root = Path(__file__).resolve().parent.parent
    docs_dir = repo_root / "docs" / "tutorial" / "screenshots"
    out_dir = repo_root / "paper" / "results"
    
    # 1. Copy the overview image to paper/results
    overview_src = repo_root / "docs" / "_build" / "html" / "_images" / "synaptipy_overview.png"
    if overview_src.exists():
        shutil.copy(overview_src, out_dir / "synaptipy_overview.png")
    else:
        # Create a dummy image if it doesn't exist
        dummy = Image.new("RGB", (1280, 800), "lightgray")
        draw = ImageDraw.Draw(dummy)
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 60)
        except:
            font = ImageFont.load_default()
        draw.text((400, 350), "Overview Placeholder", fill="black", font=font)
        dummy.save(out_dir / "synaptipy_overview.png")
        
    img_a = Image.open(out_dir / "synaptipy_overview.png")
    img_b = Image.open(docs_dir / "explorer_tab.png")
    img_c = Image.open(docs_dir / "analyser_spike_analysis.png")
    img_d = Image.open(docs_dir / "exporter_tab.png")
    
    # Target width for the whole canvas
    target_width = 1600
    
    # 2x2 grid layout
    padding = 30
    panel_width = (target_width - padding) // 2
    
    # Resize all to panel_width
    def resize_img(img, width):
        ratio = width / img.width
        height = int(img.height * ratio)
        return img.resize((width, height), Image.Resampling.LANCZOS)
        
    img_a = resize_img(img_a, panel_width)
    img_b = resize_img(img_b, panel_width)
    img_c = resize_img(img_c, panel_width)
    img_d = resize_img(img_d, panel_width)
    
    row1_height = max(img_a.height, img_b.height)
    row2_height = max(img_c.height, img_d.height)
    
    # Margin for letters on the OUTSIDE
    top_margin = 80
    left_margin = 80
    bottom_margin = 20
    right_margin = 20
    
    canvas_width = left_margin + panel_width*2 + padding + right_margin
    canvas_height = top_margin + row1_height + padding + row2_height + bottom_margin
    
    canvas = Image.new("RGB", (canvas_width, canvas_height), "white")
    
    # Paste images
    # Row 1
    canvas.paste(img_a, (left_margin, top_margin))
    canvas.paste(img_b, (left_margin + panel_width + padding, top_margin))
    # Row 2
    canvas.paste(img_c, (left_margin, top_margin + row1_height + padding))
    canvas.paste(img_d, (left_margin + panel_width + padding, top_margin + row1_height + padding))
    
    # Draw letters OUTSIDE the images
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 72)
    except IOError:
        font = ImageFont.load_default()
        
    # Letters are offset to the top-left of each image block
    # y-coordinate is the TOP of the text. Font is 72pt, so we need at least 72px above the image!
    labels = [
        ("A", (10, top_margin - 75)),
        ("B", (left_margin + panel_width + padding - 60, top_margin - 75)),
        ("C", (10, top_margin + row1_height + padding - 75)),
        ("D", (left_margin + panel_width + padding - 60, top_margin + row1_height + padding - 75)),
    ]
    
    for text, (x, y) in labels:
        # Draw shadow
        draw.text((x, y), text, fill="black", font=font)
        
    final_path = out_dir / "gui_workflow.png"
    canvas.save(final_path)
    print(f"Stitched figure saved to {final_path}")

if __name__ == "__main__":
    main()
