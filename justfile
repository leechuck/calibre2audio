# kindle2audio task runner

# Install dependencies into a local venv (CUDA build of torch for the Blackwell GPU)
sync:
    uv sync

# Run the CLI, e.g. `just run generate --book "..." --from "..." -m 90`
run *ARGS:
    uv run kindle2audio {{ARGS}}

# List Calibre books matching a query
books QUERY:
    uv run kindle2audio books "{{QUERY}}"

# List available voices
voices:
    uv run kindle2audio voices

# Quick smoke test of the text pipeline without invoking TTS
selftest:
    uv run python -m kindle2audio._selftest
