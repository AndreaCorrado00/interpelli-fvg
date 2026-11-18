"""Accesso HTTP: una sola sessione, pause brevi tra le richieste, nessun tentativo aggressivo."""
from __future__ import annotations

import time
from typing import Optional

import requests

from . import robots


class VietatoDaRobots(Exception):
    """La pagina è esclusa dal robots.txt del sito: non la leggiamo."""

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


MAX_SECONDI = 60          # tempo massimo per scaricare una singola risorsa
MAX_BYTE = 15_000_000


def _scarica(url: str, timeout: int, **kw) -> requests.Response:
    """GET con limite di tempo complessivo: un server lentissimo non blocca tutto il controllo."""
    r = _sessione.get(url, timeout=(10, timeout), stream=True, **kw)
    fine = time.monotonic() + MAX_SECONDI
    dati = bytearray()
    try:
        for blocco in r.iter_content(65536):
            dati += blocco
            if time.monotonic() > fine or len(dati) > MAX_BYTE:
                raise requests.Timeout(f"download troppo lento o troppo grande: {url}")
    finally:
        r.close()
    r._content = bytes(dati)
    return r


def _grezzo(url: str) -> Optional[requests.Response]:
    _attendi()
    try:
        return _scarica(url, 15)
    except requests.RequestException:
        return None


def get(url: str, *, timeout: int = 30, tentativi: int = 2, **kw) -> Optional[requests.Response]:
    """GET rispettando robots.txt; nuovo tentativo solo per errori di rete o 5xx. None se fallisce."""
    if not robots.consentito(url, _grezzo):
        raise VietatoDaRobots(url)
    for i in range(tentativi):
        _attendi()
        try:
            r = _scarica(url, timeout, **kw)
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
    if not robots.consentito(url, _grezzo):
        raise VietatoDaRobots(url)
    _attendi()
    try:
        return _sessione.post(url, json=dati, timeout=(10, timeout))
    except requests.RequestException:
        return None
