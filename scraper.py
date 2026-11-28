import json
import os
import re
import time
import unicodedata
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin, urlparse, unquote, quote_plus

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

HTML_SOURCES = [
    # Hypeddit Top Downloads Charts
    {"platform": "Hypeddit", "genre": "Dancehall", "url": "https://hypeddit.com/charts/downloads/genre/dancehall", "strict_filter": False},
    {"platform": "Hypeddit", "genre": "Dubstep", "url": "https://hypeddit.com/charts/downloads/genre/dubstep", "strict_filter": False},
    {"platform": "Hypeddit", "genre": "Trap", "url": "https://hypeddit.com/charts/downloads/genre/trap", "strict_filter": False},
    {"platform": "Hypeddit", "genre": "Afro House", "url": "https://hypeddit.com/charts/downloads/genre/afro-house", "strict_filter": False},
    {"platform": "Hypeddit", "genre": "Bass", "url": "https://hypeddit.com/charts/downloads/genre/bass", "strict_filter": True},
    # Hypeddit New Releases & Streaming Charts
    {"platform": "Hypeddit", "genre": "Dancehall", "url": "https://hypeddit.com/newreleases/genre/dancehall", "strict_filter": False},
    {"platform": "Hypeddit", "genre": "Dancehall", "url": "https://hypeddit.com/charts/streams/genre/dancehall", "strict_filter": False},
    {"platform": "Hypeddit", "genre": "Dubstep", "url": "https://hypeddit.com/newreleases/genre/dubstep", "strict_filter": False},
    {"platform": "Hypeddit", "genre": "Trap", "url": "https://hypeddit.com/newreleases/genre/trap", "strict_filter": False},
    {"platform": "Hypeddit", "genre": "Afro House", "url": "https://hypeddit.com/newreleases/genre/afro-house", "strict_filter": False},
    {"platform": "Hypeddit", "genre": "New Releases", "url": "https://hypeddit.com/newreleases/genre/all", "strict_filter": True},
    # Droploud Genre & Deeper Pages (Latin/Reggaeton holds Dancehall/Dembow/Moombahton on Droploud)
    {"platform": "Droploud", "genre": "Dancehall", "url": "https://droploud.com/genre/latin-reggaeton", "strict_filter": True},
    {"platform": "Droploud", "genre": "Dubstep", "url": "https://droploud.com/genre/dubstep", "strict_filter": False},
    {"platform": "Droploud", "genre": "Dubstep", "url": "https://droploud.com/genre/dubstep?page=2", "strict_filter": False},
    {"platform": "Droploud", "genre": "Trap", "url": "https://droploud.com/genre/trap", "strict_filter": False},
    {"platform": "Droploud", "genre": "Trap", "url": "https://droploud.com/genre/trap?page=2", "strict_filter": False},
    {"platform": "Droploud", "genre": "Afro House", "url": "https://droploud.com/genre/afro-house", "strict_filter": False},
    {"platform": "Droploud", "genre": "Afro House", "url": "https://droploud.com/genre/afro-house?page=2", "strict_filter": False},
    {"platform": "Droploud", "genre": "Discover", "url": "https://droploud.com/discover", "strict_filter": True},
]

SOUNDCLOUD_SEARCH_QUERIES = [
    {"genre": "Dancehall", "query": "dancehall free download"},
    {"genre": "Dancehall", "query": "dancehall flip bootleg free download"},
    {"genre": "Dubstep", "query": "dubstep flip free download"},
    {"genre": "Trap", "query": "trap edit free download"},
    {"genre": "Afro House", "query": "afro house remix free download"},
]

AUDIUS_FEEDS = [
    {"genre": "Dancehall", "mode": "trending", "param": "Dancehall"},
    {"genre": "Dancehall", "mode": "search", "param": "dancehall flip remix"},
    {"genre": "Dubstep", "mode": "trending", "param": "Dubstep"},
    {"genre": "Trap", "mode": "trending", "param": "Trap"},
    {"genre": "Afro House", "mode": "search", "param": "afro house"},
]

HEARTHIS_CATEGORIES = [
    {"genre": "Dancehall", "slug": "dancehall"},
    {"genre": "Dubstep", "slug": "dubstep"},
    {"genre": "Trap", "slug": "trap"},
    {"genre": "Afro House", "slug": "afro-house"},
]

EDIT_KEYWORDS = re.compile(r"\b(flip|edit|bootleg|vip|remix|rework|mashup|refix|redrum)\b", re.I)
GENRE_KEYWORDS = re.compile(
    r"\b(dancehall|riddim|bashment|moombahton|dembow|dubstep|trap|afro\s*house|afrotech|afro-tech|bass)\b",
    re.I
)

