

FROM python:3.11-slim

ARG APP_ENV=production
ENV APP_ENV=${APP_ENV} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    LOG_LEVEL=INFO

WORKDIR /app

# --- dependencies (cached layer) ---------------------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- app code ------------------------------------------------------------
COPY agent.py .
COPY streamlit_app.py .
COPY tests/ ./tests/

# --- run as non-root -----------------------------------------------------
RUN groupadd -r appuser && useradd -r -g appuser appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8501

# --- healthcheck: confirm the Streamlit server is actually serving -------
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://localhost:8501/_stcore/health').status == 200 else sys.exit(1)"

ENTRYPOINT ["streamlit", "run", "streamlit_app.py", \
            "--server.port=8501", "--server.address=0.0.0.0"]