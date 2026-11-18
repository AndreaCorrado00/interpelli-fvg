"""Spaggiari: modulo Interpelli (sdg2/Interpelli) e Albo online (sdg2/AlboOnline)."""
from __future__ import annotations

import html
import json
import re
from datetime import datetime, timedelta

from .. import rete
from ..analisi import (classi_concorso, e_interpello_docenti, email_da, ordine_da, ore_da, pulisci,
                       scadenza_da, testo_pdf)
from ..modello import Fonte, Interpello

BASE = "https://web.spaggiari.eu/sdg2"
GIORNI_ALBO = 45   # atti dell'albo più vecchi di così non vengono considerati


def _props(testo: str) -> dict:
    m = re.search(r'data-page="([^"]*)"', testo)
    if not m:
        raise RuntimeError("struttura della pagina Spaggiari non riconosciuta")
    return json.loads(html.unescape(m.group(1)))["props"]


def _data(s: str):
    s = (s or "").strip()
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def leggi_interpelli(f: Fonte) -> list[Interpello]:
    """Modulo Interpelli. 403 = modulo non attivo per la scuola (non è un errore)."""
    codice = f.rif.upper()
    out, pagina, ultima = [], 1, 1
    adesso = datetime.now()
    while pagina <= min(ultima, 5):
        r = rete.get(f"{BASE}/Interpelli/{codice}?page={pagina}")
        if r is None:
            raise RuntimeError("Spaggiari non raggiungibile")
        if r.status_code == 404:
            return []
        if r.status_code == 403:
            if "Forbidden" in r.text and "data-page" not in r.text and pagina == 1:
                # 403 è anche la risposta normale per le scuole senza modulo interpelli:
                # lo distinguiamo dal blocco controllando che l'albo della stessa scuola risponda
                prova = rete.get(f"{BASE}/AlboOnline/{codice}")
                if prova is not None and prova.status_code == 403:
                    raise RuntimeError("Spaggiari ha rifiutato la richiesta (403): possibile blocco")
            return []
        props = _props(r.text)
        blocco = props.get("interpelli") or {}
        ultima = blocco.get("last_page") or 1
        for it in blocco.get("data", []):
            inizio = _data(it.get("data_inizio_pubblicazione"))
            fine = _data(it.get("data_fine_pubblicazione"))
            if fine and (fine.hour, fine.minute) == (0, 0):
                fine = fine.replace(hour=23, minute=59)   # "31/05/2027 00:00" = fino a fine giornata
            if (inizio and inizio > adesso) or (fine and fine < adesso):
                continue
            cc = it.get("classe_concorso") or {}
            codice_cdc = (cc.get("codice_ministeriale") or "").upper()
            descr = pulisci(it.get("descrizione", ""))
            testo = " ".join([descr, cc.get("descrizione") or "", it.get("ordine_scuola") or ""])
            classi = [codice_cdc] if codice_cdc else classi_concorso(descr)
            ordine = ordine_da(classi, testo)
            if (it.get("ordine_scuola") or "") == "infanzia_primaria" and ordine.startswith("secondaria"):
                ordine = "primaria"
            link = f"{BASE}/Interpelli/{codice}/{it['uuid']}"
            out.append(Interpello(
                istituto=f.istituto, provincia=f.provincia, codice_mecc=f.codice_mecc,
                titolo=descr, fonte="Spaggiari Interpelli", link_avviso=link, link_candidatura=link,
                classi=classi, classe_testo=cc.get("descrizione") or "", ordine=ordine,
                ore=str(it["orario_settimanale"]) if it.get("orario_settimanale") else ore_da(descr),
                scadenza=fine, pubblicato=inizio.date() if inizio else None,
                note=pulisci(it.get("modalita_termini_riscontro") or ""),
            ))
        pagina += 1
    return out


def leggi_albo(f: Fonte) -> list[Interpello]:
    codice = f.rif.upper()
    limite = datetime.now() - timedelta(days=GIORNI_ALBO)
    out, pagina, ultima = [], 1, 1
    while pagina <= min(ultima, 4):
        r = rete.get(f"{BASE}/AlboOnline/{codice}?page={pagina}")
        if r is None or r.status_code != 200:
            raise RuntimeError(f"albo Spaggiari non disponibile ({getattr(r, 'status_code', 'rete')})")
        doc = _props(r.text).get("documenti") or {}
        ultima = doc.get("last_page") or 1
        troppo_vecchi = False
        for d in doc.get("data", []):
            pubbl = _data(d.get("data_pubblicazione"))
            if pubbl and pubbl < limite:
                troppo_vecchi = True
                continue
            documento = d.get("documento") or {}
            prot = d.get("protocollo") or documento.get("protocollo") or {}
            oggetto = pulisci(html.unescape(prot.get("oggetto") or ""))
            nome_file = documento.get("nome_file_origine") or ""
            titolo = oggetto or nome_file
            if not e_interpello_docenti(f"{titolo} {nome_file}"):
                continue
            out.append(_da_documento(f, titolo, documento, pubbl))
        if troppo_vecchi:
            break
        pagina += 1
    return out


def _da_documento(f: Fonte, titolo: str, documento: dict, pubbl) -> Interpello:
    url = documento.get("url") or ""
    testo = ""
    if documento.get("url_download"):
        r = rete.get(documento["url_download"], timeout=60)
        if r is not None and r.status_code == 200 and r.content[:4] == b"%PDF":
            testo = testo_pdf(r.content)
    tutto = f"{titolo}\n{testo}"
    classi = classi_concorso(titolo) or classi_concorso(testo)
    email = email_da(testo)
    return Interpello(
        istituto=f.istituto, provincia=f.provincia, codice_mecc=f.codice_mecc,
        titolo=titolo, fonte="Albo Spaggiari", link_avviso=url,
        link_candidatura=f"mailto:{email}" if email else url,
        classi=classi, ordine=ordine_da(classi, tutto),
        ore=ore_da(titolo) or ore_da(testo),
        scadenza=scadenza_da(testo or titolo, dopo=pubbl.date() if pubbl else None),
        pubblicato=pubbl.date() if pubbl else None, email_candidatura=email,
        note="" if testo else "Avviso non leggibile automaticamente: verificare scadenza nel documento",
    )
