"""Avvio: python -m interpelli [--prova] [--solo TESTO]

--prova   non invia mail: scrive il riepilogo in riepilogo.html e lo stampa a schermo
--solo    controlla solo le fonti il cui istituto contiene TESTO (utile per verifiche)
"""
from __future__ import annotations

import argparse
import csv
import faulthandler
import traceback
import threading
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

from .modello import Fonte, Interpello
from .fonti import argo, axios, nuvola, sito, spaggiari
from . import posta, rete, riepilogo

RADICE = Path(__file__).resolve().parent.parent
FILE_FONTI = RADICE / "config" / "fonti.csv"
FILE_DEST = RADICE / "config" / "destinatari.yaml"
FILE_CDC = RADICE / "config" / "classi_concorso.csv"
FILE_STATO = RADICE / "stato" / "visti.json"
GIORNI_SENZA_SCADENZA = 10   # avvisi senza scadenza leggibile: mostrati solo se pubblicati da poco


def carica_fonti(filtro: str = "") -> list[Fonte]:
    with open(FILE_FONTI, newline="", encoding="utf-8") as fh:
        righe = [Fonte(**{k: (v or "").strip() for k, v in r.items()}) for r in csv.DictReader(fh)]
    parti = [p.strip().lower() for p in filtro.split(",") if p.strip()]
    return [f for f in righe if not parti or any(p in f.istituto.lower() for p in parti)]


MAX_SECONDI_FONTE = 180


def con_limite(funz, arg, secondi):
    """Esegue funz(arg) in un thread separato: se non finisce entro `secondi` la fonte viene saltata."""
    esito = {}

    def corpo():
        try:
            esito["ok"] = funz(arg)
        except BaseException as e:   # riportato al chiamante
            esito["err"] = e

    t = threading.Thread(target=corpo, daemon=True)
    # se il blocco tiene fermo tutto l'interprete, faulthandler scrive comunque dove si trova
    faulthandler.dump_traceback_later(secondi + 30, repeat=True)
    t.start()
    t.join(secondi)
    faulthandler.cancel_dump_traceback_later()
    if t.is_alive():
        print(f"  ... {arg.istituto[:45]} bloccata da {secondi}s, punto in cui si trova:", flush=True)
        for riga in traceback.format_stack(sys._current_frames()[t.ident])[-4:]:
            print("      " + riga.strip().replace("\n", " | "), flush=True)
        raise RuntimeError(f"nessuna risposta entro {secondi} secondi")
    if "err" in esito:
        raise esito["err"]
    return esito["ok"]


def raccogli(fonti: list[Fonte]) -> tuple[list[Interpello], list[str], int, list[Fonte]]:
    """Legge tutte le fonti. Restituisce interpelli, errori, numero di fonti e scuole da controllare a mano."""
    trovati: list[Interpello] = []
    errori: list[str] = []
    coperti: set[str] = set()
    lettori = {
        "nuvola": nuvola.leggi,
        "spaggiari_interpelli": spaggiari.leggi_interpelli,
        "spaggiari_albo": spaggiari.leggi_albo,
        "argo_albo": argo.leggi_albo,
        "axios_albo": axios.leggi_albo,
    }
    def leggi_fonte(f):
        if f.tipo in ("sito", "scuola"):
            risultati, pagina_dedicata = sito.leggi(f)
            return risultati, f.tipo == "sito" or pagina_dedicata
        if f.tipo in lettori:
            return lettori[f.tipo](f), True
        raise RuntimeError(f"tipo di fonte sconosciuto: {f.tipo}")

    for f in fonti:
        if f.tipo == "manuale":      # nessuna fonte automatica: finisce nell'elenco da controllare a mano
            continue
        try:
            risultati, coperta = con_limite(leggi_fonte, f, MAX_SECONDI_FONTE)
            if coperta:
                coperti.add(f.istituto)
            trovati.extend(risultati)
            print(f"  ok  {f.tipo:22s} {f.istituto[:45]:45s} {len(risultati)}", flush=True)
        except rete.VietatoDaRobots:
            errori.append(f"{f.istituto} ({f.tipo}): pagina esclusa dal robots.txt")
            print(f"  NO  {f.tipo:22s} {f.istituto[:45]:45s} robots.txt", flush=True)
        except Exception as e:  # una fonte che non risponde non deve fermare le altre
            errori.append(f"{f.istituto} ({f.tipo}): {e}")
            print(f"  ERR {f.tipo:22s} {f.istituto[:45]:45s} {e}", flush=True)
    a_mano, visti = [], set()
    for f in fonti:
        if f.istituto not in coperti and f.istituto not in visti:
            visti.add(f.istituto)
            a_mano.append(f)
    return trovati, errori, len(fonti), a_mano


