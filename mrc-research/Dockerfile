FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py ./
CMD ["sh","-c","python -c \"import urllib.request as u; base='https://raw.githubusercontent.com/jonathanmoletta17/coding-day-trading/slow-trend-production-staging/mrc-cloud/'; [u.urlretrieve(base+f,f) for f in ('slow_engine_v2.py','test_slow_engine_v2.py','slow_app_v2.py')]\" && python test_slow_engine_v2.py && uvicorn slow_app_v2:app --host 0.0.0.0 --port ${PORT:-8080}"]
