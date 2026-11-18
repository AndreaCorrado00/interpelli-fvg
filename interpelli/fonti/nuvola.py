"""Nuvola (Madisoft): interfaccia pubblica degli interpelli docenti."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from .. import rete
from ..analisi import classi_concorso, pulisci
from ..modello import Fonte, Interpello

BASE = "https://nuvola.madisoft.it"
ORDINI = {"INFANZIA": "infanzia", "PRIMARIA": "primaria",
          "SECONDARIA I GRADO": "secondaria_1", "SECONDARIA II GRADO": "secondaria_2"}


def _data(s):
    return datetime.fromisoformat(s) if s else None


def leggi(f: Fonte) -> list[Interpello]:
    codice = f.rif
    pagina = f"{BASE}/interpelli/{codice}/docenti"
    r = rete.get(pagina)
    if r is None or r.status_code != 200:
        raise RuntimeError(f"pagina Nuvola non raggiungibile ({getattr(r, 'status_code', 'rete')})")
    m = re.search(r'data-codice-cliente="([^"]+)"', r.text)
    if not m:
        raise RuntimeError("codice cliente Nuvola non trovato: la scuola potrebbe non usare più Nuvola")
    cliente = m.group(1)
    r = rete.get(f"{BASE}/api-public/amministrazione-digitale/{cliente}/interpelli-docente")
    if r is None or r.status_code != 200:
        raise RuntimeError("elenco interpelli Nuvola non disponibile")
    adesso = datetime.now(timezone.utc)
    out = []
    for it in r.json().get("results", []):
        inizio = _data(it.get("dataOraInizioPresentazioneCandidature"))
        fine = _data(it.get("dataOraScadenzaPresentazioneCandidature"))
        if (inizio and inizio > adesso) or (fine and fine < adesso):
            continue
        cdc_testo = it.get("classeDiConcorso") or ""
        note = it.get("annotazioni") or ""
        link_mod = re.findall(r"https?://\S+", note)
        ore = it.get("orarioCattedraOre")
        out.append(Interpello(
            istituto=f.istituto, provincia=f.provincia, codice_mecc=f.codice_mecc,
            titolo=pulisci(it.get("nome", "")), fonte="Nuvola",
            link_avviso=(f"{BASE}/file/api/public-file-preview/{cliente}/{it['decretoDiEmissioneInterpello']}"
                         if it.get("decretoDiEmissioneInterpello") else pagina),
            link_candidatura=link_mod[0].rstrip('."') if link_mod else pagina,
            classi=classi_concorso(cdc_testo) or [], classe_testo=cdc_testo,
            ordine=ORDINI.get((it.get("ordineDiScuola") or "").upper(), ""),
            ore=str(ore) if ore else None,
            scadenza=fine.astimezone().replace(tzinfo=None) if fine else None,
            pubblicato=inizio.date() if inizio else None,
            note=("Interpello preventivo (disponibilità per supplenze future)" if it.get("isPreventivo") else ""),
        ))
    return out
