"""Axios: albo online su trasparenzascuole.it (tabella caricata via APP_Ajax_Get.aspx)."""
from __future__ import annotations

import html
import re
from datetime import datetime, timedelta

from .. import rete
from ..analisi import classi_concorso, e_interpello_docenti, ordine_da, ore_da, pulisci, scadenza_da
from ..modello import Fonte, Interpello

BASE = "https://www.trasparenzascuole.it"
GIORNI_ALBO = 45
_RIGA = re.compile(r"Pubblicato in data\s*(\d{2}/\d{2}/\d{4}).*?Oggetto:\s*(.*?)</i>", re.S | re.I)


def leggi_albo(f: Fonte) -> list[Interpello]:
    guid = f.rif
    pubblico = f.link_pubblico or BASE
    rete.get(pubblico)                                          # apre la sessione come farebbe il browser
    ajax = {"X-Requested-With": "XMLHttpRequest", "Referer": pubblico,
            "Accept": "application/json, text/javascript, */*; q=0.01"}
    rete.get(f"{BASE}/Ajax/APP_Ajax_Get.aspx?action=INIT_APD&Others={guid}", headers=ajax)
    r = rete.get(f"{BASE}/Ajax/APP_Ajax_Get.aspx?action=GET_APD_TABLE&Others={guid}", headers=ajax)
    if r is None or r.status_code != 200 or "Pubblicato in data" not in r.text:
        stato = getattr(r, "status_code", "rete")
        inizio = (r.text[:80].replace("\n", " ") if r is not None else "")
        raise RuntimeError(f"albo Axios non disponibile ({stato}): {inizio}")
    limite = datetime.now() - timedelta(days=GIORNI_ALBO)
    out = []
    for data_s, oggetto in _RIGA.findall(r.text):
        pubbl = datetime.strptime(data_s, "%d/%m/%Y")
        if pubbl < limite:
            continue
        titolo = pulisci(html.unescape(re.sub(r"<[^>]+>", " ", oggetto)))
        if not e_interpello_docenti(titolo):
            continue
        classi = classi_concorso(titolo)
        out.append(Interpello(
            istituto=f.istituto, provincia=f.provincia, codice_mecc=f.codice_mecc,
            titolo=titolo, fonte="Albo Axios", link_avviso=pubblico, link_candidatura=pubblico,
            classi=classi, ordine=ordine_da(classi, titolo), ore=ore_da(titolo),
            scadenza=scadenza_da(titolo, dopo=pubbl.date()), pubblicato=pubbl.date(),
            note="Albo Axios: aprire l'atto per scadenza e modalità di candidatura",
        ))
    return out