MAX_TRACK_SECONDS = 720  # Skip 15-90 min DJ mixtapes; keep singles/edits under 12 min

AUDIO_EXT_RE = re.compile(r"\.(mp3|wav|flac|aiff|aif|m4a|aac|ogg|alac|wma)$", re.I)
LEADING_META_RE = re.compile(r"^(?:\d{1,3}(?:\s*bpm)?|\d{1,2}[abm])[\s._-]+", re.I)

STOP_WORDS = {
    "extended", "original", "mix", "radio", "clean", "dirty", "intro", "outro",
    "short", "club", "instrumental", "acapella", "free", "download", "dl",
    "320", "320kbps", "kbps", "master", "mastered", "hq", "explicit",
    "feat", "ft", "featuring", "vs", "and", "the", "a", "an", "of", "in", "on",
    "out", "now", "hypeddit", "droploud", "soundcloud", "sc", "audius", "hearthis",
    "bpm", "official", "audio", "video", "premiere", "release", "version", "ver"
}

REMIX_MODIFIERS = {"flip", "bootleg", "vip", "remix", "rework", "mashup", "refix", "redrum"}

SC_RESERVED_USERS = {
    "login", "signup", "connect", "oauth", "you", "settings", "stream",
    "search", "popular", "people", "stations", "pro", "go", "imprint",
    "docs", "terms-of-use", "privacy", "cookies", "hypeddit", "droploud",
    "pages", "upload", "charts", "discover", "jobs", "press", "mobile",
    "downloads", "terms-of-service"
}
SC_RESERVED_TRACKS = {
    "sets", "tracks", "reposts", "likes", "following", "followers",
    "albums", "popular-tracks", "spotlight", "comments", "recommended"
}


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def fold_ascii(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text or "")
    return nfkd.encode("ascii", "ignore").decode("ascii")


def detect_genre(title: str, fallback_genre: str) -> str:
    if re.search(r"\b(dancehall|bashment|moombahton|dembow)\b", title, re.I):
        return "Dancehall"
    if re.search(r"\b(dubstep|riddim)\b", title, re.I):
        return "Dubstep"
    if re.search(r"\btrap\b", title, re.I):
        return "Trap"
    if re.search(r"\b(afro\s*house|afrotech|afro-tech)\b", title, re.I):
        return "Afro House"
    return fallback_genre


def tokenize_title(text: str) -> dict:
    s = fold_ascii(clean_text(text))
    s = AUDIO_EXT_RE.sub("", s)
    while True:
        nxt = LEADING_META_RE.sub("", s)
        if nxt == s:
            break
        s = nxt
    s = re.sub(r"\b(radio|short)\s+edit\b", " ", s, flags=re.I)
    s = re.sub(r"\b\d{1,2}[abm]\b", " ", s, flags=re.I)
    s = re.sub(r"\b\d{2,3}\s*bpm\b", " ", s, flags=re.I)
    s = s.lower().replace("&", " ")
    raw_tokens = re.findall(r"[a-z0-9]+", s)

    tokens = set()
    for tok in raw_tokens:
        if tok in STOP_WORDS:
            continue
        if len(tok) == 1 and not tok.isdigit():
            continue
        tokens.add(tok)

    mods = tokens & REMIX_MODIFIERS
    core = tokens - REMIX_MODIFIERS
    flat = "".join(sorted(tokens))
    return {"core": core, "mods": mods, "flat": flat}


def normalize_key(text: str) -> str:
    info = tokenize_title(text)
    return info["flat"]


def is_owned_track(title: str, owned_profiles: list) -> bool:
    t_info = tokenize_title(title)
    t_core = t_info["core"]
    t_mods = t_info["mods"]
    if not t_core:
        return False

    for o_info in owned_profiles:
        if t_info["flat"] and t_info["flat"] == o_info["flat"]:
            return True
        if t_mods != o_info["mods"]:
            continue
        o_core = o_info["core"]
        if not o_core:
            continue
        common = t_core & o_core
        min_len = min(len(t_core), len(o_core))
        if min_len >= 2 and len(common) >= 2 and (len(common) / min_len) >= 0.80:
            return True
        if min_len == 1 and len(common) == 1 and len(next(iter(common))) >= 6:
            return True

    return False


