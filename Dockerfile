# Interface web (Streamlit) com backend OpenAI: não precisa de GPU.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    MAIDAI_BACKEND=openai

WORKDIR /app

COPY requirements-api.txt .
RUN pip install -r requirements-api.txt

COPY .streamlit/ .streamlit/
COPY src/ src/

# jobs/ guarda as evidências enviadas e as saídas de cada análise (volume no compose)
RUN useradd --create-home --uid 1000 app && mkdir -p jobs && chown app jobs
USER app

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health')"

CMD ["streamlit", "run", "src/demo/app_web.py", "--server.address", "0.0.0.0", "--server.port", "8501"]
