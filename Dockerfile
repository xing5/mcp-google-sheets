FROM alpine:latest AS base

WORKDIR /app
# Set environment variables for non-interactive installs and minimal locale
ENV LANG=C.UTF-8

# Update and install basic packages for a low resource machine
RUN apk update && \
    apk upgrade && \
    apk add --no-cache \
        bash \
        curl \
        tini \
        curl \
        coreutils \
        git

# Set tini as the init system to handle PID 1
ENTRYPOINT ["/sbin/tini", "--"]

RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Ensure uv is on PATH (installer places it in /root/.local/bin for root)
ENV PATH="/root/.local/bin:${PATH}"

COPY .python-version .

RUN uv venv

FROM base AS builder

COPY . .

# --locked fails the build when uv.lock is stale against pyproject.toml, so the image can only
# ever be built from a reviewed lockfile. --no-editable installs the project itself into the
# venv, which is what lets the runner ship without a source tree.
RUN uv sync --locked --no-dev --no-editable

FROM base AS runner

# Ship the venv, not a wheel: installing a built wheel with `uv pip` resolves its dependencies
# fresh from the wheel's own metadata and ignores uv.lock entirely, so every runtime dependency
# floats to whatever is newest at build time. `uv venv` in base is load-bearing — it puts the
# managed interpreter at the exact path this venv's symlinks and console-script shebangs
# resolve against.
COPY --from=builder /app/.venv /app/.venv

# Absolute path, not `uv run`: the runner carries no project for uv to discover.
CMD ["/app/.venv/bin/mcp-google-sheets", "--transport", "sse"]
