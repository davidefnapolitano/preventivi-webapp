# --- Da qui inizia il tuo Dockerfile esistente ---

FROM python:3.10-slim

# (1) Installa i pacchetti necessari per LibreOffice headless e i font di Microsoft
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
       libreoffice-core libreoffice-common libreoffice-writer \
       fonts-liberation \
       fontconfig \
       wget \
       ca-certificates \
       unzip \
       sudo

# (2) Installa i pacchetti per ottenere i font Microsoft (Calibri, Consolas, Segoe UI, ecc.)
#     Useremo il “ttf-mscorefonts-installer” che scarica i Core Fonts di MS su Debian/Ubuntu
RUN apt-get install -y --no-install-recommends \
       ttf-mscorefonts-installer \
       fonts-dejavu-core fonts-dejavu-extra && \
    rm -rf /var/lib/apt/lists/*

# Al momento di installare ttf-mscorefonts-installer, ti verrà chiesto di accettare la EULA.
# Per far sì che l’instillatore non si blocchi in modalità “interactive”, imposteremo la policy:
RUN echo "ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula select true" | debconf-set-selections

# (3) Crea la cartella out
RUN mkdir -p /app/out

# (4) Imposta la working directory
WORKDIR /app

# (5) Copia requirements.txt e installa Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# (6) Copia il resto del codice (inclusi app.py, templates/, templates_docx/, ecc.)
COPY . .

# (7) Espone la porta (se serve)
EXPOSE 5000

# (8) Comando di avvio: Gunicorn
CMD ["gunicorn", "-b", "0.0.0.0:5000", "app:app"]

# --- Fine del Dockerfile ---
