# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g @google/gemini-cli \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY src/ /app/src/
COPY scripts/ /app/scripts/
COPY dashboard/ /app/dashboard/
COPY .env.template /app/.env.template
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Regenerate gRPC/protobuf stubs from the canonical proto so Python types
# always match the execution-engine without requiring manually committed stubs.
COPY execution-engine/src/main/proto/ /app/proto/
RUN python -m grpc_tools.protoc \
        -I /app/proto \
        --python_out=/app/src/generated \
        --grpc_python_out=/app/src/generated \
        /app/proto/execution.proto && \
    # grpc_tools emits a bare 'import execution_pb2' which fails when the
    # module lives inside a package; rewrite to the fully-qualified path.
    sed -i \
        's/^import execution_pb2 as execution__pb2/from src.generated import execution_pb2 as execution__pb2/' \
        /app/src/generated/execution_pb2_grpc.py

# Expose any ports
# (MCP server might need one if used via HTTP, but FastMCP is usually stdio or SSE)
# For now, no specific port is required by the monitor.

# Create Gemini CLI config directory and registry file
RUN mkdir -p /root/.gemini && echo '{"projects": {}}' > /root/.gemini/projects.json

# Default command to run the monitor via the entrypoint script
CMD ["/app/entrypoint.sh"]
