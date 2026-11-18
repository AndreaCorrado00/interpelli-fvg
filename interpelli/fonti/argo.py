"""Argo: albo pretorio online (interfaccia pubblica generale.portaleargo.it)."""
from __future__ import annotations

from datetime import datetime, timedelta

from .. import rete
from ..analisi import (classi_concorso, e_interpello_docenti, email_da, ordine_da, ore_da, pulisci,
                       scadenza_da, testo_pdf)
from ..modello import Fonte, Interpello

API = "https://generale.portaleargo.it/albopretorio/api"
GIORNI_ALBO = 45


def _pdf_atto(id_atto: int) -> bytes:
    r = rete.get(f"{API}/public/atti/online/{id_atto}")
    if r is None or r.status_code != 200:
        return b""
    allegati = [a for a in r.json().get("allegati", []) if not a.get("nome", "").lower().startswith("timbro")]
    for a in allegati[:1]:
        r = rete.get(f"{API}/public/atti/allegati/{a['uuid']}")
        if r is None or r.status_code != 200:
            continue
        url = r.json() if r.headers.get("content-type", "").startswith("application/json") else ""
        if isinstance(url, str) and url.startswith("http"):
            r = rete.get(url, timeout=60)
            if r is not None and r.status_code == 200:
                return r.content
    return b""


def leggi_albo(f: Fonte) -> list[Interpello]:
    codice = f.rif.upper()
    limite = datetime.now() - timedelta(days=GIORNI_ALBO)
    pubblico = f"https://www.albipretorionline.com/{codice}"
    out = []
    for pagina in range(3):
        r = rete.post_json(f"{API}/public/atti/filters/{codice}",
                           {"object": {}, "page": pagina, "size": 20, "sortBy": "numRegistroAnno", "sortDesc": True})
        if r is None or r.status_code != 200:
            raise RuntimeError(f"albo Argo non disponibile ({getattr(r, 'status_code', 'rete')})")
        elenco = r.json().get("list", [])
        if not elenco:
            break
        fermati = False
        for a in elenco:
            pubbl = datetime.strptime(a["dataPubblicazione"], "%d/%m/%Y") if a.get("dataPubblicazione") else None
            if pubbl and pubbl < limite:
                fermati = True
                continue
            titolo = pulisci(a.get("descrizione", ""))
            if a.get("annullato") or not e_interpello_docenti(titolo):
                continue
            testo = testo_pdf(_pdf_atto(a["id"]))
            tutto = f"{titolo}\n{testo}"
            classi = classi_concorso(titolo) or classi_concorso(testo)
            email = email_da(testo)
            out.append(Interpello(
                istituto=f.istituto, provincia=f.provincia, codice_mecc=f.codice_mecc,
                titolo=titolo, fonte="Albo Argo", link_avviso=pubblico,
                link_candidatura=f"mailto:{email}" if email else pubblico,
                classi=classi, ordine=ordine_da(classi, tutto),
                ore=ore_da(titolo) or ore_da(testo),
                scadenza=scadenza_da(f"{titolo}\n{testo}", dopo=pubbl.date() if pubbl else None),
                pubblicato=pubbl.date() if pubbl else None, email_candidatura=email,
                note=f"Atto n. {a.get('numRegistroAnno', '')} sull'albo" + ("" if testo else "; documento non letto"),
            ))
        if fermati:
            break
    return out
