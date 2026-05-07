"""Centralised runtime configuration for ADAW.

All Google Cloud settings are read from environment variables. The application
will fail fast at import time if required variables are missing rather than
silently using a hard-coded fallback that could route to the wrong project.

Set variables in a .env file at the project root (see .env.example), or export
them in the shell before starting the server.

Required:
    GCP_PROJECT   — Google Cloud project ID that has the Vertex AI API enabled.

Optional:
    GCP_LOCATION  — Vertex AI regional endpoint (default: us-central1).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root regardless of the working directory.
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

GCP_PROJECT: str = os.getenv("GCP_PROJECT", "")
GCP_LOCATION: str = os.getenv("GCP_LOCATION", "us-central1")

if not GCP_PROJECT:
    raise ValueError(
        "GCP_PROJECT environment variable is not set.\n"
        "Copy .env.example to .env and set GCP_PROJECT to your Google Cloud project ID.\n"
        "Alternatively, export it in your shell: export GCP_PROJECT=your-project-id"
    )
