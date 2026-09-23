#!/usr/bin/env python3
import argparse
import email.utils
import html as html_lib
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "hotspot-sources.json"
OUT = ROOT / "data" / "hotspots.json"
STATE = ROOT / "data" / "hotspot-state.json"
UA = "Mozilla/5.0 (compatible; PetLaunchRadar/1.0; +https://github.com/vinge777/pet-launch-radar)"
VALID_CHANNELS = {"brand_official","specialty_retail","mass_retail","drugstore","marketplace","trade_media"}
PET_TERMS = re.compile(
    r"(?:\b(?:pet|pets|dog|dogs|cat|cats|puppy|puppies|kitten|kittens|animal|animals|canine|feline|pet food|petfood|pet care|veterinary|nutrition|treat|treats|chew|chews|tier|hund|katze|futter|haustier|chien|chat|animalerie|mascota|perro|gato|ração|cachorro)\b|ペット|犬|猫|반려동물|강아지|고양이)",
    re.I,
)
INDUSTRY_TERMS = re.compile(
    r"launch|unveil|introduc|new |innovation|trend|market|growth|research|study|science|nutrition|ingredient|packag|sustainab|retail|store|channel|consumer|shopper|category|sales|demand|ecommerce|e-commerce|distribution|product|food|treat|supplement|diet|formula|format|flavo[u]?r|texture|premium|functional|health|wellness|veterinary|technology|survey|report|expan|partnership|acqui|merger|investment|factory|facility|production|manufactur|supply|regulat|recall|safety|neu|neuheit|tendance|nouveau|lancement|新商品|新製品|発売|トレンド|혁신|신제품|tendência|lançamento|innovación|tendencia",
    re.I,
)
ADMIN_TERMS = re.compile(
    r"\b(?:appoint(?:ed|ment|s)?|named?\s+(?:as\s+)?(?:ceo|cfo|coo|cto|chief|president|director|chair|chairman|chairwoman)|chief\s+(?:executive|financial|operating|technology|marketing|people|human resources)\s+officer|board\s+(?:member|director|appointment|change|changes)|executive\s+(?:appointment|change|changes|team)|leadership\s+(?:appointment|change|changes|transition)|management\s+(?:appointment|change|changes)|succession|resign(?:s|ed|ation)?|retire(?:s|d|ment)?|departure|steps?\s+down|joins?\s+(?:the\s+)?(?:board|leadership|management|executive)|promot(?:ed|ion)|new\s+(?:ceo|cfo|coo|cto|chair|president)|governance|annual\s+general\s+meeting|agm\b|proxy\s+statement|director\s+election|committee\s+appointment|organizational\s+change|restructur(?:ing|e)\s+(?:the\s+)?(?:leadership|management|organization))\b",
    re.I,
)
STATIC_PAGE_TERMS = re.compile(
    r"privacy|cookie|terms of use|contact us|careers|sign in|login|accessibility|sitemap|newsletter|facebook|instagram|linkedin|youtube|x.com|twitter|purpose,? vision|values|about us|our purpose|our approach|documents?\s*&?\s*polic|reports? and publications?|market opportunity|corporate governance|investor relations|our strategy|our history|our business|who we are",
    re.I,
)
NEWS_PATH = re.compile(r"/(?:news|press|media|release|releases|article|articles|story|stories)(?:/|[-_])|news-details|press-releases", re.I)
STATIC_PATH = re.compile(r"/(?:about-us|about|governance|leadership|board|careers|sustainability|policies|documents|investors?|investor-relations)(?:/|$)", re.I)


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


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")


def clean_url(base, href):
    if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
        return None
    u = urllib.parse.urljoin(base, href)
    p = urllib.parse.urlparse(u)
    if p.scheme not in ("http", "https"):
        return None
    if re.search(r"\.(jpg|jpeg|png|gif|webp|svg|pdf|css|js|zip)(\?|$)", p.path, re.I):
        return None
    return urllib.parse.urlunparse((p.scheme, p.netloc, p.path, p.params, p.query, ""))


def same_host(a, b):
    ah = (urllib.parse.urlparse(a).hostname or "").lower().removeprefix("www.")
    bh = (urllib.parse.urlparse(b).hostname or "").lower().removeprefix("www.")
    return ah == bh or ah.endswith("." + bh) or bh.endswith("." + ah)


