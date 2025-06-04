#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import uuid
import subprocess
import io
import traceback

from flask import Flask, render_template, request, send_file, flash, redirect, url_for, jsonify
from docxtpl import DocxTemplate

# ------------------------------------------------------------
# CONFIGURAZIONE FOLDER E TEMPLATE
# ------------------------------------------------------------

app = Flask(__name__)
# Inserisci qui la tua chiave segreta generata, ad es. con os.urandom o uuid
app.secret_key = 'f97b1e6c3a4f4d1e8b7c2a8e0d3abb12'

BASE_DIR        = os.path.abspath(os.path.dirname(__file__))
TEMPLATES_DOCX  = os.path.join(BASE_DIR, "templates_docx")
OUT_DIR         = os.path.join(BASE_DIR, "out")

# Percorsi ai file .docx template (verifica che i nomi siano esatti)
TPL_SENZA_ACCUMULO = os.path.join(TEMPLATES_DOCX, "template_senza_accumulo.docx")
TPL_CON_ACCUMULO   = os.path.join(TEMPLATES_DOCX, "template_con_accumulo.docx")

# Crea la cartella OUT se non esiste
os.makedirs(OUT_DIR, exist_ok=True)

# ------------------------------------------------------------
# ROUTE PRINCIPALE: mostra il form HTML (GET)
# ------------------------------------------------------------
@app.route("/", methods=["GET"])
def index():
    return render_template("form.html")

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
@app.route("/genera_pdf", methods=["POST"])
def genera_pdf():
    try:
        dati = request.get_json(force=True)

        # 1) Scegli template .docx in base al valore di "accumulo"
        if dati.get("accumulo", 0) > 0:
            tpl_path = TPL_CON_ACCUMULO
        else:
            tpl_path = TPL_SENZA_ACCUMULO

        # 2) Genera un base_name univoco (UUID) per evitare sovrascritture
        uid = uuid.uuid4().hex[:8]
        base_name = f"temp_{dati['nome']}_{dati['cognome']}_{uid}"
        nome_docx_out = base_name + ".docx"
        path_docx_out = os.path.join(OUT_DIR, nome_docx_out)

        # 3) Prepara il contesto per docxtpl
        contesto = {
            "Nome":    dati.get("nome", ""),
            "Cognome": dati.get("cognome", ""),
            "Pot":     f"{int(dati.get('potenza', 0))}",
            "Acc":     f"{int(dati.get('accumulo', 0))}" if dati.get("accumulo", 0) > 0 else "",
            "Prezzo":  f"{int(dati.get('prezzoListino', 0))}"
        }
        if "margine" in dati:
            contesto["Margine"] = f"{dati['margine']:.2f}"
        if "ritenuta" in dati:
            contesto["Ritenuta"] = f"{dati['ritenuta']:.2f}"
        if "flusso" in dati:
            contesto["Flusso"] = f"{dati['flusso']:.2f}"

        # 4) Renderizza il .docx con docxtpl
        doc = DocxTemplate(tpl_path)
        doc.render(contesto)
        doc.save(path_docx_out)

        # 5) Converte il .docx in PDF usando LibreOffice headless
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

        # 7) Ora LibreOffice ha creato “temp_<…>.pdf”
        pdf_generated = base_name + ".pdf"
        path_pdf_generated = os.path.join(OUT_DIR, pdf_generated)

        # 8) Leggi i byte del PDF creato
        with open(path_pdf_generated, "rb") as f:
            pdf_bytes = f.read()

        # 9) Rimuovi il PDF temporaneo dalla cartella OUT (opzionale)
        try:
            os.remove(path_pdf_generated)
        except:
            pass

        # 10) Restituisci il PDF al browser con nome “Preventivo_<…>.pdf”
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
# AVVIO in locale (per test)
# ------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
