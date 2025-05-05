# Test Data Directory

This directory should contain small sample electrophysiology files used for testing.

## Required Test Files

To run all tests, please add the following files to this directory:

- `sample_axon.abf` - A small ABF file for testing Axon file format support
- Other sample files as needed for specific tests

## Guidelines for Test Data

1. Keep file sizes small (ideally under 100KB)
2. Use non-proprietary data if possible
3. Document the source of each file and ensure it's permissible to include in the repository
4. If files are too large for the repository, consider:
   - Creating synthetic test files programmatically
   - Using a separate data download script
   - Adding the files to .gitignore and documenting how to obtain them

## Generating Synthetic Test Files

For some cases, you can programmatically generate test files instead of using real recordings.
See the `tests/shared/test_data_generation.py` module for examples. 