def is_valid_soundcloud_track(url: str) -> bool:
    try:
        parsed = urlparse(url)
        if "soundcloud.com" not in parsed.netloc.lower():
            return False
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) != 2:
            return False
        user_slug, track_slug = parts[0].lower(), parts[1].lower()
        if user_slug in SC_RESERVED_USERS or track_slug in SC_RESERVED_TRACKS:
            return False
        return True
    except Exception:
        return False


def fetch_preview_info(gate_url: str) -> dict:
    try:
        resp = requests.get(gate_url, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            return {}
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

        for iframe in soup.find_all("iframe", src=True):
            src = iframe["src"]
            if "w.soundcloud.com/player" in src:
                m = re.search(r"[?&]url=([^&]+)", src)
                if m:
                    sc_url = unquote(m.group(1)).split("?")[0]
                    if is_valid_soundcloud_track(sc_url):
                        return {"preview_type": "soundcloud", "preview_url": sc_url}

        for a in soup.find_all("a", href=True):
            href = a["href"].strip().split("?")[0]
            if is_valid_soundcloud_track(href):
                return {"preview_type": "soundcloud", "preview_url": href}

        sc_matches = re.findall(r"https?://(?:www\.|m\.)?soundcloud\.com/[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+", html)
        for sc_url in sc_matches:
            if is_valid_soundcloud_track(sc_url):
                return {"preview_type": "soundcloud", "preview_url": sc_url}

        og_audio = soup.find("meta", attrs={"property": "og:audio"}) or soup.find("meta", attrs={"name": "og:audio"})
        if og_audio and og_audio.get("content", "").startswith("http"):
            return {"preview_type": "audio", "preview_url": og_audio["content"].strip()}

        for audio_tag in soup.find_all(["audio", "source"], src=True):
            src = urljoin(gate_url, audio_tag["src"].strip())
            if src.startswith("http"):
                return {"preview_type": "audio", "preview_url": src}

        sp_match = re.search(r"https?://open\.spotify\.com/(?:embed/)?track/([a-zA-Z0-9]{22})", html)
        if sp_match:
            track_id = sp_match.group(1)
            return {
                "preview_type": "spotify",
                "preview_url": f"https://open.spotify.com/embed/track/{track_id}?theme=0"
            }

        yt_match = re.search(r"https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})", html)
        if yt_match:
            vid_id = yt_match.group(1)
            return {
                "preview_type": "youtube",
                "preview_url": f"https://www.youtube.com/embed/{vid_id}?autoplay=1"
            }

    except Exception as exc:
        print(f"    Preview lookup skipped for {gate_url}: {exc}")

    return {}


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


def load_owned_profiles(path: str = "owned_tracks.json") -> list:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            raw_list = data.get("tracks", []) if isinstance(data, dict) else data
            profiles = []
            seen_flats = set()
            for item in raw_list:
                name = item.get("title", "") if isinstance(item, dict) else str(item)
                info = tokenize_title(name)
                if info["core"] and info["flat"] not in seen_flats:
                    seen_flats.add(info["flat"])
                    profiles.append(info)
            return profiles
    except Exception as exc:
        print(f"Warning: could not read {path}: {exc}")
        return []


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
            "downloadable": True,
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
            "afro house", "house", "tech house", "download", "latin / reggaeton"
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
            "downloadable": True,
        })

    return found


