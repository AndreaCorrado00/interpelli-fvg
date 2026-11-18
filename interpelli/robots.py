"""Rispetto di robots.txt (regole per tutti gli agenti, '*'), con la logica usata dai motori di ricerca:
vince la regola più lunga che corrisponde; a parità vince Allow; '*' e '$' sono supportati."""
from __future__ import annotations

import re
from urllib.parse import urlsplit

_cache: dict[str, list[tuple[bool, re.Pattern, int]]] = {}


def _compila(percorso: str) -> re.Pattern:
    fine = percorso.endswith("$")
    corpo = re.escape(percorso[:-1] if fine else percorso).replace(r"\*", ".*")
    return re.compile("^" + corpo + ("$" if fine else ""))


def _analizza(testo: str) -> list[tuple[bool, re.Pattern, int]]:
    gruppi, attuale, agenti, in_regole = {}, None, [], False
    for riga in testo.splitlines():
        riga = riga.split("#", 1)[0].strip()
        if ":" not in riga:
            continue
        chiave, valore = (x.strip() for x in riga.split(":", 1))
        chiave = chiave.lower()
        if chiave == "user-agent":
            if in_regole:
                agenti, in_regole = [], False
            agenti.append(valore.lower())
            for a in agenti:
                gruppi.setdefault(a, [])
        elif chiave in ("allow", "disallow"):
            in_regole = True
            if chiave == "disallow" and not valore:
                continue
            for a in agenti:
                gruppi.setdefault(a, []).append((chiave == "allow", _compila(valore), len(valore)))
    return gruppi.get("*", [])


def consentito(url: str, scarica) -> bool:
    parti = urlsplit(url)
    host = f"{parti.scheme}://{parti.netloc}"
    if host not in _cache:
        r = scarica(host + "/robots.txt")
        if r is not None and r.status_code == 200 and "text/html" not in r.headers.get("content-type", ""):
            _cache[host] = _analizza(r.text)
        else:
            _cache[host] = []
    percorso = parti.path or "/"
    if parti.query:
        percorso += "?" + parti.query
    migliore = None
    for permesso, rx, lung in _cache[host]:
        if rx.match(percorso) and (migliore is None or lung > migliore[1] or (lung == migliore[1] and permesso)):
            migliore = (permesso, lung)
    return True if migliore is None else migliore[0]
