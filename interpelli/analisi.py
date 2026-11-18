"""Riconoscimento di interpelli nei titoli e lettura degli avvisi (testo o PDF)."""
from __future__ import annotations

import io
import re
from datetime import date, datetime
from typing import Optional

from pypdf import PdfReader

# --- Riconoscere un avviso di interpello per docenti dal titolo ------------------------------

INCLUDI = re.compile(
    r"interpell|supplenz\w*\s+fuori\s+graduatori|reperimento\s+di\s+(personale\s+)?docent|"
    r"avviso\s+(pubblico\s+)?per\s+(il\s+)?(conferimento|reclutamento)\s+di\s+(una\s+)?supplenz|"
    r"(avviso|ricerca|disponibilit\w*|richiesta)\b.{0,40}supplenz|supplenz\w*\s+(docent|temporane|brev|annual|fino\s+al|per\s+(la\s+)?(classe|cdc|c\.d\.c))",
    re.I,
)
ESCLUDI = re.compile(
    r"esit[oi]\b|individuazion|individuat|graduatori[ae]\s+(provvisori|definitiv|candidat|interpell)|"
    r"pubblicazione\s+graduatori|approvazione\s+graduatori|annullament|revoca|valutazione\s+(istanze|candidature|domande)|"
    r"decreto\s+di\s+nomina|nomina\s+commission|commissione|collaborator\w*\s+scolastic|\bcs\b|"
    r"assistent\w*\s+(tecnic|amministrativ)|\bata\b|dsga|\bd\.s\.g\.a|funzionari|esperto|esperti|tutor|"
    r"animatore|informativa|privacy|modello\s+di\s+domanda|modulo\s+domanda|dispositivo\s+(di\s+)?convocazione|"
    r"assegnazione|presa\s+di\s+servizio|contratto\s+a\s+t|interpello[\s-]+nazionale|allegat[oi][\s-]*\d|modulistic",
    re.I,
)


def e_interpello_docenti(titolo: str) -> bool:
    return bool(INCLUDI.search(titolo)) and not ESCLUDI.search(titolo)


# --- Classi di concorso -----------------------------------------------------------------------

_CDC_3 = re.compile(r"\b([AB])\s?-?\s?(0\d{2})\b")                      # A026, B003, A-026
_CDC_TRATTINO = re.compile(r"\b([AB])\s?-\s?(\d{2})\b")                     # A-28, B-14
_CDC_LETT = re.compile(r"\b(A[A-Z]\d{2}|B[A-D]0\d|AD(?:SS|MM|EE|AA)|AAAA|EEEE|AS2A)\b")
_CDC_2 = re.compile(r"(?:classe\s+di\s+concorso|cl(?:asse)?\.?\s*(?:di\s+)?conc\.?|c\.?d\.?c\.?|cdc)\s*:?\s*"
                    r"([AB])\s?-?\s?(\d{2,3})\b", re.I)


def classi_concorso(testo: str) -> list[str]:
    testo = testo.replace("_", " ").replace("%20", " ")
    trovate: list[str] = []
    for m in _CDC_2.finditer(testo):
        trovate.append(f"{m.group(1).upper()}{int(m.group(2)):03d}")
    for m in _CDC_3.finditer(testo):
        trovate.append(f"{m.group(1)}{m.group(2)}")
    for m in _CDC_TRATTINO.finditer(testo):
        trovate.append(f"{m.group(1)}{int(m.group(2)):03d}")
    for m in _CDC_LETT.finditer(testo):
        trovate.append(m.group(1).upper())
    visti, out = set(), []
    for c in trovate:
        if c not in visti:
            visti.add(c)
            out.append(c)
    return out


def ordine_da(classi: list[str], testo: str) -> str:
    t = testo.lower()
    if any(c in ("AAAA", "ADAA") for c in classi) or re.search(r"infanzia", t) and not re.search(r"secondaria", t):
        if not re.search(r"primaria", t):
            return "infanzia"
    if any(c in ("EEEE", "ADEE") for c in classi) or (re.search(r"primaria", t) and not re.search(r"secondaria", t)):
        return "primaria"
    if "ADMM" in classi or re.search(r"secondaria\s+(di\s+)?(i|1|primo)\b|\bsecondaria\s+di\s+i\s+grado|scuola\s+media", t):
        return "secondaria_1"
    if "ADSS" in classi or re.search(r"secondaria\s+(di\s+)?(ii|2|secondo)\b|istituto\s+(superiore|tecnico|professionale)|liceo", t):
        return "secondaria_2"
    if classi or re.search(r"secondaria", t):
        return "secondaria"   # classe A0xx/B0xx senza altre indicazioni: medie o superiori
    return ""


