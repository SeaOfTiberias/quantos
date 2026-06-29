FROM python:3.11-slim

# Non-root user for security
RUN useradd -m -u 1000 quantos
WORKDIR /app

# Install dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Switch to non-root
RUN chown -R quantos:quantos /app
USER quantos

# Expose port (Railway sets $PORT dynamically)
EXPOSE 8000

# Health check — Railway will restart if this fails
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "cloud.api.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--log-level", "info"]
