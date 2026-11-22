# Cross-Platform Installation and Development Setup

Synaptipy supports Windows, macOS, and Linux with Python 3.10-3.12. The
published package is the normal installation path; Conda is recommended for
development and for the repository's reproducible validation environment.

## Install the application with pip

```bash
python -m pip install --upgrade pip
python -m pip install synaptipy
synaptipy
```

This installs the application and its required runtime dependencies, including
the project-pinned `PySide6==6.7.3`. Do not substitute a newer PySide6 release:
the pin protects against known Qt/PyQtGraph crashes and is part of the tested
application configuration.

## Use a standalone application bundle

Windows installers (`.exe`), macOS disk images (`.dmg` for both `arm64` Apple
Silicon and `x86_64` Intel architectures), and Linux AppImages (`.AppImage`)
are published on the
[GitHub Releases page](https://github.com/anzalks/synaptipy/releases).
Select the asset matching your operating system and processor architecture;
release filenames include the release version and architecture suffix.

- **Windows:** run the downloaded `Synaptipy_Setup_*.exe` installer and follow
  the setup wizard.
- **macOS:** download `Synaptipy_*_macOS_arm64.dmg` on Apple Silicon Macs (M1
  and newer) or `Synaptipy_*_macOS_x86_64.dmg` on Intel Macs, open the disk
  image, and drag `Synaptipy.app` to `Applications`. Because releases use
  ad-hoc signatures without Apple Developer ID notarization, approve the first
  launch in **System Settings -> Privacy & Security -> Open Anyway** or clear
  the download quarantine attribute in Terminal:

  ```bash
  xattr -dr com.apple.quarantine /Applications/Synaptipy.app
  ```

- **Linux:** make the AppImage executable, then run it:

  ```bash
  chmod +x Synaptipy-*.AppImage
  ./Synaptipy-*.AppImage
  ```

  Some distributions require `libfuse2` to launch AppImages.

## Development environment

The repository provides the `synaptipy` Conda environment. Recreate it only
when required; otherwise use the existing environment:

```bash
conda env create -f environment.yml   # first-time setup only
conda activate synaptipy
python -m pip install -e ".[dev]"
```

Run development checks from that environment:

```bash
conda run -n synaptipy python scripts/verify_ci.py
```

The GitHub Actions matrix is the authority for platform compatibility. It
tests Ubuntu, Windows, and macOS on Python 3.10, 3.11, and 3.12, while the
release workflow also validates the package built for publication.

## Common issues

- **The app does not start after changing dependencies:** reinstall the
  supported package configuration rather than changing the PySide6 pin.
- **macOS blocks an unnotarized `.dmg` bundle after dragging to Applications:**
  verify that the downloaded `.dmg` matches your Mac architecture (`arm64` vs
  `x86_64`) and run `xattr -dr com.apple.quarantine /Applications/Synaptipy.app`
  if Gatekeeper retains quarantine flags on nested frameworks. Startup logs are
  written to `~/.synaptipy/logs/boot.log` and `~/.synaptipy/logs/app.log`.
- **A plugin does not appear:** open Preferences and toggle **Enable Custom
  Plugins** off and on. A broken plugin is reported without preventing other
  plugins or the app from loading.
- **An offline manual is required:** installed application bundles include the
  packaged manual; open it through the app's Help menu.
