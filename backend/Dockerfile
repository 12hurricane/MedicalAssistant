FROM python:3.11-slim

WORKDIR /app

# Set production environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root system user for security hardening
RUN useradd -m -u 1000 appuser

# Copy application source code
COPY . /app
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

EXPOSE 8000

# Container healthcheck — reads $PORT so it matches whatever port uvicorn
# is bound to (Railway injects PORT; locally it falls back to 8000).
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Start production ASGI server — Railway injects $PORT at runtime.
# Alembic migrations are intentionally NOT run here; they run in Railway's
# preDeployCommand (railway.toml) so a failed migration aborts the rollout
# before any traffic is shifted to the new instance.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2 --proxy-headers --forwarded-allow-ips=*"]
