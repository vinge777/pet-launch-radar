#!/usr/bin/env python3
import hashlib
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

STRONG_NEWNESS = re.compile(r'\b(new|newly|launch(?:ed|es|ing)?|introduc(?:e|ed|es|ing)|unveil(?:ed|s|ing)?|debut(?:ed|s|ing)?|rolls? out|brings? back|reformulat(?:e|ed|es|ing))\b|neuheit|nouveau|nouveaut|新商品|新製品|発売|신제품|lançamento|lanzamiento', re.I)
PRODUCT_HINT = re.compile(r'food|treat|chew|supplement|diet|formula|recipe|wet|dry|freeze[- ]?dried|air[- ]?dried|kibble|broth|mousse|pouch|can|snack|cat food|dog food|cat treat|dog treat|litter|toy|collar|leash|bed|bowl|feeder|shampoo|groom', re.I)
NON_PRODUCT_NEWS = re.compile(r'\b(metaverse|website|site|campaign|promotion|partnership|appoint|president|ceo|cfo|executive|board|facility|factory|distribution|distributor|award|study|survey|report|congress|conference|event)\b', re.I)
PRODUCT_URL_HINT = re.compile(r'/ip/|/dp/\d+|/product/|/products/|/shop/.+/\d+(?:\?|$)|\.html(?:\?|$)|/p/[^/]+', re.I)
SEASONAL = re.compile(r'halloween|holiday|christmas|xmas|limited[- ]edition|seasonal|spooky|boo\b', re.I)
OFFICIAL_SOURCE_BRANDS = {'asia-petio': 'Petio'}


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
    except Exception:
        return default


def save_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def fetch(url, timeout=8):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en-US,en;q=0.8'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode(resp.headers.get_content_charset() or 'utf-8', errors='replace')


def parse_dt(raw):
    try:
        dt = datetime.fromisoformat((raw or '').replace('Z', '+00:00'))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def norm(s):
    return re.sub(r'[^a-z0-9]+', '', (s or '').lower())


def stable_id(url):
    return 'auto-' + hashlib.sha1(url.encode('utf-8')).hexdigest()[:16]


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
    if re.search(r'supplement|probiotic|vitamin|joint|omega|calming|hairball|immune', t): return 'Supplements'
    if re.search(r'treat|snack|chew|jerky|dental', t): return 'Treats'
    if re.search(r'wet food|pouch|mousse|broth|stew|can(?:ned)? food|pate|paté', t): return 'Wet Food'
    if re.search(r'dry food|kibble|baked food', t): return 'Dry Food'
    if re.search(r'freeze[- ]?dried', t): return 'Freeze-dried'
    if re.search(r'toy|collar|leash|bed|bowl|feeder|litter|groom|shampoo', t): return 'Accessories'
    return 'Food' if re.search(r'food|diet|formula|recipe|meal', t) else 'Other'


def likely_product_url(url):
    p = urllib.parse.urlparse(url)
    text = p.path + ('?' + p.query if p.query else '')
    if re.search(r'/f/brand/|/category/|/search|/pesquisa|/specials/', text, re.I):
        return False
    return bool(PRODUCT_URL_HINT.search(text))


def looks_like_product_page(url, html=''):
    if likely_product_url(url):
        return True
    sample = html[:400000]
    return bool(re.search(r'"@type"\s*:\s*"Product"|itemtype=["\'][^"\']*schema\.org/Product|"productID"\s*:|"sku"\s*:', sample, re.I))


def extract_review_count(html):
    patterns = [
        r'"reviewCount"\s*:\s*"?(\d{1,7})',
        r'"ratingCount"\s*:\s*"?(\d{1,7})',
        r'([\d,]+)\s+(?:ratings|reviews)\b',
        r'Rating:[^<]{0,80}?\(([\d,]+)\)',
    ]
    counts = []
    for pat in patterns:
        for raw in re.findall(pat, html[:650000], re.I):
            try: counts.append(int(str(raw).replace(',', '')))
            except Exception: pass
    return max(counts) if counts else None


def extract_page_title(html):
    patterns = [
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']',
        r'<title[^>]*>(.*?)</title>',
    ]
    for pat in patterns:
        m = re.search(pat, html[:250000], re.I | re.S)
        if m:
            return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', m.group(1))).strip()[:240]
    return ''


def find_brand(text, brands):
    low = (text or '').lower()
    matches = [b for b in brands if b.get('name','').lower() in low]
    return sorted(matches, key=lambda x: len(x.get('name','')), reverse=True)[0] if matches else None