def ancora_aperto(it: Interpello, adesso: datetime) -> bool:
    if it.scadenza:
        return it.scadenza >= adesso
    if it.pubblicato:
        return it.pubblicato >= (adesso.date() - timedelta(days=GIORNI_SENZA_SCADENZA))
    return True   # dalle pagine dei siti, senza data: lo mostriamo segnalandolo


def deduplica(elenco: list[Interpello]) -> list[Interpello]:
    """Lo stesso interpello può comparire nel modulo Interpelli e nell'albo: tiene la versione più completa."""
    def punteggio(x: Interpello) -> int:
        return sum(bool(v) for v in (x.classi, x.ore, x.scadenza, x.email_candidatura)) + (x.fonte != "Sito della scuola")

    scelti: dict[tuple, Interpello] = {}
    for it in elenco:
        k = (it.codice_mecc, tuple(sorted(it.classi)) or it.titolo.lower()[:60],
             it.scadenza.date() if it.scadenza else None)
        if k not in scelti or punteggio(it) > punteggio(scelti[k]):
            scelti[k] = it
    return list(scelti.values())


def carica_stato() -> dict:
    try:
        return json.loads(FILE_STATO.read_text())
    except (OSError, ValueError):
        return {}


def salva_stato(stato: dict, aperti: list[Interpello]) -> None:
    oggi = date.today().isoformat()
    for it in aperti:
        stato.setdefault(it.chiave, oggi)
    limite = (date.today() - timedelta(days=180)).isoformat()
    stato = {k: v for k, v in stato.items() if v >= limite}
    FILE_STATO.parent.mkdir(exist_ok=True)
    FILE_STATO.write_text(json.dumps(stato, indent=1, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prova", action="store_true")
    ap.add_argument("--solo", default="")
    args = ap.parse_args()

    conf = yaml.safe_load(FILE_DEST.read_text(encoding="utf-8"))
    materie = riepilogo.carica_materie(FILE_CDC)
    fonti = carica_fonti(args.solo)
    print(f"Controllo {len(fonti)} fonti...", flush=True)
    t0 = time.time()
    trovati, errori, n_fonti, a_mano = raccogli(fonti)
    adesso = datetime.now()
    aperti = deduplica([it for it in trovati if ancora_aperto(it, adesso)])
    stato = carica_stato()
    print(f"Interpelli trovati: {len(trovati)}, aperti: {len(aperti)} ({time.time() - t0:.0f}s)", flush=True)

    for d in conf["destinatari"]:
        miei = riepilogo.filtra(aperti, d)
        oggetto, corpo_html, corpo_txt = riepilogo.componi(d, miei, aperti, stato, materie, errori, n_fonti, a_mano)
        if args.prova or not d.get("email") or not d.get("attivo", True):
            out = RADICE / f"riepilogo_{d['nome'].lower()}.html"
            out.write_text(corpo_html, encoding="utf-8")
            print(f"\n===== {d['nome']}: {oggetto}\n{corpo_txt}")
        else:
            posta.invia(d["email"], oggetto, corpo_html, corpo_txt)
            print(f"Mail inviata a {d['nome']}")

    if not args.prova and not args.solo:
        salva_stato(stato, aperti)
    return 0


if __name__ == "__main__":
    sys.exit(main())
