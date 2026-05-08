FROM python:3.11-slim

LABEL maintainer="Anzal K Shahul <anzal.ks@gmail.com>"
LABEL description="Synaptipy: Reproducible electrophysiology analysis environment"

# System dependencies for Qt6 offscreen rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libegl1 \
    libxkbcommon0 \
    libdbus-1-3 \
    libfontconfig1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir ".[dev]"

# Default to offscreen rendering for headless environments
ENV QT_QPA_PLATFORM=offscreen

# Validation entry point
ENTRYPOINT ["python", "-m", "pytest"]
CMD ["validation/", "-v"]
