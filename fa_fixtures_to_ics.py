#!/usr/bin/env python3
"""
Stanwick Rovers FC — Division 2 Fixtures → ICS
Fetches fixtures from fulltime.thefa.com via the full-time-api package
and writes a fresh fixtures.ics calendar file.

Usage:
    python fa_fixtures_to_ics.py [output.ics]   (default: fixtures.ics)
"""

import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
SEASON_ID      = 477693916
FIXTURE_GROUP  = "1_748828336"
TEAM_NAME      = "Stanwick Rovers"   # filter to this team; set None for whole division
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


_install("full-time-api", "icalendar", "pytz")

from full_time_api import Division      # noqa: E402
from icalendar import Calendar, Event  # noqa: E402
import pytz                            # noqa: E402

DATE_FMTS = ["%d/%m/%Y", "%d/%m/%y", "%d %B %Y", "%d %b %Y", "%Y-%m-%d"]
TIME_FMTS = ["%H:%M", "%I:%M %p", "%H:%M:%S"]


def _date(raw):
    for f in DATE_FMTS:
        try:
            return datetime.strptime(str(raw).strip(), f).date()
        except ValueError:
            pass
    return None


def _time(raw):
    for f in TIME_FMTS:
        try:
            return datetime.strptime(str(raw).strip(), f).time()
        except ValueError:
            pass
    return None


def main():
    print(f"Stanwick Rovers fixtures → ICS  [{datetime.now():%Y-%m-%d %H:%M}]")
    print(f"Season {SEASON_ID} / Group {FIXTURE_GROUP}")

    div = Division()
    all_fx = div.get_formatted_fixtures(
        SEASON_ID, FIXTURE_GROUP,
        include_tbc_fixtures=True,
        include_cup_fixtures=True,
    )
    print(f"Division total: {len(all_fx)} fixtures")

    if TEAM_NAME:
        fx = [f for f in all_fx
              if TEAM_NAME.lower() in f.get("Home", "").lower()
              or TEAM_NAME.lower() in f.get("Away", "").lower()]
        print(f"Filtered to '{TEAM_NAME}': {len(fx)}")
    else:
        fx = all_fx

    if not fx:
        print("ERROR: no fixtures found — check season/group IDs or team name")
        sys.exit(1)

    tz = pytz.timezone(TIMEZONE)
    cal = Calendar()
    cal.add("prodid", f"-//{CALENDAR_NAME}//fulltime.thefa.com//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", CALENDAR_NAME)
    cal.add("x-wr-timezone", TIMEZONE)

    fallback_ko = _time(DEFAULT_KO)
    count = 0
    last_date = None

    for f in fx:
        d = _date(f.get("Date"))
        if not d:
            continue
        ko = _time(f.get("Time")) or fallback_ko
        home = f.get("Home", "?").strip()
        away = f.get("Away", "?").strip()
        dt_s = tz.localize(datetime.combine(d, ko))
        dt_e = dt_s + timedelta(hours=DURATION_H)

        ev = Event()
        ev.add("summary", f"{home} v {away}")
        ev.add("dtstart", dt_s)
        ev.add("dtend", dt_e)
        ev.add("description",
               f"{home} v {away}\nType: {f.get('FixtureType', '')}\n"
               f"Source: https://fulltime.thefa.com")
        ev.add("uid",
               f"{home.lower().replace(' ','-')}-v-"
               f"{away.lower().replace(' ','-')}-"
               f"{d:%Y%m%d}@fulltime.thefa.com")
        cal.add_component(ev)
        count += 1
        last_date = f.get("Date")
        print(f"  {f.get('Date')}  {str(f.get('Time','??')):>5}  {home} v {away}")

    OUTPUT.write_bytes(cal.to_ical())
    print(f"\n✅ {count} events written → {OUTPUT}  (last: {last_date})")


if __name__ == "__main__":
    main()
