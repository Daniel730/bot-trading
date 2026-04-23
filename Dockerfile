# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build-time dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies into a virtualenv or just the user site to easily copy
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

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

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    curl \
    gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g @google/gemini-cli \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local

# Copy generated stubs
COPY --from=builder /app/src/generated /app/src/generated

# Copy the rest of the application code
COPY src/ /app/src/
COPY scripts/ /app/scripts/
COPY dashboard/ /app/dashboard/
COPY .env.template /app/.env.template
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Create Gemini CLI config directory and registry file
RUN mkdir -p /root/.gemini && echo '{"projects": {}}' > /root/.gemini/projects.json

# Default command to run the monitor via the entrypoint script
CMD ["/app/entrypoint.sh"]
