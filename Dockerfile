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
    libsqlite3-dev \
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

# Initialize the database (SQLite)
# Note: In production, you might want to mount a volume for the DB
RUN python scripts/init_db.py

# Expose any ports (MCP server might need one if used via HTTP, but FastMCP is usually stdio or SSE)
# For now, no specific port is required by the monitor.

# Create Gemini CLI config directory and registry file
RUN mkdir -p /root/.gemini && echo '{"projects": {}}' > /root/.gemini/projects.json

# Default command to run the monitor via the entrypoint script
CMD ["/app/entrypoint.sh"]
