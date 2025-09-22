FROM python:3.13-slim
WORKDIR /app
RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*
COPY services/bot/requirements.txt /app/requirements-bot.txt
RUN pip install --no-cache-dir -r /app/requirements-bot.txt
COPY app /app/app
COPY services/bot /app
# Install local app package so `import app` works
ENV PYTHONPATH=/app
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
