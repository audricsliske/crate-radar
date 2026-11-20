import json
import os
import re
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

PHT = timezone(timedelta(hours=8))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

SOURCES = [
    {"platform": "Hypeddit", "genre": "Dubstep", "url": "https://hypeddit.com/charts/downloads/genre/dubstep", "strict_filter": False},
    {"platform": "Hypeddit", "genre": "Trap", "url": "https://hypeddit.com/charts/downloads/genre/trap", "strict_filter": False},
    {"platform": "Hypeddit", "genre": "Afro House", "url": "https://hypeddit.com/charts/downloads/genre/afro-house", "strict_filter": False},
    {"platform": "Hypeddit", "genre": "Bass", "url": "https://hypeddit.com/charts/downloads/genre/bass", "strict_filter": True},
    {"platform": "Hypeddit", "genre": "New Releases", "url": "https://hypeddit.com/newreleases/genre/all", "strict_filter": True},
    {"platform": "Droploud", "genre": "Dubstep", "url": "https://droploud.com/genre/dubstep", "strict_filter": False},
    {"platform": "Droploud", "genre": "Trap", "url": "https://droploud.com/genre/trap", "strict_filter": False},
    {"platform": "Droploud", "genre": "Afro House", "url": "https://droploud.com/genre/afro-house", "strict_filter": False},
    {"platform": "Droploud", "genre": "Discover", "url": "https://droploud.com/discover", "strict_filter": True},
]

EDIT_KEYWORDS = re.compile(r"\b(flip|edit|bootleg|vip|remix|rework|mashup|refix)\b", re.I)
GENRE_KEYWORDS = re.compile(r"\b(dubstep|riddim|trap|afro\s*house|afrotech|afro-tech|bass)\b", re.I)

