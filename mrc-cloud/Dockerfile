FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
COPY trend_v1.py .
RUN mkdir -p /data
ENV MRC_DB_PATH=/data/mrc_cloud.sqlite3
CMD ["sh","-c","uvicorn trend_v1:app --host 0.0.0.0 --port ${PORT:-8080}"]
