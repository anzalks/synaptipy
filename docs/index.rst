.. Synaptipy documentation master file

Welcome to Synaptipy's Documentation
======================================

.. include:: ../README.md
   :parser: myst_parser.sphinx_
   :start-after: <!-- BADGES_START -->
   :end-before: <!-- BADGES_END -->

|

Synaptipy is a cross-platform electrophysiology visualization and analysis application.
The primary experimental focus is whole-cell patch-clamp and intracellular recordings; file I/O
is implemented via the `Neo <https://neo.readthedocs.io/en/latest/>`_ library, which supports
over 30 acquisition formats including extracellular and multi-channel data.

The software is implemented in Python using the Qt6 framework (PySide6). Signal visualization
employs PyQtGraph's CPU-vectorized native raster engine. The application includes 17 built-in analysis
modules spanning intrinsic membrane properties, action potential characterization, synaptic
event detection, and evoked responses (Evoked Sync, Paired-Pulse Ratio, Stimulus Train STP).
A batch processing engine implements composable analysis pipelines. An extensible plugin
interface permits integration of user-written analysis routines without modification to the
core package. Three example plugins are distributed with the application. File I/O is handled
via `Neo <https://neo.readthedocs.io/en/latest/>`_, supporting Axon ABF, WinWCP, CED/Spike2,
Intan, Igor Pro, NWB, Open Ephys, and additional formats. NWB 2.x export is provided via
`PyNWB <https://pynwb.readthedocs.io/en/stable/>`_.

The source code is hosted on `GitHub <https://github.com/anzalks/synaptipy>`_.

.. note::
   **Graphics Engine Architecture:** SynaptiPy's interactive workspace relies entirely on
   PyQtGraph's highly optimized, CPU-vectorized native raster engine for rendering
   high-density 2D electrophysiology traces. Matplotlib is utilized strictly for offline,
   high-resolution static figure exporting and validation reporting.

.. grid:: 2

   .. grid-item-card:: Tutorial
      :link: tutorial/index
      :link-type: doc

      Walkthrough of Explorer, Analyser, Batch Processing, and Exporter
      interfaces. Includes mathematical definitions for each analysis module.

   .. grid-item-card:: User Guide
      :link: user_guide
      :link-type: doc

      Installation procedures, supported file formats, and application
      interface description.

.. grid:: 2

   .. grid-item-card:: API Reference
      :link: api_reference
      :link-type: doc

      Public Python API for programmatic use.

   .. grid-item-card:: Developer Guide
      :link: developer_guide
      :link-type: doc

      Project structure, coding standards, testing, and contribution workflow.

.. grid:: 2

   .. grid-item-card:: Algorithmic Definitions
      :link: algorithmic_definitions
      :link-type: doc

      Mathematical definitions for all analysis metrics.

   .. grid-item-card:: NWB Export Mapping
      :link: nwb_mapping
      :link-type: doc

      Mapping of electrophysiology data to NWB 2.x containers, including
      electrode metadata and unit conventions.

.. grid:: 2

   .. grid-item-card:: Plugin Development
      :link: extending_synaptipy
      :link-type: doc

      Reference for custom analysis routines. Includes ``ui_params``,
      ``plots``, return-dict conventions, and example plugins.

   .. grid-item-card:: Scientific References
      :link: references
      :link-type: doc

      Full annotated bibliography — all algorithms, methods, and
      upstream libraries with verified DOIs.

   .. grid-item-card:: Source on GitHub
      :link: https://github.com/anzalks/synaptipy
      :link-type: url

      Browse the source code, open issues, or submit pull requests on GitHub.

   .. grid-item-card:: Changelog
      :link: https://github.com/anzalks/synaptipy/blob/main/CHANGELOG.md
      :link-type: url

      Release history and notable changes between versions.

----

.. toctree::
 :maxdepth: 2
 :caption: User Documentation
 :hidden:

 tutorial/index
 user_guide
 algorithmic_definitions
 references
 nwb_mapping
 extending_synaptipy
 reproducibility
 comparison_table
 api_reference

.. toctree::
 :maxdepth: 2
 :caption: Developer Documentation
 :hidden:

 developer_guide
 development/index

Indices and Tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
