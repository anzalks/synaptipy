import os
from PIL import Image
import icnsutil

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logo_path = os.path.join(base_dir, "src", "Synaptipy", "resources", "icons", "logo.png")
    ico_path = os.path.join(base_dir, "src", "Synaptipy", "resources", "icons", "logo.ico")
    icns_path = os.path.join(base_dir, "src", "Synaptipy", "resources", "icons", "logo.icns")

    if not os.path.exists(logo_path):
        print(f"Logo not found at {logo_path}")
        return

    # Generate ICO
    try:
        img = Image.open(logo_path)
        # Ensure image is square for ICO/ICNS by cropping to center or padding if needed. 
        # Usually logos are square.
        icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        img.save(ico_path, format="ICO", sizes=icon_sizes)
        print(f"Generated {ico_path}")
    except Exception as e:
        print(f"Error generating ICO: {e}")

    # Generate ICNS
    try:
        builder = icnsutil.IcnsFile()
        builder.add_media('icon_256x256.png', file=logo_path)
        builder.write(icns_path)
        print(f"Generated {icns_path}")
    except Exception as e:
        print(f"Error generating ICNS: {e}")

if __name__ == "__main__":
    main()
