"""Pagine 'interpelli' sui siti delle scuole: elenco di link ad avvisi (PDF o pagine)."""
from __future__ import annotations

import html
import re
from datetime import datetime
from urllib.parse import urljoin

from .. import rete
from ..analisi import (classi_concorso, e_interpello_docenti, email_da, ordine_da, ore_da, pulisci,
                       scadenza_da, testo_pdf)
from ..modello import Fonte, Interpello

_A = re.compile(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.S | re.I)
_CODICE_SPAGGIARI = re.compile(r"(?:sede_codice=|custcode=|/sdg2/\w+/|scaling\.spaggiari\.eu/|cspace\.spaggiari\.eu//?pub/|"
                               r"meta-pvw-sede_codice\"\s+content=\")([A-Za-z]{4}\d{4})")
MAX_LINK = 15


def codice_spaggiari(testo_html: str) -> str:
    for m in _CODICE_SPAGGIARI.finditer(testo_html):
        c = m.group(1).upper()
        if c != "PVW0":
            return c
    return ""


def leggi(f: Fonte) -> tuple[list[Interpello], str]:
    """Restituisce gli interpelli trovati e l'eventuale codice Spaggiari scoperto nella pagina."""
    r = rete.get(f.rif)
    if r is None or r.status_code != 200:
        raise RuntimeError(f"pagina del sito non raggiungibile ({getattr(r, 'status_code', 'rete')})")
    pagina = r.text
    scoperto = codice_spaggiari(pagina)
    oggi = datetime.now()
    out, visti = [], set()
    for href, testo_a in _A.findall(pagina):
        titolo = pulisci(html.unescape(re.sub(r"<[^>]+>", " ", testo_a)))
        url = urljoin(f.rif, html.unescape(href))
        if url in visti or len(titolo) < 12 or not e_interpello_docenti(titolo):
            continue
        visti.add(url)
        if len(visti) > MAX_LINK:
            break
        testo = ""
        rr = rete.get(url, timeout=60)
        if rr is not None and rr.status_code == 200:
            if rr.content[:4] == b"%PDF":
                testo = testo_pdf(rr.content)
            elif "html" in rr.headers.get("content-type", ""):
                testo = pulisci(re.sub(r"<[^>]+>", " ", rr.text))[:20000]
        scad = scadenza_da(f"{titolo}\n{testo}")
        if scad and scad < oggi:
            continue
        classi = classi_concorso(titolo) or classi_concorso(testo)
        email = email_da(testo)
        out.append(Interpello(
            istituto=f.istituto, provincia=f.provincia, codice_mecc=f.codice_mecc,
            titolo=titolo, fonte="Sito della scuola", link_avviso=url,
            link_candidatura=f"mailto:{email}" if email else url,
            classi=classi, ordine=ordine_da(classi, f"{titolo}\n{testo}"),
            ore=ore_da(titolo) or ore_da(testo), scadenza=scad, email_candidatura=email,
            note="" if scad else "Scadenza non trovata automaticamente: controllare l'avviso",
        ))
    return out, scoperto
