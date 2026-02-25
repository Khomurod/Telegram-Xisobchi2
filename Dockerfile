FROM python:3.12-slim

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

RUN mkdir -p data

# Expose webhook port
EXPOSE 8000

# Environment defaults
ENV MODE=webhook
ENV WEBHOOK_PATH=/webhook
ENV LOG_LEVEL=INFO
ENV TZ=Asia/Tashkent

CMD ["python", "run.py"]
