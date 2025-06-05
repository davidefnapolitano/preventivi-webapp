############################################
#  Dockerfile per la webapp che genera PDF #
############################################

# 1) Base image: Python slim
FROM python:3.10-slim

# 2) Abilitiamo “contrib non-free” aggiungendo direttamente le righe a sources.list
RUN \
  echo "deb http://deb.debian.org/debian bullseye main contrib non-free" >> /etc/apt/sources.list && \
  echo "deb http://security.debian.org/debian-security bullseye-security main contrib non-free" >> /etc/apt/sources.list

# 3) Aggiorna APT e installa LibreOffice + Core Fonts Microsoft + utilità (wget, unzip, fontconfig)
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

# 4) Scarica il file ZIP di Poppins da Google Fonts (ultima versione)
#    e lo estrai in /usr/share/fonts/truetype/poppins, quindi aggiorna fc-cache.
RUN mkdir -p /usr/share/fonts/truetype/poppins && \
    cd /usr/share/fonts/truetype/poppins && \
    wget -q https://github.com/google/fonts/raw/main/ofl/poppins/Poppins%5Bwght%5D.ttf -O Poppins-Regular.ttf && \
    wget -q https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Bold.ttf -O Poppins-Bold.ttf && \
    wget -q https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Italic.ttf -O Poppins-Italic.ttf && \
    # Altri stili se ti servono (Light, Medium, ecc.), es.:
    # wget -q https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Light.ttf -O Poppins-Light.ttf && \
    # wget -q https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Medium.ttf -O Poppins-Medium.ttf && \
    fc-cache -f -v && \
    cd /

# 5) Crea la cartella 'out' per i PDF temporanei
RUN mkdir -p /app/out

# 6) Imposta la working directory
WORKDIR /app

# 7) Copia requirements e installa dipendenze Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 8) Copia tutto il resto (app.py, templates/, templates_docx/, ecc.)
COPY . .

# 9) Espone la porta 5000 (adatta al binding di Gunicorn/Flask)
EXPOSE 5000

# 10) Avvia Gunicorn (prod)
CMD ["gunicorn", "-b", "0.0.0.0:5000", "app:app"]