AUDIO_EXT_RE = re.compile(r"\.(mp3|wav|flac|aiff|aif|m4a|aac|ogg|alac|wma)$", re.I)
TRACK_NUM_RE = re.compile(r"^\d{1,3}[\s._-]+")
DJ_NOISE_TAGS_RE = re.compile(
    r"[\(\[]\s*(extended\s*mix|original\s*mix|radio\s*edit|clean|dirty|intro|outro|"
    r"short\s*edit|club\s*mix|instrumental|acapella|free\s*download|free\s*dl|"
    r"320\s*kbps|320|master|hq|explicit)\s*[\)\]]",
    re.I,
)


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def normalize_key(text: str) -> str:
    s = clean_text(text)
    s = AUDIO_EXT_RE.sub("", s)
    s = TRACK_NUM_RE.sub("", s)
    s = DJ_NOISE_TAGS_RE.sub("", s)
    s = s.lower()
    s = s.replace("&", "and")
    s = re.sub(r"\b(feat|ft)\.?\b", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def is_owned_track(title: str, owned_keys: set) -> bool:
    key = normalize_key(title)
    if not key:
        return False
    if key in owned_keys:
        return True
    if len(key) >= 12:
        for o_key in owned_keys:
            if len(o_key) >= 12 and (key in o_key or o_key in key):
                return True
    return False


def load_existing(path: str = "tracks.json") -> list:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("tracks", [])
    except Exception as exc:
        print(f"Warning: could not read existing {path}: {exc}")
        return []


def load_owned_keys(path: str = "owned_tracks.json") -> set:
    if not os.path.exists(path):
        return set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            raw_list = data.get("tracks", []) if isinstance(data, dict) else data
            keys = set()
            for item in raw_list:
                name = item.get("title", "") if isinstance(item, dict) else str(item)
                k = normalize_key(name)
                if k:
                    keys.add(k)
            return keys
    except Exception as exc:
        print(f"Warning: could not read {path}: {exc}")
        return set()


def parse_hypeddit(soup: BeautifulSoup, base_url: str, default_genre: str) -> list:
    found = []
    seen_local = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if "/track/" not in href:
            continue
        full_url = urljoin(base_url, href).split("?")[0]
        if full_url in seen_local:
            continue

        container = a.find_parent(["li", "div", "article"]) or a
        raw_lines = [clean_text(x) for x in container.stripped_strings]
        noise = {
            "get this track", "play", "download", "free download", "promoted",
            "share", "copy link", "play on spotify", "save on spotify"
        }
        lines = [
            line for line in raw_lines
            if line.lower() not in noise
            and not re.match(r"^#?\d+$", line)
            and not re.match(r"^\d+:\d+$", line)
            and not line.lower().startswith("genre:")
            and not line.lower().startswith("length:")
        ]

        link_text = clean_text(a.get_text())
        if link_text and link_text.lower() not in noise and len(link_text) > 2:
            title_candidate = link_text
        elif lines:
            title_candidate = " - ".join(lines[:2]) if len(lines) >= 2 else lines[0]
        else:
            continue

        if len(title_candidate) < 3 or len(title_candidate) > 140:
            continue

        seen_local.add(full_url)
        found.append({
            "title": title_candidate,
            "url": full_url,
            "platform": "Hypeddit",
            "genre": default_genre,
        })

    return found


def parse_droploud(soup: BeautifulSoup, base_url: str, default_genre: str) -> list:
    found = []
    seen_local = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if "/track/" not in href:
            continue
        full_url = urljoin(base_url, href).split("?")[0]
        if full_url in seen_local:
            continue

        container = a.find_parent(["li", "div", "article", "tr"]) or a
        raw_lines = [clean_text(x) for x in container.stripped_strings]
        noise = {
            "free dl", "free download", "no change", "dubstep", "trap",
            "afro house", "house", "tech house", "download"
        }
        lines = [
            line for line in raw_lines
            if line.lower() not in noise
            and not re.match(r"^#?\d+$", line)
            and not re.match(r"^(up|down)\s*\d+$", line, re.I)
            and not re.match(r"^\d{1,2}\s+[A-Z]{3}\s+'\d{2}$", line)
        ]

        link_text = clean_text(a.get_text())
        if link_text and link_text.lower() not in noise and len(link_text) > 2:
            title_candidate = link_text
        elif lines:
            title_candidate = lines[0]
        else:
            continue

        if len(title_candidate) < 3 or len(title_candidate) > 140:
            continue

        seen_local.add(full_url)
        found.append({
            "title": title_candidate,
            "url": full_url,
            "platform": "Droploud",
            "genre": default_genre,
        })

    return found


def main():
    owned_keys = load_owned_keys("owned_tracks.json")
    print(f"Loaded {len(owned_keys)} owned local tracks from owned_tracks.json")

    existing_tracks = load_existing("tracks.json")
    for t in existing_tracks:
        t["is_duplicate"] = is_owned_track(t.get("title", ""), owned_keys)

    seen_urls = {t.get("url", "").rstrip("/") for t in existing_tracks}
    seen_keys = {normalize_key(t.get("title", "")) for t in existing_tracks}

    now_pht = datetime.now(PHT)
    timestamp_label = now_pht.strftime("%b %d, %I:%M %p PHT")
    iso_now = now_pht.isoformat()

    new_tracks = []

    for src in SOURCES:
        url = src["url"]
        platform = src["platform"]
        genre = src["genre"]
        strict = src["strict_filter"]

        print(f"Scanning {platform} ({genre}): {url}")
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            if resp.status_code != 200:
                print(f"  Skipped (HTTP {resp.status_code})")
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            items = (
                parse_hypeddit(soup, url, genre)
                if platform == "Hypeddit"
                else parse_droploud(soup, url, genre)
            )
            print(f"  Found {len(items)} raw candidates")

            for item in items:
                title = item["title"]
                t_url = item["url"].rstrip("/")
                t_key = normalize_key(title)

                if not t_key or t_url in seen_urls or t_key in seen_keys:
                    continue

                is_edit = bool(EDIT_KEYWORDS.search(title))
                matches_genre_kw = bool(GENRE_KEYWORDS.search(title))

                if strict and not (is_edit or matches_genre_kw):
                    continue

                detected_genre = genre
                if re.search(r"\b(dubstep|riddim)\b", title, re.I):
                    detected_genre = "Dubstep"
                elif re.search(r"\btrap\b", title, re.I):
                    detected_genre = "Trap"
                elif re.search(r"\b(afro\s*house|afrotech|afro-tech)\b", title, re.I):
                    detected_genre = "Afro House"

                seen_urls.add(t_url)
                seen_keys.add(t_key)

                new_tracks.append({
                    "id": t_key[:24] + "_" + str(int(now_pht.timestamp())),
                    "title": title,
                    "url": t_url,
                    "platform": platform,
                    "genre": detected_genre,
                    "is_edit": is_edit,
                    "is_duplicate": is_owned_track(title, owned_keys),
                    "found_at": timestamp_label,
                    "found_iso": iso_now,
                })

        except Exception as exc:
            print(f"  Error scanning {url}: {exc}")

        time.sleep(1.5)

    print(f"Total brand-new tracks added: {len(new_tracks)}")

    combined = (new_tracks + existing_tracks)[:400]

    output = {
        "last_updated": timestamp_label,
        "total_tracks": len(combined),
        "tracks": combined,
    }

    with open("tracks.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
