FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml .
# COPY uv.lock . # Uncomment if uv.lock exists

# Install dependencies
RUN uv sync --frozen --no-install-project || uv sync --no-install-project

# Copy source code
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Entrypoint
ENTRYPOINT ["uv", "run", "python", "-m", "rss.main", "--mode", "discord"]
