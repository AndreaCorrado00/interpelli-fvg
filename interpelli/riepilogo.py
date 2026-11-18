"""Filtri per destinatario e testo della mail."""
from __future__ import annotations

import csv
import html
from datetime import date
from pathlib import Path

from .modello import Interpello

ORDINI_DEFAULT = ["secondaria_1", "secondaria_2"]
NOMI_ORDINE = {"secondaria_1": "Medie", "secondaria_2": "Superiori", "secondaria": "Medie/superiori",
               "primaria": "Primaria", "infanzia": "Infanzia", "": "Non indicato"}


def carica_materie(percorso: Path) -> dict[str, str]:
    with open(percorso, newline="", encoding="utf-8") as fh:
        return {r["codice"].strip().upper(): r["materia"].strip() for r in csv.DictReader(fh)}


def filtra(aperti: list[Interpello], d: dict) -> tuple[list[Interpello], list[Interpello]]:
    """(interpelli delle classi del destinatario, interpelli senza classe riconosciuta da controllare)."""
    ordini = set(d.get("ordini") or ORDINI_DEFAULT)
    classi = {c.upper() for c in (d.get("classi") or [])}
    ok, dubbi = [], []
    for it in aperti:
        if it.ordine in ("infanzia", "primaria") and it.ordine not in ordini:
            continue
        if it.ordine in ("secondaria_1", "secondaria_2") and it.ordine not in ordini:
            continue
        if not classi:
            (ok if it.classi or it.classe_testo else dubbi).append(it)
        elif set(it.classi) & classi:
            ok.append(it)
        elif not it.classi and d.get("mostra_senza_classe", True):
            dubbi.append(it)
    ordina = lambda x: (x.scadenza.isoformat() if x.scadenza else "9999", x.provincia, x.istituto)
    return sorted(ok, key=ordina), sorted(dubbi, key=ordina)


def _materia(it: Interpello, materie: dict[str, str]) -> str:
    nomi = [materie.get(c, "") for c in it.classi]
    nomi = [n for n in nomi if n]
    return "; ".join(nomi) or it.classe_testo or "—"


def _scad(it: Interpello) -> str:
    if not it.scadenza:
        return "non indicata"
    s = it.scadenza.strftime("%d/%m/%Y")
    if (it.scadenza.hour, it.scadenza.minute) != (23, 59):
        s += it.scadenza.strftime(" ore %H:%M")
    return s


def _riga_txt(it: Interpello, materie, nuovi: set) -> str:
    righe = [
        f"- {it.istituto} ({it.provincia}){'  [NUOVO]' if it.chiave in nuovi else ''}",
        f"  Classe di concorso: {', '.join(it.classi) or it.classe_testo or 'non indicata'}",
        f"  Materia: {_materia(it, materie)}",
        f"  Ore: {it.ore or 'non indicate'}   Scadenza: {_scad(it)}",
        f"  Candidatura: {it.link_candidatura.replace('mailto:', 'mail a ')}",
    ]
    if it.link_avviso and it.link_avviso != it.link_candidatura:
        righe.append(f"  Avviso: {it.link_avviso}")
    if it.note:
        righe.append(f"  Nota: {it.note}")
    return "\n".join(righe)


def _tabella_html(elenco: list[Interpello], materie, nuovi: set) -> str:
    e = html.escape
    th = "".join(f"<th style='text-align:left;padding:6px;border-bottom:1px solid #ccc'>{t}</th>"
                 for t in ("Istituto", "Classe di concorso", "Materia", "Ore", "Scadenza", "Candidatura"))
    righe = []
    for it in elenco:
        cand = it.link_candidatura
        testo_cand = it.email_candidatura or "Candidati"
        avviso = (f"<br><a href='{e(it.link_avviso)}'>Avviso</a>"
                  if it.link_avviso and it.link_avviso != cand else "")
        nuovo = " <b style='color:#b45309'>NUOVO</b>" if it.chiave in nuovi else ""
        nota = f"<div style='color:#666;font-size:12px'>{e(it.note)}</div>" if it.note else ""
        td = "style='padding:6px;border-bottom:1px solid #eee;vertical-align:top'"
        righe.append(
            f"<tr><td {td}><b>{e(it.istituto)}</b> ({e(it.provincia)}){nuovo}"
            f"<div style='color:#666;font-size:12px'>{e(it.titolo[:160])}</div>{nota}</td>"
            f"<td {td}>{e(', '.join(it.classi) or it.classe_testo or 'non indicata')}</td>"
            f"<td {td}>{e(_materia(it, materie))}</td>"
            f"<td {td}>{e(it.ore or '—')}</td>"
            f"<td {td}>{e(_scad(it))}</td>"
            f"<td {td}><a href='{e(cand)}'>{e(testo_cand)}</a>{avviso}</td></tr>")
    return (f"<table style='border-collapse:collapse;font-family:sans-serif;font-size:14px'>"
            f"<tr>{th}</tr>{''.join(righe)}</table>")


def componi(d: dict, miei: tuple, tutti_aperti: list, stato: dict, materie: dict, errori: list[str],
            n_fonti: int) -> tuple[str, str, str]:
    ok, dubbi = miei
    nuovi = {it.chiave for it in ok + dubbi if it.chiave not in stato}
    oggi = date.today().strftime("%d/%m/%Y")
    classi = ", ".join(d.get("classi") or []) or "tutte le classi di concorso"
    if ok:
        oggetto = f"Interpelli aperti {oggi}: {len(ok)}" + (f" ({len(nuovi)} nuovi)" if nuovi else "")
    else:
        oggetto = f"Interpelli {oggi}: non ci sono interpelli aperti oggi"

    txt = [f"Ciao {d['nome']},", ""]
    htm = [f"<div style='font-family:sans-serif;font-size:14px'><p>Ciao {html.escape(d['nome'])},</p>"]
    if ok:
        txt.append(f"Interpelli aperti oggi per {classi}:\n")
        txt += [_riga_txt(it, materie, nuovi) + "\n" for it in ok]
        htm.append(f"<p>Interpelli aperti oggi per <b>{html.escape(classi)}</b>:</p>")
        htm.append(_tabella_html(ok, materie, nuovi))
    else:
        txt.append(f"Non ci sono interpelli aperti oggi per {classi}.")
        htm.append(f"<p><b>Non ci sono interpelli aperti oggi</b> per {html.escape(classi)}.</p>")

    if dubbi:
        txt.append("\nInterpelli aperti in cui la classe di concorso non è scritta nel titolo (da controllare):\n")
        txt += [_riga_txt(it, materie, nuovi) + "\n" for it in dubbi]
        htm.append("<p style='margin-top:24px'>Interpelli aperti in cui la classe di concorso non è "
                   "scritta nel titolo, da controllare:</p>")
        htm.append(_tabella_html(dubbi, materie, nuovi))

    pie = (f"Fonti controllate: {n_fonti - len(errori)} su {n_fonti}. "
           f"Interpelli aperti per medie e superiori in totale: "
           f"{sum(1 for x in tutti_aperti if x.ordine not in ('infanzia', 'primaria'))}.")
    txt.append("\n" + pie)
    htm.append(f"<p style='color:#666;font-size:12px;margin-top:24px'>{html.escape(pie)}")
    if errori:
        txt.append("Fonti non raggiungibili oggi:\n" + "\n".join(f"  - {e}" for e in errori))
        htm.append("<br>Fonti non raggiungibili oggi:<br>" + "<br>".join(html.escape(e) for e in errori))
    htm.append("</p></div>")
    return oggetto, "\n".join(htm), "\n".join(txt)
