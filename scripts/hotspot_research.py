#!/usr/bin/env python3
import argparse
import email.utils
import html as html_lib
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "research-sources.json"
DATA = ROOT / "data" / "hotspots.json"
UA = "Mozilla/5.0 (compatible; PetLaunchRadar-Research/1.0; +https://github.com/vinge777/pet-launch-radar)"

PET_TERMS = re.compile(r"\b(?:pet|pets|dog|dogs|cat|cats|canine|feline|companion animal|pet food|petfood|pet care|veterinary)\b", re.I)
RESEARCH_TERMS = re.compile(r"\b(?:report|research|study|survey|data|insight|analysis|science|scientific|nutrition|guideline|market|trend|innovation|microbiome|feeding|diet|ingredient|processing|health|wellness)\b", re.I)
ADMIN_TERMS = re.compile(r"\b(?:appoint|appointment|ceo|cfo|coo|cto|board member|board director|leadership change|management change|resign|retire|promotion|annual general meeting|agm|governance)\b", re.I)
FOOD_TERMS = re.compile(r"\b(?:pet food|dog food|cat food|food|nutrition|nutritional|diet|feeding|feed|treat|treats|chew|chews|wet food|dry food|kibble|fresh food|frozen|freeze[- ]?dried|air[- ]?dried|raw food|supplement|supplements|ingredient|ingredients|protein|microbiome|digestibility|palatability|formula|formulation|extrusion|retort|canned|shelf life|probiotic|prebiotic)\b", re.I)
SUPPLY_TERMS = re.compile(r"\b(?:toy|toys|collar|leash|harness|bed|bedding|litter|grooming|apparel|clothing|accessor|smart feeder|camera|tracker|crate|carrier|bowl)\b", re.I)


def fetch(url, timeout=18):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clean_text(text):
    text = html_lib.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def compact(text, limit=420):
    text = clean_text(text)
    if len(text) <= limit:
        return text
    clipped = text[:limit]
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0]
    return clipped.rstrip(" ,;:，；：") + "…"


def translate_zh(text):
    text = clean_text(text)
    if not text:
        return ""
    if re.search(r"[\u4e00-\u9fff]", text) and not re.search(r"[A-Za-z]{4,}", text):
        return text
    try:
        q = urllib.parse.urlencode({"client": "gtx", "sl": "auto", "tl": "zh-CN", "dt": "t", "q": text})
        data = json.loads(fetch("https://translate.googleapis.com/translate_a/single?" + q, timeout=8))
        return "".join(p[0] for p in (data[0] or []) if p and p[0]).strip() or text
    except Exception:
        return text


def parse_date(raw):
    if not raw:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(raw)
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except Exception:
        return None


def segment_for(text, default="industry"):
    food = len(FOOD_TERMS.findall(text or ""))
    supplies = len(SUPPLY_TERMS.findall(text or ""))
    if food and supplies and abs(food - supplies) <= 1:
        return "industry"
    if food > supplies:
        return "food"
    if supplies > food:
        return "supplies"
    return default if default in {"food", "supplies", "industry"} else "industry"


def subcategory(text, segment):
    t = text or ""
    if segment == "food":
        if re.search(r"microbiome|digest|gut|nutrition|nutrient|diet|feeding|health|probiotic|prebiotic", t, re.I):
            return "营养 / 健康科研"
        if re.search(r"ingredient|protein|upcycl|novel|grain|starch|fiber|fibre", t, re.I):
            return "原料 / 配方科研"
        if re.search(r"process|extrusion|retort|canned|manufactur|shelf life|safety|palatability", t, re.I):
            return "加工 / 食品安全"
        if re.search(r"market|consumer|shopper|sales|spend|trend|premium|fresh|frozen", t, re.I):
            return "食品市场 / 消费趋势"
        return "宠物食品研究"
    if segment == "supplies":
        return "宠物用品研究"
    return "市场研究 / 行业数据"


def fingerprint(title):
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", (title or "").lower())[:180]


def scan_source(source):
    params = urllib.parse.urlencode({"q": source["query"], "hl": "en", "gl": "US", "ceid": "US:en"})
    root = ET.fromstring(fetch("https://news.google.com/rss/search?" + params))
    out = []
    for node in root.findall(".//item"):
        title = clean_text(node.findtext("title") or "")
        link = clean_text(node.findtext("link") or "")
        description = compact(node.findtext("description") or "", 420)
        pub = parse_date(node.findtext("pubDate") or "")
        source_el = node.find("source")
        publisher = clean_text(source_el.text if source_el is not None else source["name"])
        hay = f"{title} {description}"
        if not title or not link or ADMIN_TERMS.search(hay):
            continue
        if not PET_TERMS.search(hay) or not RESEARCH_TERMS.search(hay):
            continue
        seg = segment_for(hay, source.get("focus", "industry"))
        out.append({
            "title": title[:240],
            "summary": description,
            "url": link,
            "publisher": publisher or source["name"],
            "published_at": pub,
            "segment": seg,
            "subcategory_zh": subcategory(hay, seg),
        })
    return out[:60]


