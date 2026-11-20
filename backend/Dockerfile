FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    default-mysql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY backend/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Production Compose runs the API and worker as an unprivileged account.
RUN groupadd --system --gid 10001 kingflow \
    && useradd --system --uid 10001 --gid kingflow --no-create-home --shell /usr/sbin/nologin kingflow

# Copy application
COPY backend/ .
COPY frontend/ /frontend/

# Create logs directory
RUN mkdir -p logs /frontend/uploads \
    && chown -R 10001:10001 logs /frontend/uploads

# Expose port
EXPOSE 8000

# Run as the unprivileged application account by default.
USER 10001:10001

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
