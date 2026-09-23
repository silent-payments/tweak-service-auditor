# Prefer venv python if available
PY := `if [ -x ".venv/bin/python" ]; then echo ".venv/bin/python"; else command -v python3; fi`

default:
    just --list

# Audit a single block
# Usage:
#   just block -d -o save.json 840000 # save detailed output
#   just block -v 840000      # INFO
#   just block -vv 840000     # DEBUG
#   ex. just block 840000
block *args:
    {{PY}} main.py block {{args}}

# Audit a range
# Usage:
#   just range -d 840000 840100
#   just range -vv 840000 840100 -d -o save.out
#   ex. just range 840000 840100
range *args:
    {{PY}} main.py range {{args}}

services *args:
    {{PY}} main.py config --list {{args}}

validate:
    {{PY}} main.py config --validate

# Probe Frigate using canary key reverse-derivation against BlindBit or explicit tweaks
# Usage:
#   just probe-frigate 850000 --index 0
#   just probe-frigate 850000 --sample 5
#   just probe-frigate 850000 --all
#   FRIGATE_ENDPOINT="127.0.0.1:57001" BLINDBIT_GRPC_ENDPOINT="127.0.0.1:51051" just probe-frigate 850000 --sample 5
probe-frigate *args:
    {{PY}} frigate_probe.py {{args}}

# Run tests (runs against service endpoints when configured via ENDPOINT env vars)
test *args:
    {{PY}} -m unittest discover tests {{args}}

# copy sample config to running config.json
make-config:
    cp sample.config.json config.json

# Create venv and install dependencies from requirements.txt if present
init:
    @if [ ! -d .venv ]; then python3 -m venv .venv; fi
    @. .venv/bin/activate && pip install -U pip
    @if [ -f requirements.txt ]; then \
        . .venv/bin/activate && pip install -r requirements.txt; \
    else \
        echo "No requirements.txt found. Skipping installs."; \
    fi
