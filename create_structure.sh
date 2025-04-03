#!/bin/bash

# Create root directory
mkdir -p Synaptipy
cd Synaptipy || exit

# Create directory structure
mkdir -p .github/workflows
mkdir -p docs
mkdir -p examples/data
mkdir -p notebooks
mkdir -p scripts
mkdir -p src/Synaptipy/application/{cli,gui}
mkdir -p src/Synaptipy/core
mkdir -p src/Synaptipy/infrastructure/{exporters,file_readers}
mkdir -p src/Synaptipy/shared
mkdir -p tests/{application/gui,core,data,infrastructure/{exporters,file_readers},shared}

# Create files
# .github workflows
touch .github/workflows/{docs,release,test}.yml

# Documentation
touch docs/{api_reference,developer_guide,user_guide}.md

# Examples
touch examples/advanced_analysis.ipynb
touch examples/basic_usage.py
touch examples/data/sample_recording.abf

# Source files
# Main package
touch src/Synaptipy/{__init__,__main__}.py

# Application
touch src/Synaptipy/application/{__init__,__main__}.py
touch src/Synaptipy/application/cli/{__init__,main}.py
touch src/Synaptipy/application/gui/{__init__,main_window}.py

# Core
touch src/Synaptipy/core/{__init__,data_model,event_detector,signal_processor}.py

# Infrastructure
touch src/Synaptipy/infrastructure/__init__.py
touch src/Synaptipy/infrastructure/exporters/{__init__,csv_exporter,nwb_exporter}.py
touch src/Synaptipy/infrastructure/file_readers/{__init__,abf_reader,neo_adapter}.py

# Shared
touch src/Synaptipy/shared/{__init__,constants,error_handling}.py

# Tests
touch tests/{__init__,conftest}.py
touch tests/application/gui/test_main_window.py
touch tests/core/test_data_model.py
touch tests/infrastructure/exporters/test_nwb_exporter.py
touch tests/infrastructure/file_readers/test_neo_adapter.py
touch tests/shared/test_constants.py

# Root files
touch {.gitignore,CHANGELOG.md,LICENSE,README.md,pyproject.toml,requirements-dev.txt,requirements.txt}

echo "Directory structure created successfully!"
