FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on

WORKDIR /app

# Systemabhängigkeiten (inkl. curl für Healthchecks)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Non-Root-User anlegen (von HF Spaces verlangt)
RUN useradd -m -u 1000 user

# requirements zuerst kopieren (Caching), Owner direkt setzen
COPY --chown=user requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Projektordner kopieren, Owner direkt setzen
COPY --chown=user . .

# Datenverzeichnis anlegen, Owner setzen
RUN mkdir -p data && chown -R user:user data && chmod 755 data

# Ab hier als Non-Root-User weiterarbeiten
USER user

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=30s --start-period=10s --retries=3 \
CMD curl -f http://localhost:7860/api/simple-health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
