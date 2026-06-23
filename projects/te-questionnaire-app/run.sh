#!/bin/bash
# Launch ThousandEyes QA Automator (source / developer mode)
DIR="$(cd "$(dirname "$0")" && pwd)"

if [ ! -d "$DIR/.venv" ]; then
    echo "Setting up for the first time…"
    bash "$DIR/setup.sh"
fi

source "$DIR/.venv/bin/activate"
python "$DIR/launcher.py" "$@"
