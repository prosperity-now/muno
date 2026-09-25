import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "matches.json"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "MUNO-Soccer-Analytics/2.0",
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
})

# ESPN exposes public scoreboard feeds for major soccer competitions.
# These feeds require no API key and are much more structured than search-engine HTML.
ESPN_LEAGUES = [
    ("eng.1", "Premier League"),
    ("esp.1", "La Liga"),
    ("ger.1", "Bundesliga"),
    ("ita.1", "Serie A"),
    ("fra.1", "Ligue 1"),
    ("ned.1", "Eredivisie"),
    ("por.1", "Primeira Liga"),
    ("bel.1", "Belgian Pro League"),
    ("sco.1", "Scottish Premiership"),
    ("tur.1", "Super Lig"),
    ("gre.1", "Greek Super League"),
    ("mex.1", "Liga MX"),
    ("bra.1", "Brasileirao"),
    ("arg.1", "Argentine Primera"),
    ("usa.1", "MLS"),
    ("uefa.champions", "UEFA Champions League"),
    ("uefa.europa", "UEFA Europa League"),
    ("uefa.europa.conf", "UEFA Conference League"),
]

def espn_fixtures(date):
    date_key = date.replace("-", "")
    fixtures = []
    errors = []

    for league, competition_name in ESPN_LEAGUES:
        url = (
            "https://site.api.espn.com/apis/site/v2/sports/soccer/"
            f"{league}/scoreboard?dates={date_key}"
        )
        try:
            response = SESSION.get(url, timeout=20)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            errors.append(f"{league}: {exc}")
            continue

        for event in payload.get("events", []):
            competitions = event.get("competitions") or []
            if not competitions:
                continue

            competition = competitions[0]
            competitors = competition.get("competitors") or []
            home = next(
                (c for c in competitors if c.get("homeAway") == "home"), None
            )
            away = next(
                (c for c in competitors if c.get("homeAway") == "away"), None
            )
            if not home or not away:
                continue

            home_name = (
                home.get("team", {}).get("displayName")
                or home.get("team", {}).get("name")
            )
            away_name = (
                away.get("team", {}).get("displayName")
                or away.get("team", {}).get("name")
            )
            if not home_name or not away_name:
                continue

            kickoff = event.get("date") or competition.get("date") or "TBD"
            event_id = str(event.get("id") or "").strip()
            if not event_id:
                event_id = slug(f"{date}-{home_name}-{away_name}")

            league_name = (
                event.get("season", {}).get("displayName")
                or competition.get("league", {}).get("name")
                or competition_name
            )

            fixtures.append({
                "match_id": f"espn-{league}-{event_id}",
                "id": f"espn-{league}-{event_id}",
                "date": date,
                "competition": league_name,
                "kickoff": kickoff,
                "home_team": {"name": home_name},
                "away_team": {"name": away_name},
                "source": url,
                "source_provider": "ESPN",
                "source_event_id": event_id,
            })

    return dedupe(fixtures), errors


def search(q):
    response = SESSION.get(
        "https://html.duckduckgo.com/html/?q=" + quote_plus(q),
        timeout=25,
    )
    response.raise_for_status()
    return [
        (a.get_text(" ", strip=True), a.get("href", ""))
        for a in BeautifulSoup(response.text, "html.parser").select(".result__a")[:10]
    ]


def search_fallback(date):
    found = []
    for query in (f"football fixtures {date}", f"soccer fixtures {date}"):
        try:
            results = search(query)
        except requests.RequestException as exc:
            print(f"Fixture search failed: {exc}", file=sys.stderr)
            continue

        for title, url in results:
            try:
                response = SESSION.get(url, timeout=20)
                response.raise_for_status()
                text = " ".join(
                    BeautifulSoup(response.text, "html.parser").stripped_strings
                )
            except requests.RequestException:
                continue

            for pattern in (
                r"([A-Z][A-Za-z0-9 .&'’_-]{2,40})\s+(?:vs\.?|v)\s+([A-Z][A-Za-z0-9 .&'’_-]{2,40})",
                r"([A-Z][A-Za-z0-9 .&'’_-]{2,40})\s+[-–]\s+([A-Z][A-Za-z0-9 .&'’_-]{2,40})",
            ):
                match = re.search(pattern, text)
                if match:
                    found.append({
                        "home": match.group(1).strip(),
                        "away": match.group(2).strip(),
                        "source": url,
                    })
                    break

        if found:
            break

    return dedupe([
        {
            "match_id": slug(f"{date}-{item['home']}-{item['away']}"),
            "id": slug(f"{date}-{item['home']}-{item['away']}"),
            "date": date,
            "competition": "Football",
            "kickoff": "TBD",
            "home_team": {"name": item["home"]},
            "away_team": {"name": item["away"]},
            "source": item["source"],
            "source_provider": "search-fallback",
        }
        for item in found
    ])


def slug(value):
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def dedupe(fixtures):
    result = []
    seen = set()
    for fixture in fixtures:
        home = fixture.get("home_team", {}).get("name", "").strip().lower()
        away = fixture.get("away_team", {}).get("name", "").strip().lower()
        key = (fixture.get("date"), home, away)
        if not home or not away or key in seen:
            continue
        seen.add(key)
        result.append(fixture)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    datetime.strptime(args.date, "%Y-%m-%d")

    fixtures, errors = espn_fixtures(args.date)
    print(f"ESPN returned {len(fixtures)} fixtures for {args.date}")

    if errors:
        print(f"ESPN sources with errors: {len(errors)}", file=sys.stderr)
        for error in errors[:10]:
            print(f"  {error}", file=sys.stderr)

    if not fixtures:
        print("No structured ESPN fixtures found; trying search fallback.")
        fixtures = search_fallback(args.date)
        print(f"Search fallback returned {len(fixtures)} fixtures")

    # Do not silently publish an empty fixture set. An empty result used to make
    # Actions appear successful while leaving the dashboard with nothing to show.
    if not fixtures:
        raise RuntimeError(
            f"No fixtures could be collected for {args.date}. "
            "The workflow will not overwrite the existing fixture data for this date."
        )

    old = []
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            old = []

    if isinstance(old, dict):
        old = old.get("matches", [])

    merged = [item for item in old if item.get("date") != args.date] + fixtures
    merged.sort(
        key=lambda item: (
            item.get("date", ""),
            item.get("kickoff", ""),
            item.get("match_id", ""),
        )
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Saved {len(fixtures)} fixtures for {args.date}")


if __name__ == "__main__":
    main()
