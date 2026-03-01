.. Synaptipy documentation master file

Welcome to Synaptipy's Documentation
======================================

.. image:: https://img.shields.io/badge/source-GitHub-181717?logo=github&logoColor=white
   :target: https://github.com/anzalks/synaptipy
   :alt: GitHub repository

.. image:: https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white
   :target: https://www.python.org/
   :alt: Python 3.10+

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

.. image:: https://readthedocs.org/projects/synaptipy/badge/?version=latest
   :target: https://synaptipy.readthedocs.io/en/latest/
   :alt: Documentation Status

.. image:: https://img.shields.io/badge/code%20style-flake8-black
   :target: https://flake8.pycqa.org/
   :alt: Code style: flake8

.. image:: https://img.shields.io/badge/collaborators-welcome-brightgreen?logo=github&logoColor=white
   :target: https://github.com/anzalks/synaptipy
   :alt: Collaborators Welcome

.. image:: https://img.shields.io/github/v/release/anzalks/synaptipy?include_prereleases&label=release&color=orange
   :target: https://github.com/anzalks/synaptipy/releases
   :alt: Release

|

Synaptipy is a cross-platform, open-source electrophysiology visualisation and analysis suite.
The primary focus is whole-cell patch-clamp and intracellular recordings; however, any
electrophysiology signal whose file format is supported by the
`Neo <https://neo.readthedocs.io>`_ I/O library can be loaded, visualised, and processed
— including extracellular and multi-channel recordings.

Built on Python and Qt6, Synaptipy provides OpenGL-accelerated signal visualisation,
14 built-in analysis modules spanning intrinsic membrane properties, action potential
characterisation, synaptic event detection, and optogenetics, a composable batch processing
engine, and an extensible plugin interface that allows custom analysis routines to be
integrated without modifying the core package. File I/O is handled through
`Neo <https://neo.readthedocs.io>`_, supporting over 30 acquisition formats including
Axon ABF, WinWCP, CED/Spike2, Intan, Igor Pro, NWB, Open Ephys, and more.
NWB export is provided via `PyNWB <https://pynwb.readthedocs.io>`_.

The source code is hosted on `GitHub <https://github.com/anzalks/synaptipy>`_.
Collaborations, bug reports, and pull requests are welcome.

.. grid:: 2

   .. grid-item-card:: Quick-start Tutorial
      :link: tutorial/index
      :link-type: doc

      A full walkthrough of every feature — Explorer, Analyser, Batch
      Processing, and Exporter — with the maths behind each analysis module.

   .. grid-item-card:: User Guide
      :link: user_guide
      :link-type: doc

      Installation, supported file formats, and a detailed walkthrough of
      all three application tabs.

.. grid:: 2

   .. grid-item-card:: API Reference
      :link: api_reference
      :link-type: doc

      Public Python API for using Synaptipy as a library in your own scripts.

   .. grid-item-card:: Developer Guide
      :link: developer_guide
      :link-type: doc

      Project structure, coding standards, testing, and contribution workflow.

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
   extending_synaptipy
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
