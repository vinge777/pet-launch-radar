#!/usr/bin/env python3
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DISCOVERY = ROOT / 'data' / 'discovery.json'
PRODUCTS = ROOT / 'data' / 'products.json'
BRANDS = ROOT / 'data' / 'brands.json'
SOURCES = ROOT / 'config' / 'sources.json'
UA = 'Mozilla/5.0 (compatible; PetLaunchRadar/1.0; +https://github.com/vinge777/pet-launch-radar)'

STRONG_NEWNESS = re.compile(r'\b(new|newly|launch(?:ed|es|ing)?|introduc(?:e|ed|es|ing)|unveil(?:ed|s|ing)?|debut(?:ed|s|ing)?|new arrival|new at)\b|neuheit|nouveau|nouveaut|新商品|新製品|発売|신제품|lançamento|lanzamiento', re.I)
PRODUCT_HINT = re.compile(r'food|treat|chew|supplement|diet|formula|recipe|wet|dry|freeze[- ]?dried|air[- ]?dried|kibble|broth|mousse|pouch|can|snack|toy|collar|leash|litter|bed|shampoo|groom|bowl|feeder', re.I)
PRODUCT_URL_HINT = re.compile(r'/(?:product|products|ip|p|shop|dog-products|cat-products)/|/dp/\d+', re.I)
SEASONAL = re.compile(r'halloween|holiday|christmas|xmas|limited[- ]edition|seasonal|spooky|boo\b', re.I)
OFFICIAL_SOURCE_BRANDS = {'asia-petio': 'Petio'}


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
    except Exception:
        return default


def save_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def fetch(url, timeout=7):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en-US,en;q=0.8'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode(resp.headers.get_content_charset() or 'utf-8', errors='replace')


def parse_dt(raw):
    try:
        return datetime.fromisoformat((raw or '').replace('Z', '+00:00'))
    except Exception:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


def norm(s):
    return re.sub(r'[^a-z0-9]+', '', (s or '').lower())


def infer_species(text):
    t = (text or '').lower()
    dog = bool(re.search(r'\bdog|dogs|puppy|puppies|canine\b|犬|강아지|perro|cachorro|chien|hund', t))
    cat = bool(re.search(r'\bcat|cats|kitten|kittens|feline\b|猫|고양이|gato|chat|katze', t))
    if dog and cat: return 'Multi'
    if cat: return 'Cat'
    if dog: return 'Dog'
    return 'Other'


def infer_category(text):
    t = (text or '').lower()
    if re.search(r'supplement|probiotic|vitamin|joint|omega|calming', t): return 'Supplements'
    if re.search(r'treat|snack|chew|jerky|dental', t): return 'Treats'
    if re.search(r'wet food|pouch|mousse|broth|stew|can(?:ned)? food', t): return 'Wet Food'
    if re.search(r'dry food|kibble|baked food', t): return 'Dry Food'
    if re.search(r'freeze[- ]?dried', t): return 'Freeze-dried'
    if re.search(r'toy|collar|leash|bed|bowl|feeder|litter|groom|shampoo', t): return 'Accessories'
    return 'Food' if re.search(r'food|diet|formula|recipe|meal', t) else 'Other'


def looks_like_product_page(url, html=''):
    if PRODUCT_URL_HINT.search(urllib.parse.urlparse(url).path):
        return True
    sample = html[:350000]
    return bool(re.search(r'"@type"\s*:\s*"Product"|itemtype=["\'][^"\']*schema\.org/Product|"productID"\s*:|"sku"\s*:', sample, re.I))


def extract_review_count(html):
    patterns = [
        r'"reviewCount"\s*:\s*"?(\d{1,7})',
        r'"ratingCount"\s*:\s*"?(\d{1,7})',
        r'Rated[^<]{0,80}?([\d,]+)\s+Ratings',
        r'([\d,]+)\s+(?:ratings|reviews)\b',
    ]
    counts = []
    for pat in patterns:
        for raw in re.findall(pat, html[:500000], re.I):
            try:
                counts.append(int(str(raw).replace(',', '')))
            except Exception:
                pass
    return max(counts) if counts else None


def find_brand(text, brands):
    low = (text or '').lower()
    matches = [b for b in brands if b.get('name','').lower() in low]
    return sorted(matches, key=lambda x: len(x.get('name','')), reverse=True)[0] if matches else None


def clean_product_name(title, brand_name):
    name = re.sub(r'\s+-\s+[^-]{2,80}$', '', (title or '').strip())
    name = re.sub(r'^(?:new\s+)?' + re.escape(brand_name) + r'\s*[:\-–—]?\s*', '', name, flags=re.I)
    name = re.sub(r'\b(?:launches?|launched|introduces?|introduced|unveils?|unveiled|debuts?)\b\s*', '', name, flags=re.I)
    return name.strip(' :-–—')[:180] or title[:180]


def keep_existing_auto(p):
    if not str(p.get('id','')).startswith('auto-'):
        return True
    if 'official' in (p.get('evidence') or []):
        return True
    sources = p.get('sources') or []
    has_detail = any(s.get('page_type') == 'product_detail' for s in sources)
    return bool(has_detail and SEASONAL.search(p.get('product_name','')))


