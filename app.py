#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import uuid
import subprocess
import io
import traceback
import random
import string
import json
import base64

from datetime import datetime

from flask import (
    Flask,
    render_template,
    request,
    send_file,
    flash,
    redirect,
    url_for,
    jsonify,
    session,
)
from docxtpl import DocxTemplate
import gspread
from google.oauth2.service_account import Credentials
import requests

# ------------------------------------------------------------
# CONFIGURAZIONE FOLDER E TEMPLATE
# ------------------------------------------------------------

app = Flask(__name__)
# Inserisci qui la tua chiave segreta generata, ad es. con os.urandom o uuid
app.secret_key = 'f97b1e6c3a4f4d1e8b7c2a8e0d3abb12'

# Semplice archivio di credenziali (username: {password, role})
# L'utente con ruolo "admin" vede tutte le informazioni, mentre quello con
# ruolo "utente" visualizza un set ridotto di dati.
USERS = {
    "admin": {"password": "adminpass", "role": "admin"},
    "utente": {"password": "userpass", "role": "utente"},
}

BASE_DIR        = os.path.abspath(os.path.dirname(__file__))
TEMPLATES_DOCX  = os.path.join(BASE_DIR, "templates_docx")
OUT_DIR         = os.path.join(BASE_DIR, "out")
GOOGLE_SHEET_ID = "1sazXbmARDJ29s8HuPVfvvRdCig93KJpj-th6xBYw7-g"
SERVICE_ACCOUNT_FILE = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Percorsi ai file .docx template (verifica che i nomi siano esatti)
TPL_SENZA_ACCUMULO = os.path.join(TEMPLATES_DOCX, "template_senza_accumulo.docx")
TPL_CON_ACCUMULO   = os.path.join(TEMPLATES_DOCX, "template_con_accumulo.docx")
TPL_SENZA_ACCUMULO_WALLBOX = os.path.join(
    TEMPLATES_DOCX, "template_senza_accumulo_wallbox.docx"
)
TPL_CON_ACCUMULO_WALLBOX = os.path.join(
    TEMPLATES_DOCX, "template_con_accumulo_wallbox.docx"
)

# Crea la cartella OUT se non esiste
os.makedirs(OUT_DIR, exist_ok=True)

# Mappa dei pannelli per tipologia e potenza (usata per {{Np}} nei template)
NUM_PANNELLI = {
    "Mono": {3: 7, 4: 9, 5: 12, 6: 14},
    "Tri": {
        6: 14,
        8: 18,
        10: 23,
        15: 34,
        20: 45,
        25: 56,
        30: 67,
        40: 89,
        50: 112,
        60: 134,
    },
}


def generate_nc() -> str:
    """Genera il codice univoco per {{NC}}."""
    random_part = "".join(random.choices(string.ascii_lowercase + string.digits, k=3))
    date_part = datetime.now().strftime("%d%m%y")
    return random_part + date_part


def get_sheet():
    """Return the first worksheet of the configured Google Sheet."""
    creds_info = os.environ.get("GOOGLE_SERVICE_ACCOUNT_INFO")
    creds = None
    if creds_info:
        service_dict = None
        parse_errors = []
        try:
            service_dict = json.loads(creds_info)
        except json.JSONDecodeError as e:
            parse_errors.append(str(e))
            try:
                decoded = base64.b64decode(creds_info).decode("utf-8")
                service_dict = json.loads(decoded)
            except Exception as e2:
                parse_errors.append(str(e2))
                raise RuntimeError(
                    "Invalid GOOGLE_SERVICE_ACCOUNT_INFO; provide valid JSON or "
                    f"base64 encoded JSON. Errors: {', '.join(parse_errors)}"
                )
        try:
            creds = Credentials.from_service_account_info(
                service_dict, scopes=SCOPES
            )
        except Exception as e:
            raise RuntimeError(f"Invalid service account info: {e}")
    else:
        cred_file = SERVICE_ACCOUNT_FILE
        if not os.path.exists(cred_file):
            raise RuntimeError(
                "Google Sheets credentials not found. "
                "Set GOOGLE_SERVICE_ACCOUNT_INFO or GOOGLE_SERVICE_ACCOUNT_FILE"
            )
        try:
            creds = Credentials.from_service_account_file(cred_file, scopes=SCOPES)
        except Exception as e:
            raise RuntimeError(
                f"Invalid service account file '{cred_file}': {e}"
            )
    try:
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(GOOGLE_SHEET_ID)
    except Exception as e:
        raise RuntimeError(
            f"Google Sheets authentication failed: {e}. "
            "Verify your service account credentials."
        )
    return sh.sheet1

