# calibre2audio task runner

# Install dependencies into a local venv (CUDA build of torch for the Blackwell GPU)
sync:
    uv sync

# Run the CLI, e.g. `just run generate --book "..." --from "..." -m 90`
run *ARGS:
    uv run calibre2audio {{ARGS}}

# List Calibre books matching a query
books QUERY:
    uv run calibre2audio books "{{QUERY}}"

# List available voices
voices:
    uv run calibre2audio voices

# Quick smoke test of the text pipeline without invoking TTS
selftest:
    uv run python -m calibre2audio._selftest

# Install the CLI as a 'calibre2audio' command on PATH (needed by the plugin)
install-cli:
    uv tool install . --force

# Build the Calibre plugin zip into dist/
build-plugin:
    uv run python build_plugin.py

# Build and install the plugin into your local Calibre, then it's ready to use
install-plugin: build-plugin
    calibre-customize -a dist/calibre2audio-plugin.zip