def build_item(source, raw, previous=None):
    previous = previous or {}
    seg = raw.get("segment") or segment_for(f"{raw.get('title','')} {raw.get('summary','')}", source.get("focus", "industry"))
    title = raw.get("title", "").strip()
    summary = compact(raw.get("summary", ""), 420)
    return {
        "id": previous.get("id") or f"{source['id']}-{abs(hash(raw.get('url') or title))}",
        "title": title,
        "title_zh": previous.get("title_zh", ""),
        "summary": summary,
        "summary_zh": previous.get("summary_zh", ""),
        "url": raw.get("url", ""),
        "publisher": raw.get("publisher") or source["name"],
        "source_name": source["name"],
        "source_id": source["id"],
        "channel_type": "research_institute",
        "region": source.get("region", "Global"),
        "country": source.get("country", "Global"),
        "topic": "研究 / 报告",
        "published_at": parse_date(raw.get("published_at")),
        "discovered_at": previous.get("discovered_at") or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "segment": seg,
        "segment_zh": {"food": "宠物食品", "supplies": "宠物用品", "industry": "行业综合"}.get(seg, "行业综合"),
        "subcategory_zh": raw.get("subcategory_zh") or subcategory(f"{title} {summary}", seg),
        "food_priority": 4 if seg == "food" else 0,
        "research_source": True,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channels", default="all")
    args = ap.parse_args()
    scope = args.channels.strip() or "all"
    if scope not in {"all", "research_institute"}:
        print(f"Research scan skipped for scope: {scope}")
        return

    cfg = load_json(CONFIG, {"sources": [], "seed_items": []})
    data = load_json(DATA, {"items": [], "source_status": []})
    old_items = data.get("items", [])
    old_by_url = {x.get("url"): x for x in old_items if x.get("url")}
    source_by_id = {s["id"]: s for s in cfg.get("sources", [])}

    # Remove prior research rows before rebuilding them, while keeping all other hotspot channels unchanged.
    items = [x for x in old_items if x.get("channel_type") != "research_institute"]
    research_items = []
    statuses = []

    for seed in cfg.get("seed_items", []):
        src = source_by_id.get(seed.get("source_id"))
        if not src:
            continue
        research_items.append(build_item(src, seed, old_by_url.get(seed.get("url"))))

    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(scan_source, src): src for src in cfg.get("sources", [])}
        for fut in as_completed(futures):
            src = futures[fut]
            try:
                found = fut.result()
                statuses.append({"id": src["id"], "name": src["name"], "channel_type": "research_institute", "status": "ok", "items_found": len(found)})
                for raw in found:
                    research_items.append(build_item(src, raw, old_by_url.get(raw.get("url"))))
            except Exception as exc:
                statuses.append({"id": src["id"], "name": src["name"], "channel_type": "research_institute", "status": "error", "items_found": 0, "error": str(exc)[:180]})

    # Deduplicate research rows by URL and normalized title, preferring rows with an original publication date.
    dedup_url = {}
    dedup_title = {}
    for x in sorted(research_items, key=lambda r: bool(r.get("published_at")), reverse=True):
        fp = fingerprint(x.get("title"))
        if x.get("url") and x["url"] in dedup_url:
            continue
        if fp and fp in dedup_title:
            continue
        if x.get("url"):
            dedup_url[x["url"]] = x
        if fp:
            dedup_title[fp] = x

    final_research = list(dedup_url.values())

    # Translate research titles and summaries in parallel so the page remains Chinese-first.
    title_jobs = [x for x in final_research if not x.get("title_zh")]
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(translate_zh, x.get("title", "")): x for x in title_jobs}
        for fut in as_completed(futs):
            x = futs[fut]
            try:
                x["title_zh"] = fut.result()
            except Exception:
                x["title_zh"] = x.get("title", "")

    summary_jobs = [x for x in final_research if x.get("summary") and not x.get("summary_zh")]
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(translate_zh, compact(x.get("summary", ""), 360)): x for x in summary_jobs}
        for fut in as_completed(futs):
            x = futs[fut]
            try:
                x["summary_zh"] = compact(fut.result(), 180)
            except Exception:
                x["summary_zh"] = ""

    for x in final_research:
        if not x.get("summary_zh"):
            x["summary_zh"] = f"研究 / 报告：{x.get('title_zh') or x.get('title') or '原文摘要暂未识别'}。"

    items.extend(final_research)
    data["items"] = items
    old_status = [s for s in data.get("source_status", []) if s.get("channel_type") != "research_institute"]
    data["source_status"] = old_status + statuses
    data["research_scan_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    save_json(DATA, data)
    print(f"Research hotspot scan: sources={len(statuses)} reports={len(final_research)} food={sum(1 for x in final_research if x.get('segment') == 'food')}")


if __name__ == "__main__":
    main()
