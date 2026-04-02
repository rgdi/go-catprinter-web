# CAT Printer Web Interface Dockerfile
# Based on go-catprinter: https://git.boxo.cc/massivebox/go-catprinter
# License: MIT

FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    bluetooth \
    libbluetooth-dev \
    libglib2.0-dev \
    pkg-config \
    libmagic1 \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create necessary directories
RUN mkdir -p /app/catprinter /app/temp

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:5000/api/health || exit 1

# Run the application
CMD ["python", "app.py"]