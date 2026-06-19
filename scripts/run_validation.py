#!/usr/bin/env python3
"""
SynaptiPy Allen SDK headless validation pipeline.

Validates BatchAnalysisEngine against Allen Cell Types Database ground-truth
features (IPFX) for N mouse cortical cells.

Usage:
    pip install -r paper/requirements_paper.txt
    python paper/run_validation.py [--n 20] [--out paper/validation_results.csv]

Output:
    paper/validation_results.csv        — wide-format per-cell results
    paper/validation_results_tidy.csv   — long-format for R/seaborn
    paper/validation_results_provenance.json — full parameter record
    paper/allen_cache/                  — downloaded NWB files (cached)
"""

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Fix for xarray/allensdk with NumPy 2.0+
if not hasattr(np, 'unicode_'):
    np.unicode_ = np.str_
if not hasattr(np, 'VisibleDeprecationWarning'):
    np.VisibleDeprecationWarning = UserWarning

# --- repo path setup ---
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

CACHE_DIR = REPO / "paper" / "allen_cache"
OUT_CSV   = REPO / "paper" / "validation_results.csv"
TARGET_N  = 1

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Allen helpers ────────────────────────────────────────────────────────────

def get_long_square_sweeps(ephys_data):
    """Return sweep numbers whose stimulus type contains 'Long Square'."""
    out = []
    for sn in ephys_data.get_sweep_numbers():
        meta = ephys_data.get_sweep_metadata(sn)
        if "Long Square" in meta.get("stimulus_name", ""):
            out.append(sn)
    return out


def run_ipfx_on_sweep(ephys_data, sweep_number):
    """Extract AP features via IPFX for one sweep. Returns dict or None."""
    try:
        from ipfx.feature_extractor import SpikeFeatureExtractor
        sweep = ephys_data.get_sweep(sweep_number)
        v   = sweep["response"] * 1e3           # V → mV
        i   = sweep["stimulus"] * 1e12          # A → pA
        t   = np.arange(len(v)) / sweep["sampling_rate"]
        ext = SpikeFeatureExtractor(filter=9.9, dv_cutoff=20.0)
        spk = ext.process(t, v, i)
        if spk.empty:
            return None
        return {
            "ipfx_peak_mV": float(spk["peak_v"].mean()),
            "ipfx_thr_mV":  float(spk["threshold_v"].mean()),
            "ipfx_amp_mV":  float(
                (spk["peak_v"] - spk["threshold_v"]).mean()
            ),
            "ipfx_n_spikes": len(spk),
        }
    except Exception as exc:
        log.debug("IPFX sweep %s failed: %s", sweep_number, exc)
        return None


# ── SynaptiPy headless helpers ───────────────────────────────────────────────

def run_synaptipy_on_nwb(nwb_path: Path, out_csv: Path) -> dict | None:
    """
    Load an NWB file via NeoAdapter, run BatchAnalysisEngine headlessly,
    save results to CSV via CSVExporter, and return the first row as a dict.

    Returns None if no spikes found or any step fails.
    """
    try:
        from Synaptipy.infrastructure.file_readers.neo_adapter import NeoAdapter
        from Synaptipy.core.analysis.batch_engine import BatchAnalysisEngine
        from Synaptipy.infrastructure.exporters.csv_exporter import CSVExporter

        # 1. Load recording
        adapter   = NeoAdapter()
        recording = adapter.load(str(nwb_path))

        # 2. Define pipeline — use exact registered analysis names
        pipeline = [
            {
                "analysis": "spike_detection",
                "scope":    "all_trials",
                "params":   {"dvdt_threshold": 20.0, "refractory_ms": 2.0},
            },
            {
                "analysis": "spike_analysis",
                "scope":    "all_trials",
                "params":   {},
            },
            {
                "analysis": "rmp_analysis",
                "scope":    "average",
                "params":   {"baseline_start": 0.0, "baseline_end": 0.1},
            },
        ]

        # 3. Run batch — returns pd.DataFrame
        engine     = BatchAnalysisEngine()
        results_df = engine.run_batch([recording], pipeline)

        if results_df.empty:
            log.debug("SynaptiPy: empty results for %s", nwb_path.name)
            return None

        # 4. Save to CSV headlessly via CSVExporter
        exporter = CSVExporter()
        rows     = results_df.to_dict("records")

        # Wide-format CSV (one row per file)
        exporter.export_analysis_results(
            results=rows,
            output_path=out_csv,
            analysis_config={"pipeline": pipeline, "source": str(nwb_path)},
        )

        # Tidy long-format CSV alongside it
        tidy_path = out_csv.with_name(out_csv.stem + "_tidy.csv")
        exporter.export_tidy(
            results=rows,
            output_path=tidy_path,
            analysis_config={"pipeline": pipeline},
        )

        # 5. Extract scalar metrics from first row for comparison table
        row = rows[0]
        return {
            "syn_peak_mV":   row.get("peak_voltage_mean")
                             or row.get("ap_peak_voltage_mean"),
            "syn_thr_mV":    row.get("threshold_mean")
                             or row.get("ap_threshold_mean"),
            "syn_amp_mV":    row.get("amplitude_mean")
                             or row.get("ap_amplitude_mean"),
            "syn_n_spikes":  row.get("spike_count") or row.get("n_spikes"),
        }

    except Exception as exc:
        log.debug("SynaptiPy failed on %s: %s", nwb_path.name, exc)
        return None


