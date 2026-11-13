# ── WaitLess · Backend ─────────────────────────────────────────────
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 1) Dependencias (capa cacheable: solo se reconstruye si cambia requirements.txt)
COPY requirements.txt .
RUN pip install -r requirements.txt "bcrypt==4.0.1"

# 2) Código y fotos del menú
COPY . .

# 3) Usuario sin privilegios
RUN useradd --create-home --uid 1000 waitless && chown -R waitless:waitless /app
USER waitless

# Render entrega el puerto en $PORT; en local se usa 8000
ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','8000'), timeout=4)" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
