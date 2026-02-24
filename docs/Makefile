# Minimal Makefile for Sphinx documentation
# Builds using the 'synaptipy' conda environment.
# Usage:
#   make html        – build HTML docs (default)
#   make clean       – remove build output
#   make livehtml    – auto-rebuild on file changes (requires sphinx-autobuild)

CONDA_ENV   = synaptipy
SPHINXBUILD = conda run -n $(CONDA_ENV) sphinx-build
SOURCEDIR   = .
BUILDDIR    = _build

.PHONY: help html clean livehtml Makefile

help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

html:
	@$(SPHINXBUILD) -b html "$(SOURCEDIR)" "$(BUILDDIR)/html" $(SPHINXOPTS) $(O)
	@echo
	@echo "Build finished. HTML pages are in $(BUILDDIR)/html."

clean:
	@rm -rf "$(BUILDDIR)"
	@echo "Build directory cleaned."

livehtml:
	@conda run -n $(CONDA_ENV) sphinx-autobuild \
		"$(SOURCEDIR)" "$(BUILDDIR)/html" \
		--watch ../src \
		$(SPHINXOPTS) $(O)

# Catch-all: pass any other targets straight to sphinx-build.
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
