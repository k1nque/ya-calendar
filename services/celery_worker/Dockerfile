FROM python:3.13-slim
WORKDIR /app
RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*
COPY services/celery_worker/requirements.txt /app/requirements-celery.txt
RUN pip install --no-cache-dir -r /app/requirements-celery.txt
COPY services/celery_worker /app
COPY app /app/app
ENV PYTHONPATH=/app
CMD ["celery", "-A", "tasks", "worker", "--loglevel=info"]
