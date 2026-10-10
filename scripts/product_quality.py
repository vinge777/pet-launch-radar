#!/usr/bin/env python3
import html
import json
import re
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = ROOT / 'data' / 'products.json'
DISCOVERY = ROOT / 'data' / 'discovery.json'

NON_PRODUCT = re.compile(r'brand identity|rebrand|branding|visual identity|new logo|website|metaverse|campaign|promotion|partnership|appoint|executive|ceo|cfo|board', re.I)
RETURNING_PRODUCT = re.compile(r'brings?[-\s]?back|returns?|returning|back[-\s]for|relaunch(?:es|ed)?', re.I)
LAUNCH_VERBS = re.compile(r'\b(brings? back|launches?|launched|introduces?|introduced|unveils?|unveiled|debuts?|debuted|releases?|released)\b', re.I)


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
    except Exception:
        return default


def save_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def parse_dt(raw):
    try:
        dt = datetime.fromisoformat((raw or '').replace('Z', '+00:00'))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def source_name(p):
    src = (p.get('sources') or [{}])[0]
    return src.get('name') or ''


def source_url(p):
    src = (p.get('sources') or [{}])[0]
    return src.get('url') or ''


def is_auto(p):
    return str(p.get('id','')).startswith('auto-')


def normalize_article_product_name(p):
    name = html.unescape(str(p.get('product_name') or '')).strip()
    url = source_url(p)
    src = source_name(p)
    if 'Pet Food Processing' in src and url:
        slug = urllib.parse.unquote(urllib.parse.urlparse(url).path.rstrip('/').split('/')[-1])
        slug = re.sub(r'^\d+[-_]', '', slug)
        candidate = re.sub(r'[-_]+', ' ', slug)
        brand = re.escape(str(p.get('brand') or ''))
        candidate = re.sub(r'^' + brand + r'\s+', '', candidate, flags=re.I)
        candidate = LAUNCH_VERBS.sub('', candidate, count=1)
        candidate = re.sub(r'\s+', ' ', candidate).strip(' -:')
        if candidate:
            name = candidate
    p['product_name'] = re.sub(r'\s+', ' ', name).strip()
    return p


def keep(p, now):
    if not is_auto(p):
        return True, 'manual_or_curated'

    name = html.unescape(str(p.get('product_name') or ''))
    src_name = source_name(p)
    src_url = source_url(p)
    evidence = set(p.get('evidence') or [])
    species = p.get('species') or ''

    if NON_PRODUCT.search(name):
        return False, 'non_product_news'

    # A returning/relaunched old seasonal product is useful intelligence, but it belongs in
    # Global Hotspots rather than the formal new-product feed.
    if 'trade_media' in evidence and RETURNING_PRODUCT.search(name + ' ' + src_url):
        return False, 'returning_existing_product'

    # Catch navigation pollution between species-specific new-product pages.
    if re.search(r'\bcat\b', src_name, re.I) and species == 'Dog':
        return False, 'source_species_mismatch'
    if re.search(r'\bdog\b', src_name, re.I) and species == 'Cat':
        return False, 'source_species_mismatch'

    if 'trade_media' in evidence:
        # Pet Food Processing New Products is intentionally curated as a high-signal source.
        if 'Pet Food Processing' in src_name:
            return True, 'high_signal_trade_media'
        published = parse_dt(p.get('source_published_at'))
        if not published:
            return False, 'trade_media_missing_date'
        if published < now - timedelta(days=40):
            return False, 'trade_media_stale'
        return True, 'fresh_trade_media'

    if 'retailer' in evidence:
        reviews = p.get('review_count_at_detection')
        ntype = p.get('newness_type') or ''
        confidence = p.get('newness_confidence') or ''
        if ntype == 'new_retailer_listing' or confidence == 'low':
            return False, 'retailer_low_confidence'
        if reviews is None:
            if not re.search(r'halloween|holiday|christmas|xmas|seasonal|limited', name, re.I):
                return False, 'retailer_no_review_signal'
        elif int(reviews) > 25:
            return False, 'retailer_review_history'
        return True, 'retailer_strong_signal'

    return 'official' in evidence, 'official' if 'official' in evidence else 'unknown_auto'


def main():
    doc = load_json(PRODUCTS, {'products': []})
    discovery = load_json(DISCOVERY, {'candidates': []})
    now = datetime.now(timezone.utc)
    kept = []
    removed = []
    for p in doc.get('products', []):
        p = normalize_article_product_name(p)
        ok, reason = keep(p, now)
        if ok:
            kept.append(p)
        else:
            removed.append((p.get('id'), p.get('brand'), p.get('product_name'), reason))

    seen_urls = set()
    seen_keys = set()
    deduped = []
    for p in sorted(kept, key=lambda x: x.get('first_seen_at',''), reverse=True):
        url = p.get('product_url') or source_url(p)
        key = re.sub(r'[^a-z0-9]+', '', (str(p.get('brand','')) + str(p.get('product_name',''))).lower())
        if url and url in seen_urls:
            continue
        if key and key in seen_keys:
            continue
        if url: seen_urls.add(url)
        if key: seen_keys.add(key)
        deduped.append(p)

    stamp = now.replace(microsecond=0).isoformat().replace('+00:00','Z')
    save_json(PRODUCTS, {'generated_at': stamp, 'quality_gate': {'removed': len(removed), 'kept': len(deduped)}, 'products': deduped[:2500]})

    removed_ids = {x[0] for x in removed if x[0]}
    if removed_ids:
        for c in discovery.get('candidates', []):
            url = c.get('url')
            if not url:
                continue
            for p in doc.get('products', []):
                if p.get('id') in removed_ids and (p.get('product_url') == url or source_url(p) == url):
                    c['review_status'] = 'rejected_quality_gate'
                    break
        save_json(DISCOVERY, discovery)

    print(f'Product quality gate: kept={len(deduped)} removed={len(removed)}')
    for row in removed[:30]:
        print('REMOVED', row)


if __name__ == '__main__':
    main()
