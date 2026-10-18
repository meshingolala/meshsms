FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    telnet \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy project definition and files
COPY pyproject.toml README.md /app/
COPY meshsms /app/meshsms
COPY scripts /app/scripts

# Install dependencies using uv into system environment
RUN uv pip install --system --no-cache -e .

EXPOSE 8000

CMD ["python", "-m", "meshsms.cli", "run", "--host", "0.0.0.0", "--port", "8000"]
