# Synaptipy

A multi-channel electrophysiology visualization and analysis toolkit built with Python, PySide6, and `neo`.

## Features

*   Load various electrophysiology file formats (ABF, NEX, Spike2, etc.) via the `neo` library.
*   Visualize multi-channel data with `pyqtgraph`.
*   Interactive plotting: Zoom, Pan, Reset View.
*   Optional downsampling for large datasets.
*   Plot individual trials or the average trace.
*   Load single files or navigate through files in a folder.
*   Export loaded recordings to NWB:N 2.0 format.

## Installation

1.  **Clone the repository (or download the code):**
    ```bash
    git clone https://github.com/anzalks/synaptipy/tree/main/Synaptipy.git # Replace with your repo URL
    cd Synaptipy
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
![image](https://github.com/user-attachments/assets/0798e5f1-0962-4d90-8182-0a7fe18062ef)
![image](https://github.com/user-attachments/assets/73cb6e19-4077-4f29-87bb-f50efee8f528)
![image](https://github.com/user-attachments/assets/3f3ebde9-6787-4a98-bda0-91e0a2a76cc7)
