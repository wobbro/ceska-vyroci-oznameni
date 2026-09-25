#!/usr/bin/env python3
"""
Denně zkontroluje:
1) Wikidata: čeští spisovatelé/spisovatelky s narozeninami nebo úmrtím dnes
   (dynamické - chytí i nově přidané osoby na Wikidatech, ne pevný seznam)
2) Pevný seznam českých státních svátků a významných dnů
A pošle push notifikaci přes ntfy.sh (zdarma, bez registrace).
"""

import os
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

NTFY_TOPIC = os.environ["NTFY_TOPIC"]  # nastaveno jako GitHub secret
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"

TZ = ZoneInfo("Europe/Prague")
TODAY = datetime.now(TZ)
MONTH, DAY = TODAY.month, TODAY.day

# ---------- 1) Wikidata: dynamické hledání spisovatelů ----------

SPARQL_QUERY = """
SELECT ?person ?personLabel ?dob ?dod WHERE {
  VALUES ?occ { wd:Q36180 wd:Q49757 wd:Q214917 wd:Q6625963 wd:Q28389 }
  ?person wdt:P106 ?occ .
  VALUES ?country { wd:Q213 wd:Q33946 }
  ?person wdt:P27 ?country .
  OPTIONAL { ?person wdt:P569 ?dob . }
  OPTIONAL { ?person wdt:P570 ?dod . }
  FILTER(
    (BOUND(?dob) && MONTH(?dob) = %d && DAY(?dob) = %d) ||
    (BOUND(?dod) && MONTH(?dod) = %d && DAY(?dod) = %d)
  )
  SERVICE wikibase:label { bd:serviceParam wikibase:language "cs,en". }
}
LIMIT 50
""" % (MONTH, DAY, MONTH, DAY)


def fetch_writers():
    resp = requests.get(
        "https://query.wikidata.org/sparql",
        params={"query": SPARQL_QUERY, "format": "json"},
        headers={"User-Agent": "ceska-vyroci-bot/1.0"},
        timeout=30,
    )
    resp.raise_for_status()
    results = resp.json()["results"]["bindings"]

    people = {}
    for row in results:
        name = row["personLabel"]["value"]
        dob = row.get("dob", {}).get("value")
        dod = row.get("dod", {}).get("value")
        entry = people.setdefault(name, {"dob": None, "dod": None})
        if dob and dob[5:7] == f"{MONTH:02d}" and dob[8:10] == f"{DAY:02d}":
            entry["dob"] = dob[:4]
        if dod and dod[5:7] == f"{MONTH:02d}" and dod[8:10] == f"{DAY:02d}":
            entry["dod"] = dod[:4]
    return people


def get_fun_fact(name):
    """Krátký výtah z české Wikipedie jako 'fun fact'."""
    try:
        resp = requests.get(
            "https://cs.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "prop": "extracts",
                "exintro": 1,
                "explaintext": 1,
                "exchars": 300,
                "titles": name,
                "format": "json",
            },
            headers={"User-Agent": "ceska-vyroci-bot/1.0"},
            timeout=15,
        )
        pages = resp.json()["query"]["pages"]
        for page in pages.values():
            extract = page.get("extract", "")
            if extract:
                return extract.strip()
    except Exception:
        pass
    return ""


def build_writer_messages():
    messages = []
    for name, info in fetch_writers().items():
        birth_year = TODAY.year
        if info["dob"]:
            years = TODAY.year - int(info["dob"])
            messages.append(f"🎂 {name} by dnes slavil/a {years}. narozeniny (narozen/a {info['dob']})")
        if info["dod"]:
            years = TODAY.year - int(info["dod"])
            messages.append(f"🕯️ {name} - dnes je to {years} let od úmrtí ({info['dod']})")
    # doplnit fun fact k prvním pár jménům, ať notifikace není moc dlouhá
    detailed = []
    for msg in messages:
        for name in fetch_writers().keys():
            if name in msg:
                fact = get_fun_fact(name)
                if fact:
                    msg = f"{msg}\n💡 {fact}"
                break
        detailed.append(msg)
    return detailed


# ---------- 2) Pevné české státní svátky a významné dny ----------

HOLIDAYS = {
    (1, 1): ("Den obnovy samostatného českého státu", "Také Nový rok."),
    (4, 23): ("Světový den knihy", "Symbolické datum úmrtí Cervantese i Shakespeara."),
    (5, 1): ("Svátek práce", ""),
    (5, 8): ("Den vítězství", "Konec 2. světové války v Evropě, 1945."),
    (7, 5): ("Den slovanských věrozvěstů Cyrila a Metoděje", ""),
    (7, 6): ("Den upálení mistra Jana Husa", "Upálen v Kostnici roku 1415."),
    (9, 28): ("Den české státnosti", "Svátek svatého Václava."),
    (10, 28): ("Den vzniku samostatného československého státu", "Vznik Československa, 1918."),
    (11, 17): ("Den boje za svobodu a demokracii", "Sametová revoluce 1989 a demonstrace 1939."),
    (12, 24): ("Štědrý den", ""),
    (12, 25): ("1. svátek vánoční", ""),
    (12, 26): ("2. svátek vánoční", ""),
}


def build_holiday_message():
    key = (MONTH, DAY)
    if key in HOLIDAYS:
        title, note = HOLIDAYS[key]
        return f"🎉 Dnes je: {title}" + (f"\n{note}" if note else "")
    return None


# ---------- 3) Odeslání notifikace ----------

def send_notification(title, body):
    requests.post(
        NTFY_URL,
        data=body.encode("utf-8"),
        headers={
            "Title": title.encode("utf-8"),
            "Priority": "high",
            "Tags": "books,cz",
        },
        timeout=15,
    )


def main():
    parts = []

    holiday_msg = build_holiday_message()
    if holiday_msg:
        parts.append(holiday_msg)

    parts.extend(build_writer_messages())

    if not parts:
        print("Dnes žádné výročí ani svátek - notifikace se neposílá.")
        return

    body = "\n\n".join(parts)
    send_notification("Česká výročí a svátky dnes", body)
    print("Odesláno:\n", body)


if __name__ == "__main__":
    main()