def clean_text(text):
    text = html_lib.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def compact_summary(text, max_chars=420):
    text = clean_text(text)
    if not text:
        return ""
    text = re.sub(r"^(?:read more|learn more|click here)\s*[:\-–—]?\s*", "", text, flags=re.I)
    parts = re.split(r"(?<=[.!?。！？])\s+", text)
    summary = " ".join(parts[:2]).strip()
    if len(summary) > max_chars:
        summary = summary[:max_chars].rsplit(" ", 1)[0].rstrip(" ,;:，；：") + "…"
    return summary


def topic_for(title):
    t = title.lower()
    if re.search(r"trend|market|growth|consumer|shopper|survey|report|tendance|tendência|tendencia|トレンド", t):
        return "市场趋势"
    if re.search(r"nutrition|ingredient|science|research|study|health|wellness|veterinary", t):
        return "营养 / 科研"
    if re.search(r"packag|sustainab|recycl|material", t):
        return "包装 / 可持续"
    if re.search(r"retail|store|channel|ecommerce|e-commerce|marketplace|distribution", t):
        return "渠道 / 零售"
    if re.search(r"launch|unveil|introduc|new |neuheit|nouveau|新商品|新製品|発売|신제품|lançamento|lancement", t):
        return "新品 / 创新"
    if re.search(r"acqui|partner|expand|investment|merger|factory|facility|production", t):
        return "产业动态"
    return "行业新闻"


def fingerprint(title):
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", title.lower())
    return s[:180]


