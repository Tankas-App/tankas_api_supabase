FROM python:3.12-slim

WORKDIR /app

# Install system dependencies including OpenCV requirements
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libxcb1 \
    libx11-6 \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for Docker layer caching)
COPY requirements.txt .

# Install the CPU-only build of torch first, from PyTorch's CPU wheel index.
# The default PyPI wheel bundles CUDA and lands around 2.5GB; the CPU wheel is
# roughly 200MB. There is no GPU on Railway, so the CUDA payload is dead weight
# that slows builds and inflates memory. Doing it here means the torch==2.2.2
# pin in requirements.txt is already satisfied on the next step.
RUN pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    torch==2.2.2

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Ultralytics and matplotlib both want writable config dirs at import time.
ENV YOLO_CONFIG_DIR=/tmp/Ultralytics \
    MPLCONFIGDIR=/tmp/matplotlib \
    PYTHONUNBUFFERED=1

# Copy the rest of the app (includes yolov8s.pt, loaded by path at runtime)
COPY . .

# Expose port
EXPOSE 8000

# Start the app. Shell form so $PORT expands — Railway injects PORT at runtime,
# and the default keeps `docker run` working locally.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
