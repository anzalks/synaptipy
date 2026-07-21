# Cross-Platform Installation and Development Setup

Synaptipy supports Windows, macOS, and Linux with Python 3.10–3.12. The
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

Windows installers (`.exe`), macOS disk images (`.dmg`), and Linux AppImages
(`.AppImage`) are published on the [GitHub Releases page](https://github.com/anzalks/synaptipy/releases).
Use the asset for your platform rather than relying on a hard-coded filename;
release filenames include the release version.

- **Windows:** run the downloaded installer and follow the setup wizard.
- **macOS:** open the disk image and drag Synaptipy to Applications. Because
  releases are not currently Apple-notarised, use Control-click → **Open** on
  the first launch if Gatekeeper blocks the app.
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
- **A plugin does not appear:** open Preferences and toggle **Enable Custom
  Plugins** off and on. A broken plugin is reported without preventing other
  plugins or the app from loading.
- **An offline manual is required:** installed application bundles include the
  packaged manual; open it through the app's Help menu.
