FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml poetry.lock* ./

RUN pip install poetry && \
    poetry config virtualenvs.create false && \
    poetry install --no-root && \
    pip install "openai>=1.30.0"

# Install Playwright browsers (only needed for renderer service)
RUN playwright install chromium --with-deps || true

COPY . .

EXPOSE 8000
