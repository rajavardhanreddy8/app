FROM python:3.11-slim

# Install system dependencies for RDKit and other chemistry tools
RUN apt-get update && apt-get install -y \
    curl \
    libxrender1 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install -r requirements.txt --no-cache-dir

# Copy the rest of the application
COPY . .

# Set PYTHONPATH to include the backend directory
ENV PYTHONPATH=/app

# Expose the port
EXPOSE 8000

# Command to run the application
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