def clean_product_name(title, brand_name):
    name = (title or '').strip()
    name = re.sub(r'\s+[\-|–|—]\s+(?:PetfoodIndustry|Pet Food Processing|PR Newswire|Business Wire|[^-]{2,50})$', '', name, flags=re.I)
    name = re.sub(r'^(?:new\s+)?' + re.escape(brand_name) + r'\s*[:\-–—]?\s*', '', name, flags=re.I)
    name = re.sub(r'\b(?:launches?|launched|introduces?|introduced|unveils?|unveiled|debuts?|debuted|brings? back|reformulates?)\b\s*', '', name, flags=re.I)
    return name.strip(' :-–—')[:180] or title[:180]


def keep_existing_auto(p):
    if not str(p.get('id','')).startswith('auto-'):
        return True
    if p.get('newness_status') in {'verified','candidate_verified','retailer_new'}:
        return True
    return False


def add_product(products, existing_keys, existing_urls, c, src, brand, title, url, evidence, page_type,
                now, product_page=False, review_count=None, newness_type='new_product_or_line', confidence='medium'):
    product_name = clean_product_name(title, brand['name'])
    key = norm(brand['name'] + ' ' + product_name)
    if key in existing_keys or (product_page and url in existing_urls):
        c['review_status'] = 'duplicate'
        return False
    published = parse_dt(c.get('published_at'))
    is_focus = src.get('focus_group') == 'spectrum_pet_food' or brand.get('focus_group') == 'spectrum_pet_food'
    tags = ['Auto-verified', 'Launch Signal' if evidence != 'retailer' else 'Retailer New']
    if is_focus:
        tags.insert(0, 'Spectrum Focus')
    p = {
        'id': stable_id(url),
        'brand': brand['name'],
        'brand_origin_country': brand['origin_country'],
        'origin_verified': True,
        'product_name': product_name,
        'species': infer_species(title),
        'category': infer_category(title),
        'market_region': c.get('region') or (brand.get('market_regions') or [''])[0],
        'country': c.get('country') or '',
        'launch_date': None,
        'launch_date_verified': False,
        'first_seen_at': c.get('discovered_at') or now.isoformat().replace('+00:00','Z'),
        'newness_status': 'verified' if evidence == 'official' else ('retailer_new' if evidence == 'retailer' else 'candidate_verified'),
        'newness_type': newness_type,
        'newness_confidence': confidence,
        'summary': (
            f"自动扫描从 {src.get('name') or c.get('source_name') or '公开来源'} 发现。"
            + ("Spectrum Brands 宠物食品/零食重点监测。" if is_focus else "")
            + ("品牌官方或行业新品发布信号明确。" if evidence in {'official','trade_media'} else "该商品位于渠道新品页；属于渠道新上架，尚不等同于品牌全球首发。")
            + (f" 当前识别到 {review_count} 条评分/评论。" if review_count is not None else '')
        ),
        'tags': tags,
        'image_url': '',
        'evidence': [evidence],
        'sources': [{'name': src.get('name') or c.get('source_name') or '', 'url': url, 'page_type': page_type}]
    }
    if is_focus:
        p['focus_group'] = 'spectrum_pet_food'
        p['parent_company'] = 'Spectrum Brands'
    elif brand.get('parent_company'):
        p['parent_company'] = brand.get('parent_company')
    if published:
        p['source_published_at'] = published.replace(microsecond=0).isoformat().replace('+00:00','Z')
    if product_page:
        p['product_url'] = url
    if review_count is not None:
        p['review_count_at_detection'] = review_count
    products.append(p)
    existing_keys.add(key)
    if product_page: existing_urls.add(url)
    c['review_status'] = 'promoted_auto'
    c['promoted_at'] = now.isoformat().replace('+00:00','Z')
    return True


