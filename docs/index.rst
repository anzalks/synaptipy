.. Synaptipy documentation master file

Welcome to Synaptipy's Documentation
======================================

.. image:: https://img.shields.io/badge/source-GitHub-181717?logo=github&logoColor=white
 :target: https://github.com/anzalks/synaptipy
 :alt: GitHub repository

.. image:: https://img.shields.io/badge/python-3.10--3.12-blue?logo=python&logoColor=white
 :target: https://www.python.org/
 :alt: Python 3.10-3.12

.. image:: https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey
 :target: https://github.com/anzalks/synaptipy
 :alt: Platform: Windows | macOS | Linux

.. image:: https://img.shields.io/badge/license-AGPL--3.0-blue
 :target: https://github.com/anzalks/synaptipy/blob/main/LICENSE
 :alt: License: AGPL-3.0

.. image:: https://github.com/anzalks/synaptipy/actions/workflows/test.yml/badge.svg?branch=main
 :target: https://github.com/anzalks/synaptipy/actions/workflows/test.yml
 :alt: CI status

.. image:: https://github.com/anzalks/synaptipy/actions/workflows/docs.yml/badge.svg?branch=main
 :target: https://github.com/anzalks/synaptipy/actions/workflows/docs.yml
 :alt: Docs build

.. image:: https://app.readthedocs.org/projects/synaptipy/badge/?version=latest
 :target: https://synaptipy.readthedocs.io/en/latest/
 :alt: Documentation Status

.. image:: https://img.shields.io/badge/code%20style-flake8-black
 :target: https://flake8.pycqa.org/en/latest/
 :alt: Code style: flake8

.. image:: https://img.shields.io/badge/collaborators-welcome-brightgreen?logo=github&logoColor=white
 :target: https://github.com/anzalks/synaptipy
 :alt: Collaborators Welcome

.. image:: https://img.shields.io/github/v/release/anzalks/synaptipy?include_prereleases&label=release&color=orange
 :target: https://github.com/anzalks/synaptipy/releases
 :alt: Release

|

Synaptipy is a cross-platform electrophysiology visualization and analysis application.
The primary experimental focus is whole-cell patch-clamp and intracellular recordings; file I/O
is implemented via the `Neo <https://neo.readthedocs.io/en/latest/>`_ library, which supports
over 30 acquisition formats including extracellular and multi-channel data.

The software is implemented in Python using the Qt6 framework (PySide6). Signal visualization
employs GPU-accelerated rendering via PyQtGraph. The application includes 17 built-in analysis
modules spanning intrinsic membrane properties, action potential characterization, synaptic
event detection, and evoked responses (Evoked Sync, Paired-Pulse Ratio, Stimulus Train STP).
A batch processing engine implements composable analysis pipelines. An extensible plugin
interface permits integration of user-written analysis routines without modification to the
core package. Three example plugins are distributed with the application. File I/O is handled
via `Neo <https://neo.readthedocs.io/en/latest/>`_, supporting Axon ABF, WinWCP, CED/Spike2,
Intan, Igor Pro, NWB, Open Ephys, and additional formats. NWB 2.x export is provided via
`PyNWB <https://pynwb.readthedocs.io/en/stable/>`_.

The source code is hosted on `GitHub <https://github.com/anzalks/synaptipy>`_.

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

.. grid:: 2

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
 decisions/index
 manuals/index

.. toctree::
 :maxdepth: 1
 :caption: Development Logs
 :hidden:

 development_logs/index

Indices and Tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
