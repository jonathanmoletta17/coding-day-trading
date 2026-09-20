FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
COPY trend_v1.py .
COPY slow_v1.py .
COPY research_v1.py .
COPY combined_app.py .
COPY proxy_app.py .
RUN mkdir -p /data
ENV MRC_DB_PATH=/data/mrc_cloud.sqlite3
RUN python -m py_compile app.py trend_v1.py slow_v1.py research_v1.py combined_app.py proxy_app.py
RUN python -c "import proxy_app; print('BUILD_IMPORT_OK', proxy_app.app.title)"
CMD ["sh","-c","uvicorn proxy_app:app --host 0.0.0.0 --port ${PORT:-8080}"]
