FROM python:3.12-slim

# Set envs and workdir
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_HOME=/pywhichshay
WORKDIR $APP_HOME

# Get system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Add custom user
RUN groupadd -g 1000 pywhichshay && \
    useradd -u 1000 -g pywhichshay -s /usr/sbin/nologin -d $APP_HOME pywhichshay

# Copy application & install requirements
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt
COPY default_names.txt main.py
RUN chown -R pywhichshay:pywhichshay $APP_HOME

# Run application
USER pywhichshay
CMD ["python", "main.py"]