def main():
    discovery = load_json(DISCOVERY, {'candidates': []})
    products_doc = load_json(PRODUCTS, {'products': []})
    brands_doc = load_json(BRANDS, {'brands': []})
    sources_doc = load_json(SOURCES, {'sources': []})

    brands = [b for b in brands_doc.get('brands', []) if b.get('active', True) and b.get('origin_country') != 'China']
    source_map = {s.get('id'): s for s in sources_doc.get('sources', [])}
    brand_by_name = {b.get('name'): b for b in brands}
    before_cleanup = len(products_doc.get('products', []))
    products = [p for p in products_doc.get('products', []) if keep_existing_auto(p)]
    removed_old_auto = before_cleanup - len(products)
    existing_urls = {p.get('product_url') for p in products if p.get('product_url')}
    existing_keys = {norm((p.get('brand') or '') + ' ' + (p.get('product_name') or '')) for p in products}

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=21)
    promoted = 0
    checked = 0
    fetched = 0

    for c in sorted(discovery.get('candidates', []), key=lambda x: x.get('discovered_at',''), reverse=True):
        if c.get('review_status') not in (None, '', 'pending') or parse_dt(c.get('discovered_at')) < cutoff:
            continue
        checked += 1
        src = source_map.get(c.get('source_id'), {})
        title = c.get('title', '')
        url = c.get('url', '')
        source_name = src.get('name') or c.get('source_name') or ''
        ch = src.get('channel_type')
        dedicated_new_source = bool(re.search(r'new|neuheit|nouveau|新品|新商品|new arrivals|new at', source_name, re.I))
        official_source = ch == 'brand_official'
        strong_launch = bool(STRONG_NEWNESS.search(title))

        # News and trade-media hits are discovery evidence only, never automatic product entries.
        if ch == 'trade_media':
            continue
        if not (dedicated_new_source or official_source):
            continue

        pre_hay = ' '.join([title, urllib.parse.unquote(url)])
        brand = find_brand(pre_hay, brands)
        if not brand and c.get('source_id') in OFFICIAL_SOURCE_BRANDS:
            brand = brand_by_name.get(OFFICIAL_SOURCE_BRANDS[c.get('source_id')])
        if not brand:
            continue

        page = ''
        product_page = False
        review_count = None
        try:
            page = fetch(url)
            fetched += 1
            product_page = looks_like_product_page(url, page)
            review_count = extract_review_count(page)
        except Exception:
            product_page = bool(PRODUCT_URL_HINT.search(urllib.parse.urlparse(url).path))

        hay = ' '.join([pre_hay, re.sub(r'<[^>]+>', ' ', page[:100000])])
        if not PRODUCT_HINT.search(hay):
            continue

        if ch in {'specialty_retail','mass_retail','drugstore','marketplace'}:
            if not product_page or not dedicated_new_source:
                continue
            # Avoid old SKUs that are merely newly listed by a retailer.
            if review_count is not None and review_count > 50:
                c['review_status'] = 'rejected_old_reviews'
                continue
            if review_count is None and not SEASONAL.search(hay):
                continue

        if official_source and not (strong_launch or product_page):
            continue

        product_name = clean_product_name(title, brand['name'])
        key = norm(brand['name'] + ' ' + product_name)
        if key in existing_keys or (product_page and url in existing_urls):
            c['review_status'] = 'duplicate'
            continue

        evidence = 'official' if official_source else 'retailer'
        p = {
            'id': f"auto-{abs(hash(url))}",
            'brand': brand['name'], 'brand_origin_country': brand['origin_country'], 'origin_verified': True,
            'product_name': product_name, 'species': infer_species(hay), 'category': infer_category(hay),
            'market_region': c.get('region') or (brand.get('market_regions') or [''])[0], 'country': c.get('country') or '',
            'launch_date': None, 'launch_date_verified': False,
            'first_seen_at': c.get('discovered_at') or now.isoformat().replace('+00:00','Z'),
            'newness_status': 'verified' if official_source else 'candidate_verified',
            'newness_type': 'new_product_or_sku', 'newness_confidence': 'high' if official_source else 'medium',
            'summary': f"自动扫描从 {source_name} 发现。已确认品牌原产地为非中国，并通过单品页与新品信号核验。" + (f" 当前识别到 {review_count} 条评分/评论。" if review_count is not None else ''),
            'tags': ['Auto-verified', 'New Arrival'], 'image_url': '',
            'evidence': [evidence], 'product_url': url,
            'sources': [{'name': source_name, 'url': url, 'page_type': 'product_detail'}]
        }
        products.append(p)
        existing_keys.add(key)
        existing_urls.add(url)
        c['review_status'] = 'promoted_auto'
        c['promoted_at'] = now.isoformat().replace('+00:00','Z')
        promoted += 1
        if promoted >= 50: break

    products.sort(key=lambda x: x.get('first_seen_at',''), reverse=True)
    stamp = now.replace(microsecond=0).isoformat().replace('+00:00','Z')
    save_json(PRODUCTS, {'generated_at': stamp, 'products': products[:2500]})
    save_json(DISCOVERY, {**discovery, 'generated_at': stamp})
    print(f'Candidate promotion: checked={checked}; fetched={fetched}; promoted={promoted}; removed_weak_auto={removed_old_auto}; products={len(products)}')


if __name__ == '__main__':
    main()
