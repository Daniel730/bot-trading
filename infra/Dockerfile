# syntax=docker/dockerfile:1.6
# Stage 1: Builder
FROM ghcr.io/astral-sh/uv:python3.11-trixie AS builder

WORKDIR /app

# Install build-time dependencies. Use BuildKit apt caches so packages don't
# re-download on every rebuild.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl

# Install Python dependencies with a pip cache mount so wheels (numpy, pandas,
# scipy, grpcio, etc.) aren't recompiled every time unrelated files change.
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir --no-build-isolation --user -r requirements.txt

# Copy proto and generate gRPC stubs
COPY execution-engine/src/main/proto/ /app/proto/
RUN mkdir -p /app/src/generated && \
    python -m grpc_tools.protoc \
    -I /app/proto \
    --python_out=/app/src/generated \
    --grpc_python_out=/app/src/generated \
    /app/proto/execution.proto && \
    sed -i \
    's/^import execution_pb2 as execution__pb2/from src.generated import execution_pb2 as execution__pb2/' \
    /app/src/generated/execution_pb2_grpc.py

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV PATH="/root/.local/bin:${PATH}"

# Install runtime dependencies, Node.js 20, and Gemini CLI.
# Placed BEFORE any application code COPYs so this expensive layer stays cached
# across Python code changes. apt caches are BuildKit-mounted.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    --mount=type=cache,target=/root/.npm \
    apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    curl \
    gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @google/gemini-cli

# Copy installed Python packages from builder
COPY --from=builder /root/.local /root/.local

# Copy generated gRPC stubs
COPY --from=builder /app/src/generated /app/src/generated

# Copy the rest of the application code (this is the layer that invalidates
# most often; everything above is kept stable).
COPY src/ /app/src/
COPY scripts/ /app/scripts/
COPY legacy/dashboard/ /app/dashboard/
COPY .env.template /app/.env.template
COPY infra/entrypoint.sh /app/infra/entrypoint.sh
RUN chmod +x /app/infra/entrypoint.sh

# Create Gemini CLI config directory and data directory
RUN mkdir -p /root/.gemini /app/data && echo '{"projects": {}}' > /root/.gemini/projects.json

# Default command to run the monitor via the entrypoint script
CMD ["/app/infra/entrypoint.sh"]