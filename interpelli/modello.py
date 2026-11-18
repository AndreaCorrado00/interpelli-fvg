"""Strutture dati comuni."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


@dataclass
class Fonte:
    """Una riga di config/fonti.csv."""
    provincia: str
    istituto: str
    codice_mecc: str
    tipo: str          # nuvola | spaggiari_interpelli | spaggiari_albo | argo_albo | axios_albo | sito
    rif: str           # codice piattaforma, GUID o URL a seconda del tipo
    link_pubblico: str = ""
    note: str = ""


@dataclass
class Interpello:
    istituto: str
    provincia: str
    codice_mecc: str
    titolo: str
    fonte: str                                   # es. "Nuvola", "Albo Spaggiari"
    link_avviso: str = ""
    link_candidatura: str = ""
    classi: list[str] = field(default_factory=list)   # codici normalizzati, es. ["A026"]
    classe_testo: str = ""                       # descrizione così come la dà la piattaforma
    ordine: str = ""                             # infanzia | primaria | secondaria_1 | secondaria_2 | ""
    ore: Optional[str] = None
    scadenza: Optional[datetime] = None
    pubblicato: Optional[date] = None
    email_candidatura: str = ""
    note: str = ""

    @property
    def chiave(self) -> str:
        """Identificativo stabile per riconoscere un interpello già segnalato."""
        base = self.link_avviso or self.link_candidatura or ""
        titolo = re.sub(r"\W+", " ", self.titolo.lower()).strip()
        return hashlib.sha1(f"{self.codice_mecc}|{titolo}|{base}".encode()).hexdigest()[:16]
