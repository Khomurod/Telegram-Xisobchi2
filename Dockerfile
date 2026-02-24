FROM python:3.12-slim

# System deps for audio conversion (OGG → WAV via ffmpeg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create data directory
RUN mkdir -p data temp

# Expose webhook port
EXPOSE 8000

# Environment defaults
ENV MODE=polling
ENV WEBHOOK_PATH=/webhook
ENV LOG_LEVEL=INFO

CMD ["python", "run.py"]