def scrape_soundcloud_search(query: str, default_genre: str) -> list:
    found = []
    search_url = f"https://soundcloud.com/search/sounds?q={quote_plus(query)}"
    print(f"Scanning SoundCloud ({default_genre}): {search_url}")
    try:
        resp = requests.get(search_url, headers=HEADERS, timeout=18)
        if resp.status_code != 200:
            print(f"  SoundCloud skipped (HTTP {resp.status_code})")
            return found

        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        seen_local = set()

        # 1. Extract from semantic noscript / SSR links
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            full_url = urljoin("https://soundcloud.com", href).split("?")[0]
            if not is_valid_soundcloud_track(full_url) or full_url in seen_local:
                continue
            title_text = clean_text(a.get_text())
            if not title_text or len(title_text) < 3 or len(title_text) > 140:
                continue
            seen_local.add(full_url)
            found.append({
                "title": title_text,
                "url": full_url,
                "platform": "SoundCloud",
                "genre": default_genre,
                "preview_type": "soundcloud",
                "preview_url": full_url,
                "preview_checked": True,
                "downloadable": True,
            })

        # 2. Extract from SoundCloud hydration payload if present
        hyd_match = re.search(r"window\.__sc_hydration\s*=\s*(\[.*?\]);</script>", html, re.S)
        if hyd_match:
            try:
                hyd_data = json.loads(hyd_match.group(1))
                for block in hyd_data:
                    data = block.get("data")
                    collection = data.get("collection", []) if isinstance(data, dict) else []
                    for item in collection:
                        if not isinstance(item, dict):
                            continue
                        permalink = item.get("permalink_url", "").split("?")[0]
                        title_text = clean_text(item.get("title", ""))
                        duration_ms = item.get("duration") or 0
                        if duration_ms and (duration_ms / 1000.0) > MAX_TRACK_SECONDS:
                            continue
                        if not is_valid_soundcloud_track(permalink) or permalink in seen_local:
                            continue
                        if not title_text or len(title_text) < 3:
                            continue
                        artist = clean_text((item.get("user") or {}).get("username", ""))
                        display_title = (
                            f"{artist} - {title_text}"
                            if artist and artist.lower() not in title_text.lower()
                            else title_text
                        )
                        seen_local.add(permalink)
                        found.append({
                            "title": display_title[:140],
                            "url": permalink,
                            "platform": "SoundCloud",
                            "genre": default_genre,
                            "preview_type": "soundcloud",
                            "preview_url": permalink,
                            "preview_checked": True,
                            "downloadable": bool(item.get("downloadable") or item.get("purchase_url")),
                        })
            except Exception:
                pass

        print(f"  Found {len(found)} SoundCloud candidates")
    except Exception as exc:
        print(f"  Error scanning SoundCloud ({query}): {exc}")

    return found


def scrape_audius_feed(feed: dict) -> list:
    found = []
    genre = feed["genre"]
    mode = feed["mode"]
    param = feed["param"]

    if mode == "trending":
        api_url = f"https://api.audius.co/v1/tracks/trending?genre={quote_plus(param)}&limit=25&app_name=CrateRadar"
    else:
        api_url = f"https://api.audius.co/v1/tracks/search?query={quote_plus(param)}&limit=25&app_name=CrateRadar"

    print(f"Scanning Audius ({genre} - {mode}): {api_url}")
    try:
        resp = requests.get(api_url, headers=HEADERS, timeout=18)
        if resp.status_code != 200:
            print(f"  Audius skipped (HTTP {resp.status_code})")
            return found

        payload = resp.json()
        tracks = payload.get("data") or []
        for tr in tracks:
            if not isinstance(tr, dict):
                continue
            track_id = tr.get("id")
            title_text = clean_text(tr.get("title", ""))
            duration = tr.get("duration") or 0
            if not track_id or not title_text or duration > MAX_TRACK_SECONDS:
                continue

            artist = clean_text((tr.get("user") or {}).get("name", ""))
            display_title = (
                f"{artist} - {title_text}"
                if artist and artist.lower() not in title_text.lower()
                else title_text
            )
            permalink = tr.get("permalink") or ""
            web_url = f"https://audius.co{permalink}" if permalink.startswith("/") else f"https://audius.co/tracks/{track_id}"
            stream_url = f"https://api.audius.co/v1/tracks/{track_id}/stream?app_name=CrateRadar"

            found.append({
                "title": display_title[:140],
                "url": web_url,
                "platform": "Audius",
                "genre": genre,
                "preview_type": "audio",
                "preview_url": stream_url,
                "preview_checked": True,
                "downloadable": bool(tr.get("is_downloadable")),
            })
        print(f"  Found {len(found)} Audius candidates")
    except Exception as exc:
        print(f"  Error scanning Audius ({genre}): {exc}")

    return found


def scrape_hearthis_category(cat: dict) -> list:
    found = []
    genre = cat["genre"]
    slug = cat["slug"]
    api_url = f"https://api-v2.hearthis.at/categories/{slug}/?page=1&count=25"
    print(f"Scanning Hearthis.at ({genre}): {api_url}")
    try:
        resp = requests.get(api_url, headers=HEADERS, timeout=18)
        if resp.status_code != 200:
            print(f"  Hearthis skipped (HTTP {resp.status_code})")
            return found

        items = resp.json()
        if not isinstance(items, list):
            return found

        for tr in items:
            if not isinstance(tr, dict):
                continue
            title_text = clean_text(tr.get("title", ""))
            permalink_url = (tr.get("permalink_url") or "").split("?")[0]
            stream_url = tr.get("stream_url") or ""
            try:
                duration_sec = int(float(tr.get("duration") or 0))
            except Exception:
                duration_sec = 0

            if not title_text or not permalink_url:
                continue
            if duration_sec > MAX_TRACK_SECONDS:
                continue

            artist = clean_text((tr.get("user") or {}).get("username", ""))
            display_title = (
                f"{artist} - {title_text}"
                if artist and artist.lower() not in title_text.lower()
                else title_text
            )
            entry = {
                "title": display_title[:140],
                "url": permalink_url,
                "platform": "Hearthis",
                "genre": genre,
                "preview_checked": True,
                "downloadable": str(tr.get("downloadable", "0")) == "1",
            }
            if stream_url.startswith("http"):
                entry["preview_type"] = "audio"
                entry["preview_url"] = stream_url

            found.append(entry)
        print(f"  Found {len(found)} Hearthis candidates")
    except Exception as exc:
        print(f"  Error scanning Hearthis ({genre}): {exc}")

    return found


