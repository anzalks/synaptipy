import os
import tempfile

import icnsutil
from PIL import Image


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logo_path = os.path.join(base_dir, "src", "synaptipy", "resources", "icons", "logo.png")
    ico_path = os.path.join(base_dir, "src", "synaptipy", "resources", "icons", "logo.ico")
    icns_path = os.path.join(base_dir, "src", "synaptipy", "resources", "icons", "logo.icns")

    if not os.path.exists(logo_path):
        print(f"Logo not found at {logo_path}")
        return

    img = Image.open(logo_path).convert("RGBA")

    # Generate ICO (Windows) — multiple sizes in a single file.
    try:
        icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        img.save(ico_path, format="ICO", sizes=icon_sizes)
        print(f"Generated {ico_path}")
    except Exception as e:
        print(f"Error generating ICO: {e}")

    # Generate ICNS (macOS) — must include multiple canonical sizes so macOS
    # renders the icon correctly at every resolution and Dock zoom level.
    # The icnsutil key strings map to ICNS OSType codes:
    #   icp4=16, icp5=32, icp6=64, ic07=128, ic08=256, ic09=512, ic10=1024
    # Passing an invalid string as key (e.g. a filename) produces a silently
    # broken ICNS that macOS ignores.  Use explicit keys here.
    try:
        icns_sizes = {
            "icp4": 16,
            "icp5": 32,
            "icp6": 64,
            "ic07": 128,
            "ic08": 256,
            "ic09": 512,
            "ic10": 1024,
        }
        builder = icnsutil.IcnsFile()
        with tempfile.TemporaryDirectory() as tmpdir:
            for key, size in icns_sizes.items():
                resized = img.resize((size, size), Image.LANCZOS)
                tmp_path = os.path.join(tmpdir, f"icon_{size}.png")
                resized.save(tmp_path, format="PNG")
                try:
                    builder.add_media(key, file=tmp_path)
                except Exception as exc:
                    print(f"  Warning: could not add {key} ({size}x{size}): {exc}")
        builder.write(icns_path)
        print(f"Generated {icns_path}")
    except Exception as e:
        print(f"Error generating ICNS: {e}")


if __name__ == "__main__":
    main()
