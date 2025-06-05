FROM python:3.10-slim

# --------------------------------------------------
# 1. Aggiungo “contrib” e “non-free” a /etc/apt/sources.list
# --------------------------------------------------
RUN sed -i 's/debian\.org\/debian bullseye main/debian.org\/debian bullseye main contrib non-free/' /etc/apt/sources.list && \
    sed -i 's/debian\.org\/debian-security bullseye-security main/debian.org\/debian-security bullseye-security main contrib non-free/' /etc/apt/sources.list

# --------------------------------------------------
# 2. Aggiorna APT e installa LibreOffice + font Microsoft
# --------------------------------------------------
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        fontconfig \
        fonts-dejavu-core \
        fonts-dejavu-extra \
        ttf-mscorefonts-installer \
        libreoffice-core \
        libreoffice-common \
        libreoffice-writer \
        wget \
        ca-certificates \
        unzip \
        sudo && \
    rm -rf /var/lib/apt/lists/*

# Nota: 'ttf-mscorefonts-installer' appartiene alla sezione 'contrib non-free',
#       per questo abbiamo modificato sources.list sopra.

# --------------------------------------------------
# 3. Crea la cartella 'out' per i PDF temporanei
# --------------------------------------------------
RUN mkdir -p /app/out

# --------------------------------------------------
# 4. Imposta la working directory
# --------------------------------------------------
WORKDIR /app

# --------------------------------------------------
# 5. Copia requirements e installa dipendenze Python
# --------------------------------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --------------------------------------------------
# 6. Copia tutto il resto (app.py, templates, ecc.)
# --------------------------------------------------
COPY . .

# --------------------------------------------------
# 7. Espone la porta 5000 (se usi Gunicorn/Flask)
# --------------------------------------------------
EXPOSE 5000

# --------------------------------------------------
# 8. Avvia Gunicorn
# --------------------------------------------------
CMD ["gunicorn", "-b", "0.0.0.0:5000", "app:app"]
