#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import uuid
import subprocess
import io
import traceback
import random
import string
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

# Percorsi ai file .docx template (verifica che i nomi siano esatti)
TPL_SENZA_ACCUMULO = os.path.join(TEMPLATES_DOCX, "template_senza_accumulo.docx")
TPL_CON_ACCUMULO   = os.path.join(TEMPLATES_DOCX, "template_con_accumulo.docx")

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
        np_value = NUM_PANNELLI.get(dati.get("tipologia"), {}).get(int(dati.get("potenza", 0)), "")
        contesto = {
            "Nome":           dati.get("nome", ""),
            "Cognome":        dati.get("cognome", ""),
            "Pot":            f"{int(dati.get('potenza', 0))}",
            "Acc":            f"{int(dati.get('accumulo', 0))}" if dati.get("accumulo", 0) > 0 else "",
            "Prezzo":         dati.get("prezzoFormatted", "")  # già stringa formattata con “.”
        }
        contesto["Np"] = np_value
        contesto["NC"] = generate_nc()
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
        return send_file(
            io.BytesIO(pdf_bytes),
            as_attachment=True,
            download_name=download_name,
            mimetype="application/pdf"
        )

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
        np_value = NUM_PANNELLI.get(dati.get("tipologia"), {}).get(int(dati.get("potenza", 0)), "")
        contesto = {
            "Nome":           dati.get("nome", ""),
            "Cognome":        dati.get("cognome", ""),
            "Pot":            f"{int(dati.get('potenza', 0))}",
            "Acc":            f"{int(dati.get('accumulo', 0))}" if dati.get("accumulo", 0) > 0 else "",
            "Prezzo":         dati.get("prezzoFormatted", "")
        }
        contesto["Np"] = np_value
        contesto["NC"] = generate_nc()
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
        return send_file(
            io.BytesIO(docx_bytes),
            as_attachment=True,
            download_name=download_name,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500



# ------------------------------------------------------------
# AVVIO in locale (per test)
# ------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