def main():
    owned_profiles = load_owned_profiles("owned_tracks.json")
    print(f"Loaded {len(owned_profiles)} owned local tracks from owned_tracks.json")

    existing_tracks = load_existing("tracks.json")
    for t in existing_tracks:
        t["is_duplicate"] = is_owned_track(t.get("title", ""), owned_profiles)

    seen_urls = {t.get("url", "").rstrip("/") for t in existing_tracks}
    seen_keys = {normalize_key(t.get("title", "")) for t in existing_tracks}

    now_pht = datetime.now(PHT)
    timestamp_label = now_pht.strftime("%b %d, %I:%M %p PHT")
    iso_now = now_pht.isoformat()

    new_tracks = []
    preview_lookups = 0
    MAX_PREVIEW_LOOKUPS = 65

    def register_candidates(candidates: list, strict: bool = False):
        nonlocal preview_lookups
        for item in candidates:
            title = item["title"]
            t_url = item["url"].rstrip("/")
            t_key = normalize_key(title)

            if not t_key or t_url in seen_urls or t_key in seen_keys:
                continue

            is_edit = bool(EDIT_KEYWORDS.search(title))
            matches_genre_kw = bool(GENRE_KEYWORDS.search(title))

            if strict and not (is_edit or matches_genre_kw):
                continue

            detected_genre = detect_genre(title, item["genre"])

            seen_urls.add(t_url)
            seen_keys.add(t_key)

            preview = {}
            if item.get("preview_url"):
                preview = {
                    "preview_type": item.get("preview_type", "audio"),
                    "preview_url": item["preview_url"],
                    "preview_checked": True,
                }
            elif preview_lookups < MAX_PREVIEW_LOOKUPS:
                preview = fetch_preview_info(t_url)
                preview_lookups += 1
                time.sleep(0.3)

            track_entry = {
                "id": t_key[:24] + "_" + str(int(now_pht.timestamp())),
                "title": title,
                "url": t_url,
                "platform": item["platform"],
                "genre": detected_genre,
                "is_edit": is_edit,
                "is_duplicate": is_owned_track(title, owned_profiles),
                "downloadable": bool(item.get("downloadable", True)),
                "found_at": timestamp_label,
                "found_iso": iso_now,
            }
            track_entry.update(preview)
            new_tracks.append(track_entry)

    # 1. Hypeddit & Droploud
    for src in HTML_SOURCES:
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
            register_candidates(items, strict=strict)
        except Exception as exc:
            print(f"  Error scanning {url}: {exc}")

        time.sleep(0.8)

    # 2. SoundCloud Free Downloads & Edits
    for sc in SOUNDCLOUD_SEARCH_QUERIES:
        items = scrape_soundcloud_search(sc["query"], sc["genre"])
        register_candidates(items, strict=False)
        time.sleep(0.8)

    # 3. Audius Free Streaming & Downloads
    for af in AUDIUS_FEEDS:
        items = scrape_audius_feed(af)
        register_candidates(items, strict=False)
        time.sleep(0.5)

    # 4. Hearthis.at Free DJ Tracks & Edits
    for hc in HEARTHIS_CATEGORIES:
        items = scrape_hearthis_category(hc)
        register_candidates(items, strict=False)
        time.sleep(0.5)

    # Backfill missing previews on older tracks
    for t in existing_tracks:
        if preview_lookups >= MAX_PREVIEW_LOOKUPS:
            break
        if not t.get("preview_checked"):
            preview = fetch_preview_info(t.get("url", ""))
            t["preview_checked"] = True
            t.update(preview)
            preview_lookups += 1
            time.sleep(0.3)

    print(f"Total brand-new tracks added: {len(new_tracks)}")

    combined = (new_tracks + existing_tracks)[:1000]

    output = {
        "last_updated": timestamp_label,
        "total_tracks": len(combined),
        "tracks": combined,
    }

    with open("tracks.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
