#!/bin/bash
set -euo pipefail

uv sync --frozen
uv run flask --app app db upgrade
