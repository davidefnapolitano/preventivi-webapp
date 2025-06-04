# Dockerfile
FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive

# 1) Installa LibreOffice headless e le altre dipendenze di sistema
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      libreoffice-core \
      libreoffice-writer \
      libreoffice-calc \
      libreoffice-common \
      xz-utils \
      unzip \
      fontconfig \
      libglu1-mesa \
      libxrender1 \
      libxtst6 \
      libxi6 \
      libxrandr2 \
      libxfixes3 \
      libxdamage1 \
      libpango1.0-0 \
      libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 2) Imposta la working directory nel container
WORKDIR /app

# 3) Copia requirements e installa le dipendenze Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4) Copia tutto il codice Python e i template
COPY . .

# 5) Crea la cartella per i file temporanei (out/)
RUN mkdir -p /app/out

# 6) Espone la porta 5000 (usata da Gunicorn)
EXPOSE 5000

# 7) Imposta il comando di avvio di default (Gunicorn)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
