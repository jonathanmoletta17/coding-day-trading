FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY slow_engine_v2.py .
COPY test_slow_engine_v2.py .
COPY slow_app_v2.py .
RUN python -m py_compile slow_engine_v2.py slow_app_v2.py test_slow_engine_v2.py
RUN python test_slow_engine_v2.py
RUN python -c "import slow_app_v2; print('BUILD_IMPORT_OK', slow_app_v2.app.title)"
CMD ["sh","-c","uvicorn slow_app_v2:app --host 0.0.0.0 --port ${PORT:-8080}"]
