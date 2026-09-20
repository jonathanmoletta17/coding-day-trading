FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py ./
CMD ["sh","-c","python candidate_validate.py && python test_first_trade_postmortem.py && uvicorn lab_app:app --host 0.0.0.0 --port ${PORT:-8080}"]