# --- Ore, scadenza, contatti ------------------------------------------------------------------

_ORE = [
    re.compile(r"(\d{1,2})\s*(?:/\s*18\s*)?(?:ore|h)\s+settimanal", re.I),
    re.compile(r"ore\s+settimanali\s*:?\s*(\d{1,2})", re.I),
    re.compile(r"orario\s*(?:settimanale|cattedra)?\s*:?\s*(\d{1,2})\s*(?:ore|h)", re.I),
    re.compile(r"(\d{1,2})\s*(?:ore|h)\b", re.I),
]


def ore_da(testo: str) -> Optional[str]:
    for rx in _ORE:
        m = rx.search(testo)
        if m and 1 <= int(m.group(1)) <= 36:
            return m.group(1)
    if re.search(r"cattedra\s+(intera|completa)", testo, re.I):
        return "18"
    return None


MESI = {m: i for i, m in enumerate(
    ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
     "settembre", "ottobre", "novembre", "dicembre"], start=1)}

_DATA_NUM = r"(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{2,4})"
_DATA_TXT = r"(\d{1,2})\s+(" + "|".join(MESI) + r")\s+(\d{4})"
_ORA = r"(?:ore\s*(\d{1,2})(?:[.:,](\d{2}))?)"
_SCAD = re.compile(
    r"(?:entro|scadenza|termine|non\s+oltre|fino\s+alle)[^.\n]{0,60}?"
    r"(?:" + _ORA + r"[^.\n]{0,25}?)?"
    r"(?:" + _DATA_NUM + "|" + _DATA_TXT + r")"
    r"(?:[^.\n]{0,15}?" + _ORA + r")?",
    re.I,
)


def _anno(a: str) -> int:
    a_ = int(a)
    return a_ + 2000 if a_ < 100 else a_


def scadenza_da(testo: str, dopo: Optional[date] = None) -> Optional[datetime]:
    """Prima data dopo 'entro/scadenza/termine' (successiva alla pubblicazione, se nota)."""
    candidati: list[datetime] = []
    for m in _SCAD.finditer(testo):
        g = m.groups()
        hh, mm = g[0], g[1]
        try:
            if g[2]:
                d = datetime(_anno(g[4]), int(g[3]), int(g[2]))
            else:
                d = datetime(int(g[7]), MESI[g[6].lower()], int(g[5]))
        except (ValueError, TypeError, KeyError):
            continue
        hh = hh or g[8]
        mm = mm or g[9]
        if hh and int(hh) < 24:
            d = d.replace(hour=int(hh), minute=int(mm or 0))
        else:
            d = d.replace(hour=23, minute=59)
        if dopo and d.date() < dopo:
            continue
        candidati.append(d)
    return min(candidati) if candidati else None


_EMAIL = re.compile(r"[\w.+-]+@(?:pec\.)?istruzione\.it|[\w.+-]+@[\w-]+\.(?:edu\.)?it", re.I)


_EMAIL_SCUOLA = re.compile(r"[\w.+-]+@(?:pec\.)?istruzione\.it|[\w.+-]+@[\w-]+\.edu\.it", re.I)


def email_da(testo: str) -> str:
    """Solo indirizzi della scuola (istruzione.it o .edu.it): niente mail di fornitori dal piè di pagina."""
    m = re.search(r"(?:istanz|domand|candidatur|inviare|inoltrare|mail)[^@]{0,120}?(" + _EMAIL_SCUOLA.pattern + ")",
                  testo, re.I)
    if m:
        return m.group(1).lower()
    m = _EMAIL_SCUOLA.search(testo)
    return m.group(0).lower() if m else ""


def testo_pdf(dati: bytes, max_pagine: int = 4) -> str:
    try:
        lettore = PdfReader(io.BytesIO(dati))
        return "\n".join((p.extract_text() or "") for p in lettore.pages[:max_pagine])
    except Exception:
        return ""


def pulisci(t: str) -> str:
    return re.sub(r"\s+", " ", t or "").strip()
