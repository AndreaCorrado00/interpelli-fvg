"""Accesso HTTP: una sola sessione, pause brevi tra le richieste, nessun tentativo aggressivo."""
from __future__ import annotations

import time
from typing import Optional

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130.0.0.0 Safari/537.36")

_sessione = requests.Session()
_sessione.headers.update({
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
})
_ultima = 0.0
PAUSA = 0.6  # secondi tra una richiesta e l'altra


def _attendi() -> None:
    global _ultima
    dt = time.monotonic() - _ultima
    if dt < PAUSA:
        time.sleep(PAUSA - dt)
    _ultima = time.monotonic()


def get(url: str, *, timeout: int = 30, tentativi: int = 2, **kw) -> Optional[requests.Response]:
    """GET con un nuovo tentativo solo per errori di rete o 5xx. Restituisce None se fallisce."""
    for i in range(tentativi):
        _attendi()
        try:
            r = _sessione.get(url, timeout=timeout, **kw)
        except requests.RequestException:
            if i + 1 == tentativi:
                return None
            time.sleep(3)
            continue
        if r.status_code >= 500 and i + 1 < tentativi:
            time.sleep(3)
            continue
        return r
    return None


def post_json(url: str, dati: dict, *, timeout: int = 30) -> Optional[requests.Response]:
    _attendi()
    try:
        return _sessione.post(url, json=dati, timeout=timeout)
    except requests.RequestException:
        return None
