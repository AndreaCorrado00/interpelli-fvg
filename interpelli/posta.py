"""Invio della mail tramite Gmail (password per app nelle variabili d'ambiente)."""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


def invia(destinatario: str, oggetto: str, corpo_html: str, corpo_txt: str) -> None:
    utente = os.environ["GMAIL_USER"]
    password = os.environ["GMAIL_APP_PASSWORD"]
    msg = EmailMessage()
    msg["From"] = f"Interpelli FVG <{utente}>"
    msg["To"] = destinatario
    msg["Subject"] = oggetto
    msg.set_content(corpo_txt)
    msg.add_alternative(corpo_html, subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as s:
        s.login(utente, password)
        s.send_message(msg)
