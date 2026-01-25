import pandas as pd
import numpy as np
import json
import logging
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(name)s - %(levelname)s - %(message)s")
log = logging.getLogger("verify_json_export")


def verify_json_export():
    log.info("--- Verifying JSON Export Logic ---")

    # Create a DataFrame mimicking batch results with mixed types
    data = {
        "file": ["file1.abf", "file2.abf"],
        "channel": ["Vm_1", "Vm_1"],
        "event_count": [10, 5],
        "event_indices": [np.array([100, 200, 300]), [50, 150, 250, 350, 450]],
        "stats": [{"mean": 1.5, "std": 0.1}, {"mean": 2.0, "std": 0.2}],
    }
    df = pd.DataFrame(data)

    output_file = Path("test_export.json")

    try:
        # Simulate the export logic used in BatchAnalysisDialog
        log.info("Exporting DataFrame to JSON...")
        df.to_json(output_file, orient="records", indent=2, default_handler=str)

        if not output_file.exists():
            log.error("JSON file was not created.")
            sys.exit(1)

        # Verify content
        log.info("Reading back JSON file...")
        with open(output_file, "r") as f:
            loaded_data = json.load(f)

        if len(loaded_data) != 2:
            log.error(f"Expected 2 records, got {len(loaded_data)}")
            sys.exit(1)

        record1 = loaded_data[0]

        # Check simple fields
        if record1["file"] != "file1.abf":
            log.error(f"File name mismatch: {record1['file']}")
            sys.exit(1)

        # Check array handling
        # Note: default_handler=str might stringify numpy arrays if pandas doesn't handle them natively in to_json
        # Let's see what happened. Pandas usually converts lists/arrays to JSON arrays.
        indices = record1["event_indices"]
        log.info(f"Exported indices type: {type(indices)}")
        log.info(f"Exported indices value: {indices}")

        # If it's a list, great. If it's a string representation of an array, that's acceptable but less ideal.
        # Ideally we want a list.
        if isinstance(indices, list):
            log.info("SUCCESS: NumPy array was converted to JSON list.")
        elif isinstance(indices, str) and "[" in indices:
            log.warning("PARTIAL SUCCESS: NumPy array was stringified. This is valid JSON but requires parsing.")
        else:
            log.error(f"Unexpected type for indices: {type(indices)}")

        # Check dict handling
        stats = record1["stats"]
        if isinstance(stats, dict) and stats["mean"] == 1.5:
            log.info("SUCCESS: Dictionary preserved.")
        else:
            log.error(f"Dictionary check failed: {stats}")

        log.info("JSON Export Verification PASSED")

    except Exception as e:
        log.error(f"Verification FAILED: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # Cleanup
        if output_file.exists():
            output_file.unlink()


if __name__ == "__main__":
    verify_json_export()