# ------------------------------------------------------------
# ROUTE PRINCIPALE: mostra il form HTML (GET)
# ------------------------------------------------------------
@app.route("/", methods=["GET"])
def index():
    if "username" not in session:
        return redirect(url_for("login"))
    return render_template(
        "form.html",
        username=session.get("username"),
        role=session.get("role"),
        with_customer=session.get("with_customer", False),
    )

# ------------------------------------------------------------
# ROUTE LOGIN
# ------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        with_customer = request.form.get("with_customer") == "on"
        user = USERS.get(username)
        if user and user["password"] == password:
            session["username"] = username
            session["role"] = user["role"]
            session["with_customer"] = with_customer
            return redirect(url_for("index"))
        flash("Credenziali non valide", "error")
    return render_template("login.html")


# ------------------------------------------------------------
# ROUTE LOGOUT
# ------------------------------------------------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ------------------------------------------------------------
# ROUTE OPZIONALE: pulizia cartella out
# ------------------------------------------------------------
@app.route("/cleanup")
def cleanup():
    try:
        for f in os.listdir(OUT_DIR):
            os.remove(os.path.join(OUT_DIR, f))
        flash("Cartella OUT pulita.", "info")
    except Exception as e:
        flash(f"Impossibile pulire OUT: {e}", "error")
    return redirect(url_for("index"))

# ------------------------------------------------------------
# ROUTE AGGIUNTA: genera il PDF a partire dai dati JSON
# ------------------------------------------------------------
# … (import, configurazioni e route index/cleanup restano identiche) …

# … (import, configurazioni e route index/cleanup restano identiche) …

