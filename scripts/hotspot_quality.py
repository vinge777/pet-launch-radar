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

FOOD_TERMS = re.compile(
    r'pet\s*food|dog\s*food|cat\s*food|puppy\s*food|kitten\s*food|kibble|dry\s*food|wet\s*food|canned|can\s*food|pouch|tray|meal|diet|formula|nutrition|nutritional|ingredient|protein|meat|poultry|fish|tuna|salmon|chicken|beef|duck|treat|treats|snack|chew|chews|jerky|biscuit|dental\s*chew|supplement|nutraceutical|vitamin|mineral|probiotic|prebiotic|omega|topper|broth|gravy|mousse|lickable|freeze[- ]?dried|air[- ]?dried|raw\s*(?:food|diet)|fresh\s*(?:pet\s*)?food|palatab|flavou?r|recipe|functional\s*(?:food|treat|nutrition)|complete\s*(?:and\s*balanced\s*)?food|pet\s*nutrition|animal\s*nutrition|ração|alimento\s+para\s+(?:cães|gatos)|futter|hundefutter|katzenfutter|nahrung|ペットフード|ドッグフード|キャットフード|おやつ|사료|간식',
    re.I,
)
SUPPLIES_TERMS = re.compile(
    r'toy|toys|bed|bedding|leash|lead\b|collar|harness|apparel|fashion|costume|clothing|litter|cat\s*litter|groom|shampoo|brush|comb|bowl|feeder|fountain|crate|carrier|kennel|scratch(?:er|ing)|cat\s*tree|furniture|accessor|accessories|tracker|camera|smart\s*(?:collar|feeder|device)|training\s*pad|pee\s*pad|poop\s*bag|waste\s*bag|cleaning|odor|odour|stroller|travel\s*gear|pet\s*tech|aquarium|terrarium|服装|玩具|猫砂|牵引|项圈|宠物用品|おもちゃ|猫砂|용품',
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


def classify_segment(item):
    hay = ' '.join([
        item.get('title',''), item.get('title_zh',''), item.get('summary',''), item.get('summary_zh',''),
        item.get('topic',''), item.get('source_name',''), item.get('publisher',''), item.get('url','')
    ])
    food_hits = len(FOOD_TERMS.findall(hay))
    supply_hits = len(SUPPLIES_TERMS.findall(hay))
    if food_hits:
        segment = 'food'
    elif supply_hits:
        segment = 'supplies'
    else:
        segment = 'industry'

    subcategory = ''
    if segment == 'food':
        if re.search(r'treat|snack|chew|jerky|biscuit|lickable|おやつ|간식|零食|洁齿', hay, re.I):
            subcategory = '零食 / 洁齿'
        elif re.search(r'supplement|nutraceutical|vitamin|mineral|probiotic|prebiotic|omega|joint|skin|coat|gut|digest|营养补充|保健', hay, re.I):
            subcategory = '营养补充'
        elif re.search(r'ingredient|protein|nutrition|research|study|science|palatab|raw material|原料|营养|科研', hay, re.I):
            subcategory = '原料 / 营养科研'
        elif re.search(r'packag|retort|extrusion|freeze[- ]?dried|air[- ]?dried|baked|process|manufactur|factory|facility|包装|加工|工厂', hay, re.I):
            subcategory = '加工 / 包装'
        elif re.search(r'wet\s*food|canned|pouch|tray|broth|gravy|mousse|湿粮|罐头|汤包', hay, re.I):
            subcategory = '湿粮'
        elif re.search(r'dry\s*food|kibble|baked|extrud|干粮|烘焙粮|膨化', hay, re.I):
            subcategory = '干粮'
        elif re.search(r'market|sales|consumer|retail|growth|demand|trend|市场|消费|渠道', hay, re.I):
            subcategory = '食品市场 / 渠道'
        else:
            subcategory = '宠物食品综合'
    elif segment == 'supplies':
        if re.search(r'toy|scratch|玩具', hay, re.I):
            subcategory = '玩具 / 丰容'
        elif re.search(r'apparel|fashion|costume|clothing|服装', hay, re.I):
            subcategory = '服饰'
        elif re.search(r'litter|clean|odor|odour|pad|bag|猫砂|清洁', hay, re.I):
            subcategory = '清洁 / 猫砂'
        elif re.search(r'tracker|camera|smart|tech|智能|科技', hay, re.I):
            subcategory = '智能用品'
        else:
            subcategory = '宠物用品综合'
    else:
        subcategory = '行业综合'

    item['segment'] = segment
    item['segment_zh'] = {'food':'宠物食品','supplies':'宠物用品','industry':'行业综合'}[segment]
    item['subcategory_zh'] = subcategory
    item['food_priority'] = 3 if segment == 'food' else (2 if segment == 'industry' else 1)
    return item


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
        classify_segment(x)

    def sort_key(x):
        published = x.get('published_at') or ''
        return (x.get('food_priority', 0), published)

    # 食品情报优先进入数据文件前部；前端仍可按发布日期筛选和查看用品/行业综合。
    items.sort(key=sort_key, reverse=True)
    data['items'] = items
    data['segment_counts'] = {
        'food': sum(1 for x in items if x.get('segment') == 'food'),
        'supplies': sum(1 for x in items if x.get('segment') == 'supplies'),
        'industry': sum(1 for x in items if x.get('segment') == 'industry'),
    }
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(
        'Hotspot quality pass: '
        f'kept={len(items)}, food={data["segment_counts"]["food"]}, '
        f'supplies={data["segment_counts"]["supplies"]}, industry={data["segment_counts"]["industry"]}, '
        f'summaries={sum(1 for x in items if x.get("summary_zh"))}'
    )


if __name__ == '__main__':
    main()
