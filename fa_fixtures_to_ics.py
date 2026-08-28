#!/usr/bin/env python3
"""
Stanwick Rovers FC — Division 2 Fixtures → ICS
Uses Playwright (real Chrome) to bypass Cloudflare and fetch from fulltime.thefa.com,
then parses the fixtures table and writes a fresh .ics calendar file.

Usage:
    python3 fa_fixtures_to_ics.py [output.ics]   (default: fixtures.ics)
"""

import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
SEASON_ID      = 477693916
FIXTURE_GROUP  = "1_748828336"
TEAM_NAME      = "Stanwick Rovers"
DEFAULT_KO     = "10:30"
DURATION_H     = 2
TIMEZONE       = "Europe/London"
CALENDAR_NAME  = "Stanwick Rovers — Div 2 Fixtures"
OUTPUT         = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("fixtures.ics")
# ─────────────────────────────────────────────────────────────────────────────


def _install(*pkgs):
    for pkg in pkgs:
        try:
            __import__(pkg.replace("-", "_").split("[")[0])
        except ImportError:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--quiet", pkg],
                check=True,
            )


_install("playwright", "beautifulsoup4", "icalendar", "pytz")

# Ensure Playwright's Chromium is installed
subprocess.run(
    [sys.executable, "-m", "playwright", "install", "chromium"],
    check=False, capture_output=True,
)

from playwright.sync_api import sync_playwright  # noqa: E402
from bs4 import BeautifulSoup                    # noqa: E402
from icalendar import Calendar, Event            # noqa: E402
import pytz                                      # noqa: E402

DATE_FMTS = ["%d/%m/%Y", "%d/%m/%y", "%d %B %Y", "%d %b %Y", "%Y-%m-%d"]
TIME_FMTS = ["%H:%M", "%I:%M %p", "%H:%M:%S"]


def _parse_date(raw):
    if not raw:
        return None
    for f in DATE_FMTS:
        try:
            return datetime.strptime(raw.strip(), f).date()
        except ValueError:
            pass
    return None


def _parse_time(raw):
    if not raw:
        return None
    for f in TIME_FMTS:
        try:
            return datetime.strptime(raw.strip(), f).time()
        except ValueError:
            pass
    return None


def clean_team(raw):
    """Strip duplicated club-name prefix (e.g. 'Stanwick Rovers Stanwick Rovers First'
    → 'Stanwick Rovers First')."""
    raw = raw.strip()
    words = raw.split()
    n = len(words)
    for split in range(1, n // 2 + 1):
        prefix = " ".join(words[:split])
        rest = " ".join(words[split:])
        if rest.lower().startswith(prefix.lower()):
            return rest
    return raw


def fetch_html():
    url = (
        f"https://fulltime.thefa.com/fixtures.html"
        f"?selectedSeason={SEASON_ID}"
        f"&selectedFixtureGroupKey={FIXTURE_GROUP}"
        f"&selectedDateCode=all"
        f"&selectedRelatedFixtureOption=1"
        f"&previousSelectedFixtureGroupKey={FIXTURE_GROUP}"
        f"&itemsPerPage=10000"
    )
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # visible window passes Cloudflare
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 720},
            locale="en-GB",
        )
        page = ctx.new_page()
        page.goto(url, wait_until="networkidle", timeout=30000)
        html = page.content()
        browser.close()
    return html


def parse_fixtures(html):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        print("ERROR: no fixtures table found in page — check if the page loaded correctly")
        sys.exit(1)

    fixtures = []
    for row in table.find_all("tr")[1:]:   # skip header row
        cells = row.find_all("td")
        if len(cells) < 9:
            continue

        # cell[1] = "DD/MM/YY HH:MM"  cell[2] = home  cell[6] = away
        # cell[7] = venue  cell[8] = competition type
        date_time_raw = cells[1].get_text(" ", strip=True)
        home = clean_team(cells[2].get_text(" ", strip=True))
        away = clean_team(cells[6].get_text(" ", strip=True))
        venue = cells[7].get_text(" ", strip=True)
        fixture_type = cells[8].get_text(" ", strip=True)

        if TEAM_NAME and (
            TEAM_NAME.lower() not in home.lower()
            and TEAM_NAME.lower() not in away.lower()
        ):
            continue

        parts = date_time_raw.split()
        fixtures.append({
            "Date": parts[0] if parts else "",
            "Time": parts[1] if len(parts) > 1 else "",
            "Home": home,
            "Away": away,
            "Venue": venue,
            "FixtureType": fixture_type,
        })

    return fixtures


def build_ics(fixtures):
    tz = pytz.timezone(TIMEZONE)
    cal = Calendar()
    cal.add("prodid", f"-//{CALENDAR_NAME}//fulltime.thefa.com//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", CALENDAR_NAME)
    cal.add("x-wr-timezone", TIMEZONE)

    fallback_ko = _parse_time(DEFAULT_KO)
    count = 0
    last_date = None

    for f in fixtures:
        d = _parse_date(f["Date"])
        if not d:
            continue
        ko = _parse_time(f["Time"]) or fallback_ko
        home = f["Home"]
        away = f["Away"]
        dt_s = tz.localize(datetime.combine(d, ko))
        dt_e = dt_s + timedelta(hours=DURATION_H)

        ev = Event()
        ev.add("summary", f"{home} v {away}")
        ev.add("dtstart", dt_s)
        ev.add("dtend", dt_e)
        if f.get("Venue"):
            ev.add("location", f["Venue"])
        ev.add("description",
               f"{home} v {away}\nVenue: {f.get('Venue', '')}\n"
               f"Type: {f.get('FixtureType', '')}\n"
               f"Source: https://fulltime.thefa.com")
        ev.add("uid",
               f"{home.lower().replace(' ', '-')}-v-"
               f"{away.lower().replace(' ', '-')}-"
               f"{d:%Y%m%d}@fulltime.thefa.com")
        cal.add_component(ev)
        count += 1
        last_date = f["Date"]
        print(f"  {f['Date']}  {f['Time']:>5}  {home} v {away}  @ {f.get('Venue','')}")

    return cal.to_ical(), count, last_date


def main():
    print(f"Stanwick Rovers fixtures → ICS  [{datetime.now():%Y-%m-%d %H:%M}]")
    print(f"Season {SEASON_ID} / Group {FIXTURE_GROUP}")
    print("Fetching page via Playwright (Chrome)...")

    html = fetch_html()
    print(f"Page loaded ({len(html):,} bytes)")

    fixtures = parse_fixtures(html)
    print(f"Stanwick Rovers fixtures found: {len(fixtures)}")

    if not fixtures:
        print("ERROR: no fixtures found — check season/group IDs or team name filter")
        sys.exit(1)

    ics_bytes, count, last_date = build_ics(fixtures)
    OUTPUT.write_bytes(ics_bytes)
    print(f"\n✅ {count} events written → {OUTPUT}  (last: {last_date})")


if __name__ == "__main__":
    main()
