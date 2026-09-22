#!/usr/bin/env python3
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "sources.json"
STATUS = ROOT / "data" / "source-status.json"
DISCOVERY = ROOT / "data" / "discovery.json"
SEEN = ROOT / "data" / "discovered-links.json"
UA = "Mozilla/5.0 (compatible; PetLaunchRadar/1.0; +https://github.com/vinge777/pet-launch-radar)"


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class AnchorParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self._href = None
        self._parts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self._href = dict(attrs).get("href")
            self._parts = []

    def handle_data(self, data):
        if self._href is not None:
            self._parts.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            text = re.sub(r"\s+", " ", " ".join(self._parts)).strip()
            self.links.append((self._href, text))
            self._href = None
            self._parts = []


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        raw = resp.read()
        ctype = resp.headers.get_content_charset() or "utf-8"
        try:
            return raw.decode(ctype, errors="replace")
        except Exception:
            return raw.decode("utf-8", errors="replace")


def host_matches(candidate_url, source_url):
    try:
        ch = urllib.parse.urlparse(candidate_url).hostname or ""
        sh = urllib.parse.urlparse(source_url).hostname or ""
        ch = ch.lower().removeprefix("www.")
        sh = sh.lower().removeprefix("www.")
        return ch == sh or ch.endswith("." + sh) or sh.endswith("." + ch)
    except Exception:
        return False


def clean_url(base, href):
    if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
        return None
    u = urllib.parse.urljoin(base, href)
    p = urllib.parse.urlparse(u)
    if p.scheme not in ("http", "https"):
        return None
    if re.search(r"\.(jpg|jpeg|png|gif|webp|svg|pdf|css|js)(\?|$)", p.path, re.I):
        return None
    # Strip tracking fragments but keep query because some retailers need it.
    return urllib.parse.urlunparse((p.scheme, p.netloc, p.path, p.params, p.query, ""))


def scan_html(source):
    html = fetch(source["url"])
    parser = AnchorParser()
    parser.feed(html)
    out = []
    patterns = source.get("link_patterns") or []
    for href, text in parser.links:
        url = clean_url(source["url"], href)
        if not url:
            continue
        if source.get("same_domain_only", True) and not host_matches(url, source["url"]):
            continue
        if patterns and not any(pat in url for pat in patterns):
            continue
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 3:
            text = urllib.parse.unquote(urllib.parse.urlparse(url).path.rstrip("/").split("/")[-1]).replace("-", " ")
        if len(text) < 3:
            continue
        out.append({"url": url, "title": text[:240]})
    # Preserve order while deduping URLs.
    dedup = {}
    for item in out:
        dedup.setdefault(item["url"], item)
    return list(dedup.values())


def scan_google_news(source):
    params = urllib.parse.urlencode({"q": source["query"], "hl": "en", "gl": "US", "ceid": "US:en"})
    url = "https://news.google.com/rss/search?" + params
    xml = fetch(url)
    root = ET.fromstring(xml)
    out = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if title and link:
            out.append({"url": link, "title": title[:240]})
    return out


def main():
    cfg = load_json(CONFIG, {"sources": []})
    seen = load_json(SEEN, {"sources": {}})
    discovery = load_json(DISCOVERY, {"generated_at": None, "candidates": []})
    seen_sources = seen.setdefault("sources", {})
    candidates = discovery.setdefault("candidates", [])
    status_rows = []
    checked_at = now_iso()

    for source in cfg.get("sources", []):
        sid = source["id"]
        try:
            if source.get("mode") == "google_news":
                items = scan_google_news(source)
            else:
                items = scan_html(source)
            current_urls = [x["url"] for x in items]
            previous = set(seen_sources.get(sid, []))
            first_run = sid not in seen_sources
            new_items = [] if first_run else [x for x in items if x["url"] not in previous]

            for x in new_items:
                candidates.append({
                    "id": f"{sid}-{abs(hash(x['url']))}",
                    "title": x["title"],
                    "url": x["url"],
                    "source_id": sid,
                    "source_name": source["name"],
                    "region": source["region"],
                    "country": source.get("country"),
                    "channel_type": source["channel_type"],
                    "discovered_at": checked_at,
                    "review_status": "pending",
                    "note": "Auto-discovered candidate. Verify brand origin, launch recency and product-detail URL before moving to products.json."
                })

            # Keep a rolling union so a temporarily missing link is not repeatedly rediscovered.
            merged = list(dict.fromkeys(list(previous) + current_urls))
            seen_sources[sid] = merged[-6000:]
            status_rows.append({
                "id": sid,
                "name": source["name"],
                "region": source["region"],
                "country": source.get("country"),
                "channel_type": source["channel_type"],
                "type": source["channel_type"],
                "status": "ok",
                "items_found": len(items),
                "new_candidates": len(new_items),
                "checked_at": checked_at,
                "source_url": source.get("url") or ("Google News: " + source.get("query", "")),
                "baseline_created": first_run
            })
        except Exception as exc:
            status_rows.append({
                "id": sid,
                "name": source["name"],
                "region": source["region"],
                "country": source.get("country"),
                "channel_type": source["channel_type"],
                "type": source["channel_type"],
                "status": "error",
                "items_found": 0,
                "new_candidates": 0,
                "checked_at": checked_at,
                "source_url": source.get("url") or ("Google News: " + source.get("query", "")),
                "error": str(exc)[:300]
            })
        time.sleep(0.4)

    # Dedupe candidates by URL, retain newest record and 180 days of history.
    cutoff = datetime.now(timezone.utc) - timedelta(days=180)
    by_url = {}
    for c in candidates:
        try:
            dt = datetime.fromisoformat(c.get("discovered_at", "").replace("Z", "+00:00"))
        except Exception:
            dt = datetime.now(timezone.utc)
        if dt < cutoff:
            continue
        by_url[c["url"]] = c
    candidates = sorted(by_url.values(), key=lambda x: x.get("discovered_at", ""), reverse=True)[:2500]

    save_json(SEEN, {"generated_at": checked_at, "sources": seen_sources})
    save_json(DISCOVERY, {"generated_at": checked_at, "candidates": candidates})
    save_json(STATUS, {"generated_at": checked_at, "sources": status_rows})
    print(f"Scanned {len(status_rows)} sources; pending candidates: {len(candidates)}")


if __name__ == "__main__":
    main()
