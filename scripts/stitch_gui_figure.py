from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import shutil
import numpy as np

# Import unified plot formatting
from plot_utils import set_paper_styles, add_panel_label

def main():
    set_paper_styles()
    
    repo_root = Path(__file__).resolve().parent.parent
    docs_dir = repo_root / "docs" / "tutorial" / "screenshots"
    out_dir = repo_root / "paper" / "results"
    
    # 1. Ensure the overview image exists
    overview_src = repo_root / "docs" / "_build" / "html" / "_images" / "synaptipy_overview.png"
    if overview_src.exists():
        shutil.copy(overview_src, out_dir / "synaptipy_overview.png")
    else:
        # Create dummy image if needed
        dummy = np.ones((800, 1280, 3)) * 0.9 # Light gray
        plt.imsave(out_dir / "synaptipy_overview.png", dummy)
        
    img_a_path = out_dir / "synaptipy_overview.png"
    img_b_path = docs_dir / "explorer_tab.png"
    img_c_path = docs_dir / "analyser_spike_analysis.png"
    img_d_path = docs_dir / "exporter_tab.png"
    
    paths = [img_a_path, img_b_path, img_c_path, img_d_path]
    labels = ["A", "B", "C", "D"]
    
    # Load images
    images = []
    for p in paths:
        if p.exists():
            images.append(mpimg.imread(str(p)))
        else:
            # Fallback to empty gray if missing
            images.append(np.ones((800, 1280, 3)) * 0.9)
            
    # Create 2x2 grid using Matplotlib to ensure exact typography match
    # A standard 12x11 inch layout matches the validation plot size
    fig, axes = plt.subplots(2, 2, figsize=(12, 11))
    axes = axes.flatten()
    
    for i, ax in enumerate(axes):
        ax.imshow(images[i])
        ax.axis('off')  # Hide spines, ticks, and labels
        # Add standardized panel label!
        # x=-0.05 is used instead of -0.15 because images have no Y-axis tick labels
        add_panel_label(ax, labels[i], x=-0.05, y=1.05) 
        
    plt.tight_layout(w_pad=2.0, h_pad=2.0)
    
    final_path = out_dir / "gui_workflow.png"
    plt.savefig(final_path, dpi=300, bbox_inches='tight')
    plt.close(fig)
    print(f"Stitched figure saved to {final_path}")

if __name__ == "__main__":
    main()
