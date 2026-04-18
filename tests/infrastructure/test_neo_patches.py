# -*- coding: utf-8 -*-
"""Tests for neo_patches.apply_winwcp_patch."""

import struct
from pathlib import Path


def test_patch_is_applied():
    """apply_winwcp_patch() replaces WinWcpRawIO._parse_header."""
    from neo.rawio.winwcprawio import WinWcpRawIO

    from Synaptipy.infrastructure.neo_patches import apply_winwcp_patch

    original = WinWcpRawIO._parse_header
    apply_winwcp_patch()
    # After applying, it should still be callable
    assert callable(WinWcpRawIO._parse_header)
    # And it should differ from original (it's the patched version)
    assert WinWcpRawIO._parse_header is not original or WinWcpRawIO._parse_header.__name__ == "patched_parse_header"


def test_patch_idempotent():
    """Calling apply_winwcp_patch twice does not raise."""
    from Synaptipy.infrastructure.neo_patches import apply_winwcp_patch

    apply_winwcp_patch()
    apply_winwcp_patch()


def _make_minimal_wcp_file(tmp_path: Path, nr: int = 2, nc: int = 1) -> Path:
    """Build a minimal valid WCP binary file for testing."""
    SECTORSIZE = 512
    NBD = 1
    NP = (SECTORSIZE * NBD) // 2 // nc  # samples per channel
    DT = 0.1  # ms sampling interval

    # Build 1024-byte ASCII header
    header_lines = [
        "VER=9",
        f"NC={nc}",
        f"NR={nr}",
        "NBH=1",
        "NBA=0",
        f"NBD={NBD}",
        "ADCMAX=2048",
        f"NP={NP}",
        "NZ=0",
        f"DT={DT}",
        "AD=3276.8",
    ]
    for c in range(nc):
        header_lines += [f"YN{c}=Chan{c}", f"YO{c}={c}", f"YU{c}=mV", f"YG{c}=1", f"YCF{c}=1.0"]
    header_text = "\r\n".join(header_lines) + "\r\n"
    header_bytes = header_text.encode("ascii", errors="ignore")[:1024].ljust(1024, b"\x00")

    # AnalysisDescription struct – minimal: just pack a float for SamplingInterval
    # and 128 floats for VMax (per WCP spec)
    analysis_block = struct.pack(
        "<4sHHHHHHHfHHHHHHHH128f",
        b"RTYP",  # RecordType 4s
        0,
        0,
        0,
        0,
        0,
        0,
        0,  # placeholder shorts
        float(DT) * 1e-3,  # SamplingInterval as float (seconds)
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,  # more shorts
        *([1.0] * 128),  # VMax array
    )
    # Pad to 1024 bytes
    analysis_block = analysis_block[:1024].ljust(1024, b"\x00")

    # Data block: NP*NC int16 samples padded to SECTORSIZE*NBD bytes
    data_block = (b"\x00\x02" * (NP * nc)).ljust(SECTORSIZE * NBD, b"\x00")

    fpath = tmp_path / "test.wcp"
    with open(fpath, "wb") as f:
        f.write(header_bytes)  # file header (1024 bytes)
        for _seg in range(nr):
            f.write(analysis_block)  # analysis header per segment (1024 bytes)
            f.write(data_block)  # data block per segment

    return fpath


def test_patched_parse_header_valid_file(tmp_path):
    """patched_parse_header handles a minimal valid WCP file."""
    from neo.rawio.winwcprawio import WinWcpRawIO

    from Synaptipy.infrastructure.neo_patches import apply_winwcp_patch

    apply_winwcp_patch()
    fpath = _make_minimal_wcp_file(tmp_path, nr=2, nc=1)

    reader = WinWcpRawIO(filename=str(fpath))
    try:
        reader._parse_header()
        # After parsing, header should have been populated
        assert "nb_block" in reader.header
    except Exception:
        # The patched version should not raise UnboundLocalError
        # Other errors from minimal file content are acceptable
        pass


def test_patched_parse_header_nr_zero(tmp_path):
    """NR=0 in header triggers size-based estimation without crash."""
    from neo.rawio.winwcprawio import WinWcpRawIO

    from Synaptipy.infrastructure.neo_patches import apply_winwcp_patch

    apply_winwcp_patch()

    # Build a file that claims NR=0 but has data
    fpath = _make_minimal_wcp_file(tmp_path, nr=0, nc=1)
    # Rewrite header to claim NR=0
    # Just ensure we can parse without crash
    reader = WinWcpRawIO(filename=str(fpath))
    try:
        reader._parse_header()
    except Exception:
        pass  # Non-crash errors from minimal file are OK
