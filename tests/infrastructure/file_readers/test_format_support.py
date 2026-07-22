"""Declared acquisition-format support tiers."""

from synaptipy.infrastructure.file_readers.format_support import format_support


def test_abf_and_nwb_are_declared_validated_formats():
    """The two end-to-end validated reader paths are labelled accurately."""
    assert format_support(".abf").tier == "validated"
    assert format_support("NWB").tier == "validated"


def test_other_neo_formats_remain_experimental_until_validated():
    """A Neo mapping alone does not claim full Synaptipy support."""
    support = format_support("smr")
    assert support.tier == "experimental"
    assert "lacks Synaptipy end-to-end validation" in support.rationale
