#!/usr/bin/env python3
import html as html_lib
import json
import re
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data' / 'hotspots.json'
UA = 'Mozilla/5.0 (compatible; PetLaunchRadar/1.0; +https://github.com/vinge777/pet-launch-radar)'

LOW_VALUE = re.compile(
    r'anniversary|celebrates?\s+\d+\s+years|years in the community|community event|charity|fundrais|donat|competition|giveaway|photo contest|top tips?|how to|\bguide to\b|advice|method to|keep your (?:dog|cat|pet)|cool your (?:dog|cat|pet)|pet-friendly day out|meet the team|employee story|colleague story|behind the scenes|award(?:ed|s)?\b',
    re.I,
)
ADMIN = re.compile(
    r'\b(?:appoint(?:ed|ment|s)?|named?\s+(?:as\s+)?(?:ceo|cfo|coo|cto|chief|president|director|chair|chairman|chairwoman)|chief\s+(?:executive|financial|operating|technology|marketing|people|human resources)\s+officer|board\s+(?:member|director|appointment|change|changes)|executive\s+(?:appointment|change|changes|team)|leadership\s+(?:appointment|change|changes|transition)|management\s+(?:appointment|change|changes)|succession|resign(?:s|ed|ation)?|retire(?:s|d|ment)?|departure|steps?\s+down|joins?\s+(?:the\s+)?(?:board|leadership|management|executive)|promot(?:ed|ion)|new\s+(?:ceo|cfo|coo|cto|chair|president)|governance|annual\s+general\s+meeting|agm\b|proxy\s+statement|director\s+election|committee\s+appointment|organizational\s+change)\b',
    re.I,
)


def fetch(url, timeout=8):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en-US,en;q=0.8'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        charset = r.headers.get_content_charset() or 'utf-8'
        return raw.decode(charset, errors='replace')


def clean(text):
    text = html_lib.unescape(re.sub(r'<[^>]+>', ' ', text or ''))
    return re.sub(r'\s+', ' ', text).strip()


def fp(text):
    return re.sub(r'[^a-z0-9\u4e00-\u9fff]+', '', clean(text).lower())[:180]


def weak_summary(summary, title):
    s, t = clean(summary), clean(title)
    if not s or len(s) < 55:
        return True
    sf, tf = fp(s), fp(t)
    return bool(sf and tf and (sf == tf or sf.startswith(tf) or tf.startswith(sf)))


def compact(text, limit=420):
    text = clean(text)
    if not text:
        return ''
    parts = re.split(r'(?<=[.!?。！？])\s+', text)
    out = ' '.join(parts[:2]).strip()
    if len(out) > limit:
        out = out[:limit].rsplit(' ', 1)[0].rstrip(' ,;:，；：') + '…'
    return out


def extract_intro(url):
    try:
        page = fetch(url)
    except Exception:
        return ''
    candidates = []
    patterns = [
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+name=["\']twitter:description["\'][^>]+content=["\']([^"\']+)',
    ]
    for pat in patterns:
        for raw in re.findall(pat, page, re.I | re.S):
            txt = compact(raw, 500)
            if len(txt) >= 70:
                candidates.append(txt)
    for raw in re.findall(r'<p\b[^>]*>(.*?)</p>', page, re.I | re.S):
        txt = compact(raw, 500)
        if len(txt) < 70:
            continue
        if re.search(r'cookie|privacy|newsletter|subscribe|terms and conditions|all rights reserved|follow us|contact us|media enquiries', txt, re.I):
            continue
        candidates.append(txt)
        if len(candidates) >= 4:
            break
    if not candidates:
        return ''
    return compact(' '.join(candidates[:2]), 500)


def translate(text):
    text = clean(text)
    if not text:
        return ''
    if re.search(r'[\u4e00-\u9fff]', text) and not re.search(r'[\u3040-\u30ff\uac00-\ud7af]', text) and not re.search(r'[A-Za-z]{4,}', text):
        return text
    try:
        q = urllib.parse.urlencode({'client':'gtx','sl':'auto','tl':'zh-CN','dt':'t','q':text})
        data = json.loads(fetch('https://translate.googleapis.com/translate_a/single?' + q, timeout=8))
        return ''.join(p[0] for p in (data[0] or []) if p and p[0]).strip() or text
    except Exception:
        return text


def main():
    data = json.loads(DATA.read_text(encoding='utf-8'))
    items = []
    for x in data.get('items', []):
        hay = ' '.join([x.get('title',''), x.get('summary',''), x.get('url','')])
        if ADMIN.search(hay) or LOW_VALUE.search(hay):
            continue
        items.append(x)

    refill = [x for x in items if weak_summary(x.get('summary',''), x.get('title','')) and not x.get('url','').startswith('https://news.google.com/')]
    if refill:
        with ThreadPoolExecutor(max_workers=10) as ex:
            futs = {ex.submit(extract_intro, x.get('url','')): x for x in refill}
            for fut in as_completed(futs):
                x = futs[fut]
                try:
                    intro = fut.result()
                except Exception:
                    intro = ''
                if intro and not weak_summary(intro, x.get('title','')):
                    x['summary'] = intro
                    x['summary_zh'] = ''

    to_translate = [x for x in items if x.get('summary') and (not x.get('summary_zh') or weak_summary(x.get('summary_zh',''), x.get('title_zh') or x.get('title','')))]
    if to_translate:
        with ThreadPoolExecutor(max_workers=10) as ex:
            futs = {ex.submit(translate, compact(x.get('summary',''), 360)): x for x in to_translate}
            for fut in as_completed(futs):
                x = futs[fut]
                try:
                    x['summary_zh'] = compact(fut.result(), 180)
                except Exception:
                    x['summary_zh'] = ''

    for x in items:
        if not x.get('summary_zh') or weak_summary(x.get('summary_zh',''), x.get('title_zh') or x.get('title','')):
            title = clean(x.get('title_zh') or x.get('title') or '')
            topic = x.get('topic') or '行业动态'
            x['summary_zh'] = f'{topic}：文章主要介绍{title.rstrip("。！？!?")}。' if title else '原文摘要暂未识别。'

    data['items'] = items
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Hotspot quality pass: kept={len(items)}, summaries={sum(1 for x in items if x.get("summary_zh"))}')


if __name__ == '__main__':
    main()
