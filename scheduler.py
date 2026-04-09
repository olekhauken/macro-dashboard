"""
scheduler.py
============
Kjører datahenting automatisk én gang per dag ved hjelp av APScheduler.

Hvorfor en scheduler i stedet for cron?
----------------------------------------
APScheduler kjører *inni* Python-prosessen, så vi trenger ikke sette opp
en ekstern cron-jobb på serveren. Det gjør koden portabel – den oppfører
seg likt lokalt og på Railway.

Ulempen: Scheduleren kjøres bare mens app-prosessen er oppe. Hvis appen
krasjer og restartes midt på natten, starter scheduleren på nytt og vil
kjøre neste innhentingstidspunkt.

Bruk
----
Scheduleren startes automatisk når `app.py` importerer og kaller `start()`.
Du kan også kjøre en engangsinnhenting direkte:

    python scheduler.py
"""

import logging
from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)


def fetch_all_sources() -> None:
    """
    Henter data fra alle registrerte datakilder.

    Kalles automatisk av scheduleren én gang per dag.
    Legger du til nye fetchers, registrer dem her.
    """
    from data.fetchers.fetch_market import MarketFetcher

    sources = [
        ("market", MarketFetcher),
        # ("rates",  RatesFetcher),   # Eksempel på fremtidig kilde
    ]

    for name, FetcherClass in sources:
        try:
            logger.info("Fetching %s...", name)
            fetcher = FetcherClass()
            data = fetcher.fetch()
            fetcher.save(data)
            logger.info("Done: %s (%d items)", name, len(data))
        except Exception as exc:
            # Log og fortsett – én feilende kilde skal ikke stoppe de andre.
            logger.error("Failed to fetch %s: %s", name, exc, exc_info=True)


def start() -> BackgroundScheduler:
    """
    Starter scheduleren som bakgrunnstråd.

    Datahenting kjøres:
    - Umiddelbart ved oppstart (så dashboardet alltid har ferske data)
    - Deretter daglig kl. 18:30 CET (etter Oslo Børs stenger kl. 16:30)

    Returns
    -------
    BackgroundScheduler
        Den kjørende scheduler-instansen (kan stoppes med scheduler.shutdown()).
    """
    scheduler = BackgroundScheduler(timezone="Europe/Oslo")

    scheduler.add_job(
        fetch_all_sources,
        trigger="cron",
        hour=18,
        minute=30,
        id="daily_market_fetch",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started. Next run: %s", scheduler.get_job("daily_market_fetch").next_run_time)

    # Kjør en engangssjekk 5 sekunder etter oppstart som en egen jobb.
    # Hvorfor ikke kalle _fetch_if_stale() direkte her?
    # → _fetch_if_stale() kaller yf.download() som tar 10–20 sek og blokkerer
    #   gunicorn-oppstarten. Railway tolker dette som at appen henger og dreper
    #   prosessen. Ved å legge det inn som en "date"-jobb starter gunicorn
    #   umiddelbart, og datahentingen skjer i bakgrunnen 5 sek etterpå.
    from datetime import datetime, timedelta
    scheduler.add_job(
        _fetch_if_stale,
        trigger="date",
        run_date=datetime.now() + timedelta(seconds=5),
        id="startup_fetch",
        replace_existing=True,
    )

    return scheduler


def _fetch_if_stale() -> None:
    """
    Sjekker om market.json eksisterer og er fra i dag.
    Hvis ikke, henter vi data med en gang.
    """
    import json
    from pathlib import Path
    from datetime import date

    store = Path("data/store/market.json")
    if not store.exists():
        logger.info("No market data found – fetching now...")
        fetch_all_sources()
        return

    # Sjekk last_updated i filen
    try:
        data = json.loads(store.read_text(encoding="utf-8"))
        if data:
            last_updated = data[0].get("last_updated", "")[:10]  # "YYYY-MM-DD"
            if last_updated == str(date.today()):
                logger.info("Market data is up to date (from %s).", last_updated)
                return
    except Exception:
        pass  # Korrupt fil – hent på nytt

    logger.info("Market data is stale – fetching now...")
    fetch_all_sources()


# ---------------------------------------------------------------------------
# Kjøres direkte for engangsinnhenting
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )
    print("Running one-time fetch of all data sources...")
    fetch_all_sources()
    print("Done.")
