"""Siti delle scuole: pagine 'interpelli' e link ad avvisi di interpello nelle sezioni consentite dal robots.txt.

Tipi di fonte:
  sito    -> rif è l'indirizzo di una pagina interpelli nota
  scuola  -> rif è la home del sito: si leggono la home e, se esistono, le pagine interpelli più comuni
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlsplit

from .. import rete
from ..analisi import (classi_concorso, e_interpello_docenti, email_da, ordine_da, ore_da, pulisci,
                       scadenza_da, testo_pdf)
from ..modello import Fonte, Interpello

_A = re.compile(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.S | re.I)
_FINO_AL = re.compile(r"fino\s+al?\s*(\d{1,2})[/.\-]?(\d{1,2})[/.\-]?(\d{4})", re.I)
_DATE = re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](20\d{2})\b")
_GENERICO = re.compile(r"^(avvisi\s+e\s+)?interpell[oi](\s+(supplenze|docenti|news|ex\s*mad|info|scuola))?$", re.I)
PAGINE_TIPICHE = ["/pagine/interpelli", "/pagine/interpello", "/pagine/interpelli-supplenze",
                  "/pagine/avvisi-e-interpelli", "/interpelli/", "/servizio/interpelli/"]
MAX_LINK = 15


def _data_fine(testo: str):
    m = _FINO_AL.search(testo.replace("-", " ")) or re.search(r"fino-al-(\d{2})(\d{2})(\d{4})", testo)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), 23, 59)
        except ValueError:
            return None
    return None


def _data_piu_recente(testo: str):
    date = []
    for g, me, a in _DATE.findall(testo):
        try:
            date.append(datetime(int(a), int(me), int(g)))
        except ValueError:
            pass
    return max(date) if date else None


def _apri(url: str):
    try:
        return rete.get(url, timeout=60)
    except rete.VietatoDaRobots:
        return None


def _avvisi_in_pagina(f: Fonte, url_pagina: str, pagina: str, visti: set) -> list[Interpello]:
    oggi = datetime.now()
    out = []
    for href, testo_a in _A.findall(pagina):
        titolo = pulisci(html.unescape(re.sub(r"<[^>]+>", " ", testo_a)))
        url = urljoin(url_pagina, html.unescape(href))
        if url in visti or len(titolo) < 12 or not e_interpello_docenti(titolo):
            continue
        if (_GENERICO.match(titolo.strip(" .:"))
                or re.search(r"/sdg2/Interpelli/\w+/?$|cerca\?tag=|/albo-online|interpello-nazionale", url, re.I)
                or not e_interpello_docenti(url.rsplit("/", 1)[-1].replace("-", " ") + " interpello")):
            continue   # voce di menu, pagina indice o modulistica, non un avviso
        wp = re.search(r"/uploads/(20\d{2})/(\d{2})/", url)
        if wp and datetime(int(wp.group(1)), int(wp.group(2)), 1) < oggi - timedelta(days=60):
            continue   # file caricato da più di due mesi
        fine = _data_fine(titolo) or _data_fine(url)
        if fine and fine < oggi:
            continue
        visti.add(url)
        if len(visti) > MAX_LINK:
            break
        testo = ""
        e_pdf = False
        rr = None
        if "spaggiari.eu" not in url:            # i documenti su Spaggiari non si scaricano: link nella mail
            rr = _apri(url)
        if rr is not None and rr.status_code == 200:
            if rr.content[:4] == b"%PDF":
                testo = testo_pdf(rr.content)
                e_pdf = True
            elif "html" in rr.headers.get("content-type", ""):
                testo = pulisci(re.sub(r"<[^>]+>", " ", rr.text))[:20000]
        scad = scadenza_da(f"{titolo}\n{testo}") or fine
        if scad and scad < oggi:
            continue
        recente = _data_piu_recente(f"{titolo} {testo}")
        if not scad and recente and recente < oggi - timedelta(days=30):
            continue   # avviso vecchio rimasto in pagina
        classi = classi_concorso(f"{titolo} {url}") or classi_concorso(testo)
        specifico = bool(re.search(r"/sdg2/Interpelli/\w+/[0-9a-f-]{36}", url))
        if not classi and not scad and not specifico and not (recente and recente >= oggi - timedelta(days=30)):
            continue   # nessuna classe, nessuna data: pagina generica o avviso vecchio
        email = email_da(testo)
        out.append(Interpello(
            istituto=f.istituto, provincia=f.provincia, codice_mecc=f.codice_mecc,
            titolo=titolo, fonte="Sito della scuola", link_avviso=url,
            link_candidatura=f"mailto:{email}" if email else url,
            classi=classi, ordine=ordine_da(classi, f"{titolo}\n{testo}"),
            ore=ore_da(titolo) or ore_da(testo), scadenza=scad, email_candidatura=email,
            note=("" if scad else "Scadenza: vedi avviso") if e_pdf or "spaggiari.eu" in url else
                 "Notizia sul sito, senza bando allegato: da verificare con la segreteria",
        ))
    return out


def leggi(f: Fonte) -> tuple[list[Interpello], bool]:
    """Restituisce (interpelli trovati, True se la scuola ha una pagina interpelli leggibile)."""
    visti: set = set()
    if f.tipo == "sito":
        try:
            r = rete.get(f.rif)
        except rete.VietatoDaRobots:
            raise RuntimeError("pagina esclusa dal robots.txt del sito")
        if r is None or r.status_code != 200:
            raise RuntimeError(f"pagina del sito non raggiungibile ({getattr(r, 'status_code', 'rete')})")
        return _avvisi_in_pagina(f, f.rif, r.text, visti), True

    # tipo "scuola": home + pagine interpelli tipiche
    base = "{0.scheme}://{0.netloc}".format(urlsplit(f.rif))
    trovati: list[Interpello] = []
    pagina_interpelli = False
    r = _apri(f.rif)
    if r is None or r.status_code != 200:
        raise RuntimeError(f"sito non raggiungibile ({getattr(r, 'status_code', 'rete o robots.txt')})")
    trovati += _avvisi_in_pagina(f, f.rif, r.text, visti)
    # link nella home verso una pagina interpelli dedicata, poi gli indirizzi più comuni
    candidate = [urljoin(f.rif, html.unescape(h)) for h, t in _A.findall(r.text)
                 if re.search(r"interpell", h + t, re.I) and not re.search(r"spaggiari\.eu|cerca\?tag=", h)]
    candidate += [base + p for p in PAGINE_TIPICHE]
    provate = set()
    for url in candidate:
        if url in provate or urlsplit(url).netloc != urlsplit(base).netloc:
            continue
        provate.add(url)
        rr = _apri(url)
        if rr is None or rr.status_code != 200 or "interpell" not in rr.text.lower():
            continue
        if url.rstrip("/") != f.rif.rstrip("/"):
            pagina_interpelli = True
            trovati += _avvisi_in_pagina(f, url, rr.text, visti)
        if len(provate) >= 8:
            break
    return trovati, pagina_interpelli
