# Synaptipy

A multi-channel electrophysiology visualization and analysis toolkit built with Python, PySide6, and `neo`.

## Features

*   Load various electrophysiology file formats (ABF, NEX, Spike2, etc.) via the `neo` library.
*   Visualize multi-channel data with `pyqtgraph`.
*   Interactive plotting: Zoom, Pan, Reset View.
*   Optional downsampling for large datasets.
*   Plot individual trials or the average trace.
*   Load single files or navigate through files in a folder.

## Installation

1.  **Clone the repository (or download the code):**
    ```bash
    git clone git clone https://github.com/anzalks/synaptipy.git
    cd PATH_TO/Synaptipy/
    ```
2.  **Create a virtual environment (Recommended):**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`
    ```
3.  **Install the package in editable mode:**
    ```bash
    pip install -e .
    ```
4.  **(Optional) Install development dependencies:**
    ```bash
    pip install -r requirements-dev.txt
    ```

## Usage

Run the GUI application from your terminal:

```bash
synaptipy-gui
```

## Screen grabs
![Screenshot 2025-04-07 at 12 55 35](https://github.com/user-attachments/assets/4c379633-59b2-4f8b-aa5f-db0ea24eed91)
![Screenshot 2025-04-07 at 12 56 11](https://github.com/user-attachments/assets/a1c35c20-f697-4a17-b1ea-62282b184c1d)
![Screenshot 2025-04-07 at 12 56 28](https://github.com/user-attachments/assets/1ff65828-8d09-4992-b7a7-b4fda0e8cdbc)
![Screenshot 2025-04-07 at 12 57 09](https://github.com/user-attachments/assets/03bf9064-e745-4913-a08d-39bb72d4d94e)
