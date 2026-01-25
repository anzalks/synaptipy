import logging
from pathlib import Path
from Synaptipy.infrastructure.file_readers.neo_adapter import NeoAdapter

# Setup logging
logging.basicConfig(level=logging.DEBUG)


def test_dot_filenames():
    adapter = NeoAdapter()

    # Simulate a file with multiple dots
    complex_name = Path("test.data.1.wcp")
    simple_name = Path("test.wcp")

    # Test IO resolution
    try:
        io_class = adapter._get_neo_io_class(complex_name)
        print(f"Success for {complex_name}: Found {io_class.__name__}")
    except Exception as e:
        print(f"Failed for {complex_name}: {e}")

    try:
        io_class = adapter._get_neo_io_class(simple_name)
        print(f"Success for {simple_name}: Found {io_class.__name__}")
    except Exception as e:
        print(f"Failed for {simple_name}: {e}")

    # Test logic for suffix matching (similar to main window)
    selected_file = complex_name
    print(f"Suffix for {selected_file}: {selected_file.suffix}")

    # Simulate what glob would do (string matching)
    glob_pattern = f"*{selected_file.suffix}"
    print(f"Glob pattern: {glob_pattern}")


if __name__ == "__main__":
    # Create dummy files to test is_file() check in adapter
    Path("test.data.1.wcp").touch()
    Path("test.wcp").touch()

    try:
        test_dot_filenames()
    finally:
        # Cleanup
        Path("test.data.1.wcp").unlink()
        Path("test.wcp").unlink()