def normalize_date(raw):
    if not raw:
        return None
    raw = str(raw).strip()
    try:
        if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
            return raw + "T00:00:00Z"
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except Exception:
        pass
    for fmt in ("%Y/%m/%d", "%Y.%m.%d", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        except Exception:
            pass
    return None


def infer_date_from_text_url(title, url):
    text = f"{title} {urllib.parse.unquote(url)}"
    patterns = [
        r"(?P<y>20\d{2})[-/年](?P<m>0?[1-9]|1[0-2])[-/月](?P<d>0?[1-9]|[12]\d|3[01])(?:日)?",
        r"/(?P<y>20\d{2})/(?P<m>0[1-9]|1[0-2])(?P<d>0[1-9]|[12]\d|3[01])(?:[-_/]|$)",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            try:
                return datetime(int(m.group("y")), int(m.group("m")), int(m.group("d")), tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
            except Exception:
                pass
    return None


def extract_article_meta(url):
    try:
        page = fetch(url, timeout=8)
    except Exception:
        return {"published_at": None, "summary": ""}

    published_at = None
    date_patterns = [
        r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']article:published_time["\']',
        r'<meta[^>]+name=["\'](?:date|publish-date|publication_date|pubdate)["\'][^>]+content=["\']([^"\']+)',
        r'"datePublished"\s*:\s*"([^"]+)"',
        r'<time[^>]+datetime=["\']([^"\']+)',
    ]
    for pat in date_patterns:
        for raw in re.findall(pat, page, re.I):
            d = normalize_date(raw)
            if d:
                published_at = d
                break
        if published_at:
            break

    summary = ""
    summary_patterns = [
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:description["\']',
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']',
        r'<meta[^>]+name=["\']twitter:description["\'][^>]+content=["\']([^"\']+)',
        r'"description"\s*:\s*"((?:\\.|[^"])*)"',
    ]
    for pat in summary_patterns:
        matches = re.findall(pat, page, re.I | re.S)
        for raw in matches:
            try:
                raw = bytes(raw, "utf-8").decode("unicode_escape") if "\\u" in raw else raw
            except Exception:
                pass
            candidate = compact_summary(raw)
            if len(candidate) >= 40:
                summary = candidate
                break
        if summary:
            break

    return {"published_at": published_at, "summary": summary}


def translate_to_zh(text):
    text = (text or "").strip()
    if not text:
        return ""
    if re.search(r"[\u4e00-\u9fff]", text) and not re.search(r"[\u3040-\u30ff\uac00-\ud7af]", text) and not re.search(r"[A-Za-z]{4,}", text):
        return text
    try:
        q = urllib.parse.urlencode({"client": "gtx", "sl": "auto", "tl": "zh-CN", "dt": "t", "q": text})
        data = json.loads(fetch("https://translate.googleapis.com/translate_a/single?" + q, timeout=8))
        translated = "".join(part[0] for part in (data[0] or []) if part and part[0])
        return translated.strip() or text
    except Exception:
        return text


def is_relevant_item(item, source=None):
    title = item.get("title", "")
    summary = item.get("summary", "")
    url = item.get("url", "")
    path = urllib.parse.unquote(urllib.parse.urlparse(url).path)
    combined = f"{title} {summary} {path}"

    if ADMIN_TERMS.search(combined):
        return False
    if STATIC_PAGE_TERMS.search(title):
        return False
    if STATIC_PATH.search(path) and not NEWS_PATH.search(path):
        return False

    pet_specific = bool((source or {}).get("pet_specific"))
    if not pet_specific and not PET_TERMS.search(combined):
        return False
    if not INDUSTRY_TERMS.search(combined):
        return False
    return True


def scan_html(source):
    page = fetch(source["url"])
    parser = AnchorParser()
    parser.feed(page)
    out = []
    patterns = source.get("link_patterns") or []
    for href, text in parser.links:
        url = clean_url(source["url"], href)
        if not url or (source.get("same_domain_only", True) and not same_host(url, source["url"])):
            continue
        if patterns and not any(pat in url for pat in patterns):
            continue
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 12 or len(text) > 260 or STATIC_PAGE_TERMS.search(text):
            continue
        candidate = {"title": text[:240], "url": url, "published_at": infer_date_from_text_url(text, url), "publisher": source["name"], "summary": ""}
        if not is_relevant_item(candidate, source):
            continue
        out.append(candidate)
    dedup = {}
    for x in out:
        dedup.setdefault(x["url"], x)
    return list(dedup.values())[:200]


def scan_google_news(source):
    params = urllib.parse.urlencode({"q": source["query"], "hl": "en", "gl": "US", "ceid": "US:en"})
    root = ET.fromstring(fetch("https://news.google.com/rss/search?" + params))
    out = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        description = compact_summary(item.findtext("description") or "")
        source_el = item.find("source")
        publisher = (source_el.text or "").strip() if source_el is not None else source["name"]
        if not title or not link:
            continue
        published_at = None
        if pub:
            try:
                published_at = email.utils.parsedate_to_datetime(pub).astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            except Exception:
                pass
        candidate = {"title": title[:240], "url": link, "published_at": published_at, "publisher": publisher, "summary": description}
        if not is_relevant_item(candidate, source):
            continue
        out.append(candidate)
    return out[:100]


def parse_scope():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channels", default="all")
    args = ap.parse_args()
    raw = args.channels.strip()
    if raw == "all":
        return None, "all"
    selected = {x.strip() for x in raw.split(",") if x.strip()}
    invalid = selected - VALID_CHANNELS
    if invalid:
        raise SystemExit("Unknown channel(s): " + ", ".join(sorted(invalid)))
    return selected, ",".join(sorted(selected))


def main():
    selected, scope = parse_scope()
    cfg = load_json(CONFIG, {"sources": []})
    old = load_json(OUT, {"items": []})
    state = load_json(STATE, {"sources": {}})
    source_by_id = {s.get("id"): s for s in cfg.get("sources", [])}
    checked = now_iso()
    old_by_url = {x.get("url"): x for x in old.get("items", []) if x.get("url")}
    items = []
    source_state = state.setdefault("sources", {})
    statuses = []

    for src in cfg.get("sources", []):
        if selected is not None and src["channel_type"] not in selected:
            continue
        try:
            found = scan_google_news(src) if src.get("mode") == "google_news" else scan_html(src)
            for x in found:
                previous = old_by_url.get(x["url"], {})
                items.append({
                    "id": previous.get("id") or f"{src['id']}-{abs(hash(x['url']))}",
                    "title": x["title"],
                    "title_zh": previous.get("title_zh", ""),
                    "summary": x.get("summary") or previous.get("summary", ""),
                    "summary_zh": previous.get("summary_zh", ""),
                    "url": x["url"],
                    "publisher": x.get("publisher") or src["name"],
                    "source_name": src["name"],
                    "source_id": src["id"],
                    "channel_type": src["channel_type"],
                    "region": src.get("region", "Global"),
                    "country": src.get("country", "Global"),
                    "topic": topic_for(x["title"]),
                    "published_at": x.get("published_at") or previous.get("published_at"),
                    "discovered_at": previous.get("discovered_at") or checked,
                })
            source_state[src["id"]] = {"status": "ok", "checked_at": checked, "items_found": len(found)}
            statuses.append({"id": src["id"], "name": src["name"], "channel_type": src["channel_type"], "status": "ok", "items_found": len(found)})
        except Exception as exc:
            source_state[src["id"]] = {"status": "error", "checked_at": checked, "error": str(exc)[:240]}
            statuses.append({"id": src["id"], "name": src["name"], "channel_type": src["channel_type"], "status": "error", "items_found": 0})
        time.sleep(0.15)

    if selected is not None:
        items.extend(x for x in old.get("items", []) if x.get("channel_type") not in selected)

    items = [x for x in items if is_relevant_item(x, source_by_id.get(x.get("source_id"), {}))]

    for x in items:
        if not x.get("published_at"):
            x["published_at"] = infer_date_from_text_url(x.get("title", ""), x.get("url", ""))

    needs_meta = [
        x for x in items
        if x.get("url")
        and not x.get("url", "").startswith("https://news.google.com/")
        and (not x.get("published_at") or not x.get("summary"))
    ]
    if needs_meta:
        with ThreadPoolExecutor(max_workers=10) as ex:
            future_map = {ex.submit(extract_article_meta, x["url"]): x for x in needs_meta}
            for fut in as_completed(future_map):
                x = future_map[fut]
                try:
                    meta = fut.result()
                    if not x.get("published_at"):
                        x["published_at"] = meta.get("published_at")
                    if not x.get("summary"):
                        x["summary"] = meta.get("summary", "")
                except Exception:
                    pass

    missing_title_translations = [x for x in items if not x.get("title_zh")]
    if missing_title_translations:
        with ThreadPoolExecutor(max_workers=10) as ex:
            future_map = {ex.submit(translate_to_zh, x.get("title", "")): x for x in missing_title_translations}
            for fut in as_completed(future_map):
                x = future_map[fut]
                try:
                    x["title_zh"] = fut.result()
                except Exception:
                    x["title_zh"] = x.get("title", "")

    summary_jobs = [x for x in items if x.get("summary") and not x.get("summary_zh")]
    if summary_jobs:
        with ThreadPoolExecutor(max_workers=10) as ex:
            future_map = {ex.submit(translate_to_zh, compact_summary(x.get("summary", ""), 360)): x for x in summary_jobs}
            for fut in as_completed(future_map):
                x = future_map[fut]
                try:
                    x["summary_zh"] = compact_summary(fut.result(), 180)
                except Exception:
                    x["summary_zh"] = ""

    for x in items:
        x["summary_zh"] = compact_summary(x.get("summary_zh", ""), 180)
        if not x.get("summary_zh"):
            title_zh = (x.get("title_zh") or x.get("title") or "").strip()
            x["summary_zh"] = f"主要内容：{title_zh}" if title_zh else "原文摘要暂未识别。"

    cutoff = datetime.now(timezone.utc) - timedelta(days=120)
    by_url = {}
    by_title = {}

    def pub_dt(x):
        raw = x.get("published_at")
        if not raw:
            return datetime(1970, 1, 1, tzinfo=timezone.utc)
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            return datetime(1970, 1, 1, tzinfo=timezone.utc)

    for x in sorted(items, key=pub_dt):
        if x.get("published_at") and pub_dt(x) < cutoff:
            continue
        fp = fingerprint(x.get("title", ""))
        if x.get("url") in by_url or (fp and fp in by_title):
            continue
        by_url[x.get("url")] = x
        if fp:
            by_title[fp] = x

    final = sorted(by_url.values(), key=pub_dt, reverse=True)[:1500]
    save_json(OUT, {"generated_at": checked, "last_scan_scope": scope, "items": final, "source_status": statuses})
    save_json(STATE, {"generated_at": checked, "last_scan_scope": scope, "sources": source_state})
    print(
        f"Hotspot scan scope: {scope}; sources: {len(statuses)}; items: {len(final)}; "
        f"translated: {sum(1 for x in final if x.get('title_zh'))}; "
        f"summaries: {sum(1 for x in final if x.get('summary_zh'))}; "
        f"dated: {sum(1 for x in final if x.get('published_at'))}"
    )


if __name__ == "__main__":
    main()
