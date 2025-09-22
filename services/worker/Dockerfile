FROM python:3.13-slim
WORKDIR /app
RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*
COPY services/worker/requirements.txt /app/requirements-worker.txt
RUN pip install --no-cache-dir -r /app/requirements-worker.txt
COPY services/worker /app
COPY app /app/app
ENV PYTHONPATH=/app
CMD ["python", "main.py"]
