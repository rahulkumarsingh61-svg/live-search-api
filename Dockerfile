FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libgtk-3-0 \
    libdbus-glib-1-2 \
    libxt6 \
    libasound2 \
    libx11-xcb1 \
    libnss3 \
    libxss1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN git clone --depth 1 https://github.com/rahulkumarsingh61-svg/google-scraper.git

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r google-scraper/requirements.txt && \
    pip install --no-cache-dir -r requirements.txt && \
    python -m camoufox fetch

COPY app.py .

ENV PORT=10000
EXPOSE 10000

CMD ["python", "app.py"]
