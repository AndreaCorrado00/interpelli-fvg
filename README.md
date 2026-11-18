# Interpelli FVG

Controllo automatico degli interpelli per docenti nelle scuole medie e superiori delle province di
Udine, Pordenone e Gorizia. Due volte al giorno (circa 7:30 e 17:00) manda a ogni destinatario una
mail con gli interpelli **ancora aperti** per le sue classi di concorso: istituto, classe di concorso,
materia, ore, scadenza e link per candidarsi. Se non ce ne sono, la mail dice "non ci sono interpelli
aperti oggi".

Gira su GitHub Actions: non serve tenere acceso nessun computer e non serve installare nulla.

## Cosa controlla

`config/fonti.csv` contiene una riga per ogni fonte (113 istituti, 149 fonti):

| tipo | cosa legge |
|---|---|
| `nuvola` | modulo interpelli di Nuvola (dati strutturati: classe, ore, scadenza) |
| `scuola` | home del sito della scuola e pagine interpelli più comuni (`/pagine/interpelli`, ecc.) |
| `manuale` | nessuna fonte automatica: la scuola compare nella mail tra quelle da controllare a mano |
| `argo_albo` | albo online Argo, stesso criterio |
| `axios_albo` | albo online Axios (trasparenzascuole.it) |
| `sito` | pagina "interpelli" nota sul sito della scuola |

Per gli avvisi pubblicati all'albo lo script apre il PDF e ricava classe di concorso, ore, scadenza
e indirizzo mail per la candidatura. Scarta esiti, individuazioni, graduatorie, annullamenti, avvisi
per ATA, esperti e tutor, e gli interpelli già scaduti. In fondo alla mail c'è sempre l'elenco delle
fonti che quel giorno non hanno risposto.

## Cambiare destinatari e filtri

Modificare `config/destinatari.yaml` direttamente da GitHub (icona della matita):

```yaml
destinatari:
  - nome: Andrea
    email: indirizzo@gmail.com
    classi: [A028, A026]          # vuoto = tutte le classi di concorso
    ordini: [secondaria_1, secondaria_2]
```

Le materie mostrate nella mail vengono da `config/classi_concorso.csv`.

## Configurazione iniziale (una volta sola)

1. Su Google: Account → Sicurezza → Verifica in due passaggi attiva → **Password per le app** →
   creare una password chiamata "Interpelli".
2. Sul repository: Settings → Secrets and variables → Actions → New repository secret:
   - `GMAIL_USER`: l'indirizzo Gmail da cui partono le mail
   - `GMAIL_APP_PASSWORD`: la password per app (16 lettere, senza spazi)
3. Actions → "Interpelli FVG" → Run workflow, con "Solo prova" spuntato: il riepilogo compare nel log
   e come file scaricabile, senza inviare mail.

## Avvio manuale

Actions → "Interpelli FVG" → Run workflow. Senza "Solo prova" manda le mail come nelle esecuzioni
programmate.

In locale: `pip install -r requirements.txt` poi `python -m interpelli --prova`
(`--solo Malignani` per controllare un solo istituto).

## Limiti noti

- **Spaggiari e Axios** proteggono i loro server con Cloudflare e bloccano i programmi automatici; i siti
  scolastici fatti con Spaggiari escludono l'albo (`/albo-online`) nel robots.txt. Lo script rispetta
  entrambe le cose: per queste scuole legge solo le sezioni consentite (home, `/pagine/`, `/servizi`) dove
  molte scuole pubblicano gli interpelli. Le scuole in cui non trova una pagina interpelli compaiono in
  fondo alla mail, con il link all'albo da controllare a mano.
- Per gli avvisi che stanno su Spaggiari la scadenza non viene letta: la mail riporta "vedi avviso".
- Le scadenze ricavate dai PDF possono mancare se l'avviso è una scansione o scrive la data in modo insolito.
- Fonti ancora da trovare: ISIS D'Annunzio-Fabiani (dominio non più della scuola), ISIS Galilei-Cossar
  (certificato del sito non valido), siti di IC Della Torre-Verni e IC Cormons.
- I link di alcune pagine cambiano ogni anno scolastico (es. Liceo Stellini): vanno aggiornati a settembre.