@app.route("/genera_pdf", methods=["POST"])
def genera_pdf():
    try:
        dati = request.get_json(force=True)

        # 1) Scegli quale template .docx usare
        want_wallbox = dati.get("objColonnina", False)
        if want_wallbox:
            if dati.get("accumulo", 0) > 0:
                tpl_path = TPL_CON_ACCUMULO_WALLBOX
            else:
                tpl_path = TPL_SENZA_ACCUMULO_WALLBOX
        else:
            if dati.get("accumulo", 0) > 0:
                tpl_path = TPL_CON_ACCUMULO
            else:
                tpl_path = TPL_SENZA_ACCUMULO

        # 2) Genera un base_name univoco (UUID) per i file temporanei
        uid = uuid.uuid4().hex[:8]
        base_name = f"temp_{dati['nome']}_{dati['cognome']}_{uid}"
        nome_docx_out = base_name + ".docx"
        path_docx_out = os.path.join(OUT_DIR, nome_docx_out)

        # 3) Prepara il contesto per docxtpl
        #    NOTA: usiamo "prezzoFormatted" per preservare i punti
        extra_pan = int(dati.get("extraPannelli", 0))
        extra_kw = extra_pan // 2
        np_value = (NUM_PANNELLI.get(dati.get("tipologia"), {}).get(int(dati.get("potenza", 0)), 0) + extra_pan)
        contesto = {
            "Nome":           dati.get("nome", ""),
            "Cognome":        dati.get("cognome", ""),
            "Pot":            f"{int(dati.get('potenza', 0)) + extra_kw}",
            "Acc":            f"{int(dati.get('accumulo', 0))}" if dati.get("accumulo", 0) > 0 else "",
            "Prezzo":         dati.get("prezzoFormatted", ""),  # già stringa formattata con “.”
            "Tipo":           "IBRIDO" if dati.get("tipoInverter", "ibrido") == "ibrido" else "DI STRINGA",
        }
        contesto["Np"] = np_value
        nc_code = generate_nc()
        contesto["NC"] = nc_code
        if "margine" in dati:
            contesto["Margine"] = f"{dati['margine']:.2f}"
        if "ritenuta" in dati:
            contesto["Ritenuta"] = f"{dati['ritenuta']:.2f}"
        if "flusso" in dati:
            contesto["Flusso"] = f"{dati['flusso']:.2f}"

        # 4) Renderizza il .docx
        doc = DocxTemplate(tpl_path)
        doc.render(contesto)
        doc.save(path_docx_out)

        # 5) Converte il .docx in PDF con LibreOffice headless
        cmd = [
            "libreoffice",
            "--headless",
            "--convert-to", "pdf",
            "--outdir", OUT_DIR,
            path_docx_out
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        # 6) Rimuovi il .docx temporaneo
        try:
            os.remove(path_docx_out)
        except:
            pass

        # 7) Leggi il PDF generato (temp_<…>.pdf)
        pdf_generated     = base_name + ".pdf"
        path_pdf_generated = os.path.join(OUT_DIR, pdf_generated)

        with open(path_pdf_generated, "rb") as f:
            pdf_bytes = f.read()

        # 8) Rimuovi il PDF temporaneo (opzionale)
        try:
            os.remove(path_pdf_generated)
        except:
            pass

        # 9) Invia il PDF al browser con nome “Preventivo_<…>.pdf”
        download_name = f"Preventivo_{dati['nome']}_{dati['cognome']}_{uid}.pdf"
        response = send_file(
            io.BytesIO(pdf_bytes),
            as_attachment=True,
            download_name=download_name,
            mimetype="application/pdf"
        )
        response.headers["X-NC"] = nc_code
        return response

    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


# ------------------------------------------------------------
# ROUTE PER SALVARE I DATI NEL GOOGLE SHEET
# ------------------------------------------------------------
@app.route("/salva_sheet", methods=["POST"], endpoint="salva_sheet")
def append_to_sheet():
    try:
        dati = request.get_json(force=True)
        sheet = get_sheet()
        row = [
            dati.get("nc"),
            dati.get("nome"),
            dati.get("cognome"),
            dati.get("tipologiaCliente"),
            dati.get("tipologia"),
            dati.get("potenza"),
            dati.get("accumulo"),
            dati.get("np"),
            dati.get("installazione"),
            dati.get("tetto"),
            dati.get("oggettoFornitura"),
            dati.get("prezzoListino"),
            dati.get("prezzoScontato"),
            dati.get("provvigione"),
            dati.get("margine"),
            dati.get("ritenuta"),
            dati.get("flusso"),
        ]
        sheet.append_row(row, value_input_option="USER_ENTERED")
        return jsonify({"status": "ok"})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


# ------------------------------------------------------------
# ROUTE AGGIUNTA: genera il DOCX a partire dai dati JSON
# ------------------------------------------------------------

@app.route("/genera_doc", methods=["POST"])
def genera_doc():
    try:
        dati = request.get_json(force=True)

        # 1) Scegli quale template .docx usare
        want_wallbox = dati.get("objColonnina", False)
        if want_wallbox:
            if dati.get("accumulo", 0) > 0:
                tpl_path = TPL_CON_ACCUMULO_WALLBOX
            else:
                tpl_path = TPL_SENZA_ACCUMULO_WALLBOX
        else:
            if dati.get("accumulo", 0) > 0:
                tpl_path = TPL_CON_ACCUMULO
            else:
                tpl_path = TPL_SENZA_ACCUMULO

        # 2) Genera un base_name univoco (UUID) per i file temporanei
        uid = uuid.uuid4().hex[:8]
        base_name = f"temp_{dati['nome']}_{dati['cognome']}_{uid}"
        nome_docx_out = base_name + ".docx"
        path_docx_out = os.path.join(OUT_DIR, nome_docx_out)

        # 3) Prepara il contesto per docxtpl
        extra_pan = int(dati.get("extraPannelli", 0))
        extra_kw = extra_pan // 2
        np_value = (NUM_PANNELLI.get(dati.get("tipologia"), {}).get(int(dati.get("potenza", 0)), 0) + extra_pan)
        contesto = {
            "Nome":           dati.get("nome", ""),
            "Cognome":        dati.get("cognome", ""),
            "Pot":            f"{int(dati.get('potenza', 0)) + extra_kw}",
            "Acc":            f"{int(dati.get('accumulo', 0))}" if dati.get("accumulo", 0) > 0 else "",
            "Prezzo":         dati.get("prezzoFormatted", ""),
            "Tipo":           "IBRIDO" if dati.get("tipoInverter", "ibrido") == "ibrido" else "DI STRINGA",
        }
        contesto["Np"] = np_value
        nc_code = generate_nc()
        contesto["NC"] = nc_code
        if "margine" in dati:
            contesto["Margine"] = f"{dati['margine']:.2f}"
        if "ritenuta" in dati:
            contesto["Ritenuta"] = f"{dati['ritenuta']:.2f}"
        if "flusso" in dati:
            contesto["Flusso"] = f"{dati['flusso']:.2f}"

        # 4) Renderizza il .docx
        doc = DocxTemplate(tpl_path)
        doc.render(contesto)
        doc.save(path_docx_out)

        # 5) Leggi il DOCX generato
        with open(path_docx_out, "rb") as f:
            docx_bytes = f.read()

        # 6) Rimuovi il file temporaneo
        try:
            os.remove(path_docx_out)
        except:
            pass

        # 7) Invia il DOCX al browser
        download_name = f"Preventivo_{dati['nome']}_{dati['cognome']}_{uid}.docx"
        response = send_file(
            io.BytesIO(docx_bytes),
            as_attachment=True,
            download_name=download_name,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        response.headers["X-NC"] = nc_code
        return response

    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


# ------------------------------------------------------------
# ROUTE PAGINA ANALISI ENERGETICA
# ------------------------------------------------------------
@app.route("/analisi", methods=["GET"])
def analisi():
    if "username" not in session:
        return redirect(url_for("login"))
    kw = request.args.get("kw", "")
    return render_template("analisi.html", username=session.get("username"), kw=kw)


# ------------------------------------------------------------
# API PVGIS
# ------------------------------------------------------------
@app.route("/api/analisi", methods=["POST"])
def api_analisi():
    try:
        data = request.get_json(force=True)
        lat = float(data.get("lat"))
        lon = float(data.get("lon"))
        azimuth = float(data.get("azimuth"))  # 0=N, 90=E
        tilt = float(data.get("tilt"))
        kw = float(data.get("kw", 1))

        aspect = azimuth - 180  # PVGIS: 0=S, west positive

        url = (
            "https://re.jrc.ec.europa.eu/api/v5_2/PVcalc?"
            f"lat={lat}&lon={lon}&peakpower={kw}&loss=14&angle={tilt}&aspect={aspect}&outputformat=json"
        )
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        js = resp.json()
        monthly = []
        total = 0.0
        for m in js.get("outputs", {}).get("monthly", []):
            val = m.get("E_m")
            if val is None:
                continue
            monthly.append(val)
            total += val
        return jsonify({"monthly": monthly, "total": total})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500



# ------------------------------------------------------------
# AVVIO in locale (per test)
# ------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
