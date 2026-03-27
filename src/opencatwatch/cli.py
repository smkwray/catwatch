from __future__ import annotations

from pathlib import Path

import typer

from .config import get_settings
from .pipelines.quality import (
    audit_processed_data,
    build_manual_review_queue,
    run_release_check,
    validate_public_snapshot,
)
from .pipelines.registry import build_registry
from .pipelines.site_data import build_site_data, write_demo_dashboard
from .pipelines.watchlist import build_watchlist
from .sources.bma import fetch_bma_for_names, infer_names_from_bsx
from .sources.bsx import fetch_bsx_ils
from .sources.ibtracs import fetch_ibtracs_csv
from .sources.noaa_stormevents import fetch_stormevents_files
from .sources.nws import fetch_nws_alerts
from .sources.openfema import fetch_fema_disaster_declarations
from .sources.sec import fetch_sec_for_sponsors
from .sources.usgs import fetch_usgs_events

app = typer.Typer(help="OpenCatWatch CLI")


@app.command("fetch-bsx")
def fetch_bsx(
    max_pages: int | None = typer.Option(
        None,
        help="Optional page cap for debugging. Omit to crawl the full BSX ILS listing.",
    ),
    force: bool = False,
) -> None:
    settings = get_settings()
    normalized_max_pages = max_pages if (max_pages or 0) > 0 else None
    result = fetch_bsx_ils(settings=settings, max_pages=normalized_max_pages, force=force)
    if normalized_max_pages is not None:
        typer.echo("warning: BSX crawl was page-limited; downstream registry/watchlist may be incomplete")
    typer.echo(f"saved {len(result)} BSX records")


@app.command("fetch-bma")
def fetch_bma(names_file: Path | None = None) -> None:
    settings = get_settings()
    names = []
    if names_file and names_file.exists():
        names = [line.strip() for line in names_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        names = infer_names_from_bsx(settings)
    result = fetch_bma_for_names(settings=settings, names=names)
    typer.echo(
        f"saved {result.get('matches', 0)} BMA matches and {result.get('review_candidates', 0)} ranked review candidates"
    )


@app.command("fetch-sec")
def fetch_sec(
    sponsors_csv: Path = Path("seeds/sponsor_universe_template.csv"),
    download_docs: bool = True,
    max_docs_per_sponsor: int = 2,
    spv_terms_file: Path | None = None,
    unresolved_terms_file: Path | None = None,
) -> None:
    settings = get_settings()
    result = fetch_sec_for_sponsors(
        settings=settings,
        sponsors_csv=sponsors_csv,
        download_docs=download_docs,
        max_docs_per_sponsor=max_docs_per_sponsor,
        extra_terms_file=spv_terms_file,
        unresolved_terms_file=unresolved_terms_file,
    )
    typer.echo(
        f"saved {result.get('filings', 0)} filing rows, scanned {result.get('docs_scanned', 0)} docs, {result.get('hits', 0)} evidence hits, {result.get('spv_links', 0)} SPV links"
    )


@app.command("fetch-stormevents")
def fetch_stormevents(year_start: int = 2024, year_end: int = 2025) -> None:
    settings = get_settings()
    result = fetch_stormevents_files(settings=settings, year_start=year_start, year_end=year_end)
    typer.echo(f"downloaded {len(result)} Storm Events files")


@app.command("fetch-nws")
def fetch_nws() -> None:
    settings = get_settings()
    result = fetch_nws_alerts(settings=settings)
    typer.echo(f"saved {len(result)} NWS alerts")


@app.command("fetch-ibtracs")
def fetch_ibtracs(kind: str = "active") -> None:
    settings = get_settings()
    path = fetch_ibtracs_csv(settings=settings, kind=kind)
    typer.echo(f"downloaded {path}")


@app.command("fetch-usgs")
def fetch_usgs(days: int = 14, min_magnitude: float = 5.5) -> None:
    settings = get_settings()
    result = fetch_usgs_events(settings=settings, days=days, min_magnitude=min_magnitude)
    typer.echo(f"saved {len(result)} USGS events")


@app.command("fetch-fema")
def fetch_fema() -> None:
    settings = get_settings()
    path = fetch_fema_disaster_declarations(settings=settings)
    typer.echo(f"downloaded {path}")


@app.command("build-registry")
def build_registry_cmd() -> None:
    settings = get_settings()
    result = build_registry(settings=settings)
    typer.echo(f"saved {result}")


@app.command("build-watchlist")
def build_watchlist_cmd() -> None:
    settings = get_settings()
    result = build_watchlist(settings=settings)
    typer.echo(f"saved {result}")


@app.command("build-site")
def build_site_cmd() -> None:
    settings = get_settings()
    result = build_site_data(settings=settings)
    typer.echo(f"saved {result}")


@app.command("audit-data")
def audit_data_cmd() -> None:
    settings = get_settings()
    result = audit_processed_data(settings=settings)
    typer.echo(f"saved {result}")


@app.command("build-review-queue")
def build_review_queue_cmd(limit: int = 250) -> None:
    settings = get_settings()
    result = build_manual_review_queue(settings=settings, limit=limit)
    typer.echo(f"saved {result}")


@app.command("release-check")
def release_check_cmd() -> None:
    settings = get_settings()
    result = run_release_check(settings=settings)
    typer.echo(f"release check passed: {result}")


@app.command("validate-public-snapshot")
def validate_public_snapshot_cmd() -> None:
    settings = get_settings()
    result = validate_public_snapshot(settings=settings)
    typer.echo(f"public snapshot validation passed: {result}")


@app.command("refresh-all")
def refresh_all(
    stormevents_year_start: int = 2024,
    stormevents_year_end: int = 2025,
    usgs_days: int = 14,
    usgs_min_magnitude: float = 5.5,
) -> None:
    settings = get_settings()
    fetch_bsx_ils(settings=settings, max_pages=None, force=False)
    fetch_bma_for_names(settings=settings, names=infer_names_from_bsx(settings))
    fetch_sec_for_sponsors(
        settings=settings,
        sponsors_csv=Path("seeds/sponsor_universe_template.csv"),
        download_docs=True,
        max_docs_per_sponsor=2,
    )
    fetch_nws_alerts(settings=settings)
    fetch_usgs_events(settings=settings, days=usgs_days, min_magnitude=usgs_min_magnitude)
    fetch_ibtracs_csv(settings=settings, kind="active")
    fetch_fema_disaster_declarations(settings=settings)
    fetch_stormevents_files(settings=settings, year_start=stormevents_year_start, year_end=stormevents_year_end)
    build_registry(settings=settings)
    build_watchlist(settings=settings)
    build_site_data(settings=settings)
    audit_processed_data(settings=settings)
    build_manual_review_queue(settings=settings)
    typer.echo("refresh complete")


@app.command("demo-site-data")
def demo_site_data() -> None:
    settings = get_settings()
    result = write_demo_dashboard(settings=settings)
    typer.echo(f"saved {result}")


if __name__ == "__main__":
    app()