def main():
    discovery = load_json(DISCOVERY, {'candidates': []})
    products_doc = load_json(PRODUCTS, {'products': []})
    brands_doc = load_json(BRANDS, {'brands': []})
    sources_doc = load_json(SOURCES, {'sources': []})

    brands = [b for b in brands_doc.get('brands', []) if b.get('active', True) and b.get('origin_country') != 'China']
    source_map = {s.get('id'): s for s in sources_doc.get('sources', [])}
    brand_by_name = {b.get('name'): b for b in brands}
    products = [p for p in products_doc.get('products', []) if keep_existing_auto(p)]
    existing_urls = {p.get('product_url') for p in products if p.get('product_url')}
    existing_keys = {norm((p.get('brand') or '') + ' ' + (p.get('product_name') or '')) for p in products}

    now = datetime.now(timezone.utc)
    candidate_cutoff = now - timedelta(days=30)
    news_cutoff = now - timedelta(days=35)
    promoted = 0
    checked = 0
    fetched = 0
    rejected_old = 0

    def candidate_sort_key(c):
        src = source_map.get(c.get('source_id'), {})
        try:
            priority = int(src.get('priority', 0))
        except Exception:
            priority = 0
        return (priority, c.get('discovered_at', ''))

    for c in sorted(discovery.get('candidates', []), key=candidate_sort_key, reverse=True):
        if c.get('review_status') not in (None, '', 'pending'):
            continue
        discovered = parse_dt(c.get('discovered_at'))
        if discovered and discovered < candidate_cutoff:
            continue
        checked += 1
        src = source_map.get(c.get('source_id'), {})
        title = c.get('title', '')
        url = c.get('url', '')
        ch = src.get('channel_type') or c.get('channel_type')
        official_source = ch == 'brand_official'
        new_source = bool(src.get('new_arrivals_source'))
        high_signal_launch = bool(src.get('high_signal_launch_source'))
        strong_launch = bool(STRONG_NEWNESS.search(title))
        pre_hay = ' '.join([title, urllib.parse.unquote(url)])
        mapped_brand = brand_by_name.get(src.get('brand_name')) if src.get('brand_name') else None

        if ch == 'trade_media':
            published = parse_dt(c.get('published_at'))
            if published and published < news_cutoff:
                c['review_status'] = 'rejected_stale_news'
                continue
            if not (strong_launch or high_signal_launch):
                continue
            if not PRODUCT_HINT.search(title) or NON_PRODUCT_NEWS.search(title):
                continue
            brand = mapped_brand or find_brand(title, brands)
            if not brand:
                continue
            if add_product(products, existing_keys, existing_urls, c, src, brand, title, url,
                           'trade_media', 'launch_announcement', now,
                           product_page=False, newness_type='new_product_or_line', confidence='medium'):
                promoted += 1
            if promoted >= 100: break
            continue

        if not (official_source or new_source):
            continue
        if not official_source and not likely_product_url(url):
            continue

        brand = mapped_brand or find_brand(pre_hay, brands)
        if not brand and c.get('source_id') in OFFICIAL_SOURCE_BRANDS:
            brand = brand_by_name.get(OFFICIAL_SOURCE_BRANDS[c.get('source_id')])

        page = ''
        product_page = False
        review_count = None
        try:
            page = fetch(url)
            fetched += 1
            product_page = looks_like_product_page(url, page)
            review_count = extract_review_count(page)
        except Exception:
            product_page = likely_product_url(url)

        page_title = extract_page_title(page)
        hay = ' '.join([pre_hay, page_title, re.sub(r'<[^>]+>', ' ', page[:150000])])
        if not brand:
            brand = find_brand(hay, brands)
        if not brand:
            continue
        if not PRODUCT_HINT.search(hay):
            continue

        effective_title = title
        if len(re.sub(r'\W+', '', title)) < 8 or title.lower().endswith('.html') or re.fullmatch(r'\d+', title.strip()):
            effective_title = page_title or title

        if ch in {'specialty_retail','mass_retail','drugstore','marketplace'}:
            if not product_page or not new_source:
                continue
            if review_count is not None and review_count > 100:
                c['review_status'] = 'rejected_old_reviews'
                rejected_old += 1
                continue
            confidence = 'medium' if review_count is not None and review_count <= 25 else 'low'
            newness_type = 'new_product_or_sku' if review_count is not None and review_count <= 25 else 'new_retailer_listing'
            if add_product(products, existing_keys, existing_urls, c, src, brand, effective_title, url,
                           'retailer', 'product_detail', now, product_page=True, review_count=review_count,
                           newness_type=newness_type, confidence=confidence):
                promoted += 1
        else:
            if not (strong_launch or product_page):
                continue
            if add_product(products, existing_keys, existing_urls, c, src, brand, effective_title, url,
                           'official', 'product_detail' if product_page else 'launch_announcement', now,
                           product_page=product_page, review_count=review_count,
                           newness_type='new_product_or_sku', confidence='high'):
                promoted += 1

        if promoted >= 100: break

    products.sort(key=lambda x: x.get('first_seen_at',''), reverse=True)
    stamp = now.replace(microsecond=0).isoformat().replace('+00:00','Z')
    save_json(PRODUCTS, {'generated_at': stamp, 'products': products[:2500]})
    save_json(DISCOVERY, {**discovery, 'generated_at': stamp})
    spectrum_count = sum(1 for p in products if p.get('focus_group') == 'spectrum_pet_food')
    print(f'Candidate promotion: checked={checked}; fetched={fetched}; promoted={promoted}; rejected_old_reviews={rejected_old}; products={len(products)}; spectrum_focus={spectrum_count}')


if __name__ == '__main__':
    main()