# ── Main pipeline ─────────────────────────────────────────────────────────────

def main(target_n: int = TARGET_N, out_csv: Path = OUT_CSV):
    from allensdk.core.cell_types_cache import CellTypesCache

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    log.info("Querying Allen Cell Types Database (Mus musculus, cortex)...")
    ctc   = CellTypesCache(manifest_file=str(CACHE_DIR / "manifest.json"))
    cells = ctc.get_cells(
        species=["Mus musculus"],
        require_reconstruction=False,
        require_morphology=False,
    )
    log.info("Found %d candidate cells. Target: %d with spikes.", len(cells), target_n)

    rows      = []
    attempted = 0

    for cell in cells:
        if len(rows) >= target_n:
            break

        cell_id   = cell["id"]
        structure = (cell.get("structure") or {}).get("acronym", "unknown")
        attempted += 1
        log.info("[%d/%d] Cell %s (%s) ...", len(rows) + 1, target_n, cell_id, structure)

        try:
            # Download NWB + pre-computed features
            nwb_path      = CACHE_DIR / f"cell_{cell_id}.nwb"
            ephys_data    = ctc.get_ephys_data(cell_id, file_name=str(nwb_path))

            # Find Long Square sweeps
            sweeps = get_long_square_sweeps(ephys_data)
            if not sweeps:
                log.info("  Skipped — no Long Square sweeps")
                continue

            # Run IPFX on first sweep that yields spikes
            ipfx_res = None
            for sn in sweeps:
                ipfx_res = run_ipfx_on_sweep(ephys_data, sn)
                if ipfx_res:
                    break
            if not ipfx_res:
                log.info("  Skipped — IPFX found no spikes")
                continue

            # Run SynaptiPy headlessly, save per-cell CSV to allen_cache
            cell_csv  = CACHE_DIR / f"cell_{cell_id}_results.csv"
            syn_res   = run_synaptipy_on_nwb(nwb_path, cell_csv)
            if not syn_res:
                log.info("  Skipped — SynaptiPy found no spikes")
                continue

            row = {
                "cell_id":      cell_id,
                "structure":    structure,
                **syn_res,
                **ipfx_res,
                "bias_peak_mV": (syn_res.get("syn_peak_mV") or 0)
                                 - ipfx_res["ipfx_peak_mV"],
                "bias_thr_mV":  (syn_res.get("syn_thr_mV") or 0)
                                 - ipfx_res["ipfx_thr_mV"],
                "bias_amp_mV":  (syn_res.get("syn_amp_mV") or 0)
                                 - ipfx_res["ipfx_amp_mV"],
            }
            rows.append(row)
            log.info(
                "  OK — peak bias %+.2f mV, thr bias %+.2f mV, amp bias %+.2f mV",
                row["bias_peak_mV"], row["bias_thr_mV"], row["bias_amp_mV"],
            )

        except Exception as exc:
            log.warning("  Cell %s failed — %s", cell_id, exc)
            continue

    # ── Aggregate and save ────────────────────────────────────────────────────
    if not rows:
        log.error("No cells processed. Check Allen SDK connectivity and IPFX installation.")
        sys.exit(1)

    df = pd.DataFrame(rows)

    # Final wide-format CSV for the paper
    from Synaptipy.infrastructure.exporters.csv_exporter import CSVExporter
    exporter = CSVExporter()
    exporter.export_analysis_results(
        results=df.to_dict("records"),
        output_path=out_csv,
        analysis_config={"target_n": target_n, "species": "Mus musculus"},
    )

    # Tidy format alongside it
    tidy_out = out_csv.with_name(out_csv.stem + "_tidy.csv")
    exporter.export_tidy(
        results=df.to_dict("records"),
        output_path=tidy_out,
    )

    log.info("=" * 60)
    log.info("Completed: %d cells processed (%d attempted)", len(rows), attempted)
    log.info("Results → %s", out_csv)
    log.info("Tidy    → %s", tidy_out)
    log.info("=" * 60)
    log.info("Summary (mean ± SD across %d cells):", len(rows))
    for col in ["bias_peak_mV", "bias_thr_mV", "bias_amp_mV"]:
        vals = df[col].dropna()
        log.info("  %-22s %+.3f ± %.3f mV  (n=%d)", col, vals.mean(), vals.std(), len(vals))

    # Print table for copy-paste into paper
    print("\n--- Copy into paper (fill [ACTUAL_N] with actual value) ---")
    print(f"n={len(rows)} cells, peak bias {df['bias_peak_mV'].mean():+.2f}±{df['bias_peak_mV'].std():.2f} mV, "
          f"threshold bias {df['bias_thr_mV'].mean():+.2f}±{df['bias_thr_mV'].std():.2f} mV")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SynaptiPy Allen SDK validation")
    parser.add_argument("--n",   type=int,  default=TARGET_N, help="Target cell count")
    parser.add_argument("--out", type=Path, default=OUT_CSV,  help="Output CSV path")
    args = parser.parse_args()
    main(target_n=args.n, out_csv=args.out)
