FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY slow_engine_v2.py slow_store_v3.py slow_replay_v1.py slow_evidence_v1.py slow_app_v2.py slow_log_probe.py trend_v1.py proxy_app.py ./
COPY test_slow_engine_v2.py test_slow_cost_sensitivity_v1.py test_slow_evidence_v1.py test_slow_log_probe.py ./
RUN python -m py_compile slow_engine_v2.py slow_store_v3.py slow_replay_v1.py slow_evidence_v1.py slow_app_v2.py slow_log_probe.py trend_v1.py proxy_app.py
RUN python test_slow_engine_v2.py && python test_slow_cost_sensitivity_v1.py && python test_slow_evidence_v1.py && python test_slow_log_probe.py
RUN python -c "import slow_app_v2; print('BUILD_IMPORT_OK', slow_app_v2.app.title, slow_app_v2.STATE['storage'])"
CMD ["sh","-c","uvicorn slow_app_v2:app --host 0.0.0.0 --port ${PORT:-8080}"]
