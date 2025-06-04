#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import uuid
import subprocess
from flask import Flask, render_template, request, send_file, flash, redirect, url_for
from docxtpl import DocxTemplate

# ------------------------------------------------------------
# CONFIGURAZIONE FOLDER E TEMPLATE
# ------------------------------------------------------------

app = Flask(__name__)
app.secret_key = 'sostituisci_con_una_chiave_segreta_casuale'

BASE_DIR        = os.path.abspath(os.path.dirname(__file__))
TEMPLATES_DOCX  = os.path.join(BASE_DIR, "templates_docx")
OUT_DIR         = os.path.join(BASE_DIR, "out")

# Percorsi ai file .docx template
TPL_SENZA_ACCUMULO = os.path.join(TEMPLATES_DOCX, "template_senza_accumulo.docx")
TPL_CON_ACCUMULO   = os.path.join(TEMPLATES_DOCX, "template_con_accumulo.docx")

# Crea la cartella OUT se non esiste
os.makedirs(OUT_DIR, exist_ok=True)

# ------------------------------------------------------------
# ROUTE PRINCIPALE: mostra il form e gestisce POST per generare PDF
# ------------------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        # 1) Recupera dati dal form
        nome     = request.form.get("nome", "").strip()
        cognome  = request.form.get("cognome", "").strip()
        try:
            potenza = float(request.form.get("potenza", "0"))
        except ValueError:
            potenza = 0.0
        try:
            accumulo = float(request.form.get("accumulo", "0"))
        except ValueError:
            accumulo = 0.0
        try:
            prezzo = float(request.form.get("prezzo", "0"))
        except ValueError:
            prezzo = 0.0
        try:
            margine = float(request.form.get("margine", "0"))
        except ValueError:
            margine = None
        try:
            ritenuta = float(request.form.get("ritenuta", "0"))
        except ValueError:
            ritenuta = None
        try:
            flusso = float(request.form.get("flusso", "0"))
        except ValueError:
            flusso = None

        # 2) Validazioni base
        if not nome or not cognome:
            flash("Devi inserire Nome e Cognome.", "error")
            return redirect(url_for("index"))
        # Potresti aggiungere altri controlli (es. potenza > 0)

        # 3) Scegli template .docx in base a accumulo
        if accumulo > 0:
            tpl_path = TPL_CON_ACCUMULO
        else:
            tpl_path = TPL_SENZA_ACCUMULO

        # 4) Costruisci nome file univoco (UUID) per evitare collisioni
        uid = uuid.uuid4().hex[:8]
        nome_docx_out = f"preventivo_{nome}_{cognome}_{uid}.docx"
        nome_pdf_out  = f"preventivo_{nome}_{cognome}_{uid}.pdf"
        path_docx_out = os.path.join(OUT_DIR, nome_docx_out)
        path_pdf_out  = os.path.join(OUT_DIR, nome_pdf_out)

        # 5) Prepara contesto per docxtpl
        contesto = {
            "Nome":    nome,
            "Cognome": cognome,
            "Pot":     f"{int(potenza):d}",
            "Acc":     f"{int(accumulo):d}" if accumulo > 0 else "",
            "Prezzo":  f"{int(prezzo):d}"
        }
        if margine is not None:
            contesto["Margine"] = f"{margine:.2f}"
        if ritenuta is not None:
            contesto["Ritenuta"] = f"{ritenuta:.2f}"
        if flusso is not None:
            contesto["Flusso"] = f"{flusso:.2f}"

        # 6) Renderizza il template .docx
        try:
            doc = DocxTemplate(tpl_path)
            doc.render(contesto)
            doc.save(path_docx_out)
        except Exception as e:
            flash(f"Errore generazione .docx: {e}", "error")
            return redirect(url_for("index"))

        # 7) Converti .docx in PDF con LibreOffice headless
        try:
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
        except Exception as e:
            flash(f"Errore conversione in PDF: {e}", "error")
            # Rimuovi .docx temporaneo
            try: os.remove(path_docx_out)
            except: pass
            return redirect(url_for("index"))

        # 8) Elimina il .docx temporaneo
        try:
            os.remove(path_docx_out)
        except: pass

        # 9) Invia il PDF al browser per il download
        if not os.path.isfile(path_pdf_out):
            flash("Errore: PDF non creato.", "error")
            return redirect(url_for("index"))

        return send_file(
            path_pdf_out,
            as_attachment=True,
            download_name=nome_pdf_out,
            mimetype='application/pdf'
        )

    # Se GET, mostra il form HTML
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
# AVVIO in locale (per test)
# ------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
