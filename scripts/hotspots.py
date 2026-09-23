#!/usr/bin/env python3
import argparse
import email.utils
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
CONFIG = ROOT / "config" / "hotspot-sources.json"
OUT = ROOT / "data" / "hotspots.json"
STATE = ROOT / "data" / "hotspot-state.json"
UA = "Mozilla/5.0 (compatible; PetLaunchRadar/1.0; +https://github.com/vinge777/pet-launch-radar)"
VALID_CHANNELS = {"brand_official","specialty_retail","mass_retail","drugstore","marketplace","trade_media"}
PET_TERMS = re.compile(r"pet|pets|dog|dogs|cat|cats|puppy|kitten|animal|canine|feline|pet food|petfood|pet care|veterinary|nutrition|treat|chew|tier|hund|katze|futter|haustier|chien|chat|animalerie|mascota|perro|gato|ração|cachorro|ペット|犬|猫|반려동물|강아지|고양이", re.I)
NEWS_TERMS = re.compile(r"launch|unveil|introduc|new |innovation|trend|market|growth|research|study|science|nutrition|ingredient|packag|sustainab|retail|store|channel|consumer|shopper|acqui|partner|expand|investment|report|survey|technology|AI|health|wellness|press|news|neu|neuheit|innovation|tendance|nouveau|lancement|新商品|新製品|発売|トレンド|혁신|신제품|tendência|lançamento|innovación|tendencia", re.I)
SKIP_TERMS = re.compile(r"privacy|cookie|terms of use|contact us|careers|sign in|login|accessibility|sitemap|newsletter|facebook|instagram|linkedin|youtube|x.com|twitter", re.I)


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def load_json(path, default):
    if not path.exists(): return default
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return default

def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")

class AnchorParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self._href=None; self._parts=[]
    def handle_starttag(self, tag, attrs):
        if tag.lower()=="a": self._href=dict(attrs).get("href"); self._parts=[]
    def handle_data(self, data):
        if self._href is not None: self._parts.append(data)
    def handle_endtag(self, tag):
        if tag.lower()=="a" and self._href is not None:
            text=re.sub(r"\s+"," "," ".join(self._parts)).strip()
            self.links.append((self._href,text)); self._href=None; self._parts=[]

def fetch(url):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept-Language":"en-US,en;q=0.8"})
    with urllib.request.urlopen(req,timeout=25) as resp:
        raw=resp.read(); charset=resp.headers.get_content_charset() or "utf-8"
        return raw.decode(charset,errors="replace")

def clean_url(base, href):
    if not href or href.startswith(("javascript:","mailto:","tel:","#")): return None
    u=urllib.parse.urljoin(base,href); p=urllib.parse.urlparse(u)
    if p.scheme not in ("http","https"): return None
    if re.search(r"\.(jpg|jpeg|png|gif|webp|svg|pdf|css|js|zip)(\?|$)",p.path,re.I): return None
    return urllib.parse.urlunparse((p.scheme,p.netloc,p.path,p.params,p.query,""))

def same_host(a,b):
    ah=(urllib.parse.urlparse(a).hostname or "").lower().removeprefix("www.")
    bh=(urllib.parse.urlparse(b).hostname or "").lower().removeprefix("www.")
    return ah==bh or ah.endswith("."+bh) or bh.endswith("."+ah)

def topic_for(title):
    t=title.lower()
    if re.search(r"trend|market|growth|consumer|shopper|survey|report|tendance|tendência|tendencia|トレンド",t): return "市场趋势"
    if re.search(r"nutrition|ingredient|science|research|study|health|wellness|veterinary",t): return "营养 / 科研"
    if re.search(r"packag|sustainab|recycl|material",t): return "包装 / 可持续"
    if re.search(r"retail|store|channel|ecommerce|e-commerce|marketplace",t): return "渠道 / 零售"
    if re.search(r"launch|unveil|introduc|new |neuheit|nouveau|新商品|新製品|発売|신제품|lançamento|lancement",t): return "新品 / 创新"
    if re.search(r"acqui|partner|expand|investment|financial|results|appoint|merger",t): return "公司动态"
    return "行业新闻"

def fingerprint(title):
    s=re.sub(r"[^a-z0-9\u4e00-\u9fff]+","",title.lower())
    return s[:180]

def normalize_date(raw):
    if not raw: return None
    raw=str(raw).strip()
    try:
        if re.match(r"^\d{4}-\d{2}-\d{2}$",raw):
            return raw+"T00:00:00Z"
        dt=datetime.fromisoformat(raw.replace("Z","+00:00"))
        if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
    except Exception:
        pass
    for fmt in ("%Y/%m/%d","%Y.%m.%d","%Y-%m-%d","%B %d, %Y","%b %d, %Y"):
        try:
            return datetime.strptime(raw,fmt).replace(tzinfo=timezone.utc).isoformat().replace("+00:00","Z")
        except Exception:
            pass
    return None

def infer_date_from_text_url(title,url):
    text=f"{title} {urllib.parse.unquote(url)}"
    patterns=[
        r"(?P<y>20\d{2})[-/年](?P<m>0?[1-9]|1[0-2])[-/月](?P<d>0?[1-9]|[12]\d|3[01])(?:日)?",
        r"/(?P<y>20\d{2})/(?P<m>0[1-9]|1[0-2])(?P<d>0[1-9]|[12]\d|3[01])(?:[-_/]|$)",
    ]
    for pat in patterns:
        m=re.search(pat,text)
        if m:
            try:
                return datetime(int(m.group('y')),int(m.group('m')),int(m.group('d')),tzinfo=timezone.utc).isoformat().replace("+00:00","Z")
            except Exception:
                pass
    return None

def extract_date_from_article(url):
    try: html=fetch(url)
    except Exception: return None
    candidates=[]
    patterns=[
        r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']article:published_time["\']',
        r'<meta[^>]+name=["\'](?:date|publish-date|publication_date|pubdate)["\'][^>]+content=["\']([^"\']+)',
        r'"datePublished"\s*:\s*"([^"]+)"',
        r'<time[^>]+datetime=["\']([^"\']+)',
    ]
    for pat in patterns:
        candidates.extend(re.findall(pat,html,re.I))
    for raw in candidates:
        d=normalize_date(raw)
        if d: return d
    return None

def translate_to_zh(text):
    text=(text or '').strip()
    if not text: return ''
    # Keep already-Chinese titles as-is. Japanese/Korean titles still go through translation.
    if re.search(r'[\u4e00-\u9fff]',text) and not re.search(r'[\u3040-\u30ff\uac00-\ud7af]',text) and not re.search(r'[A-Za-z]{4,}',text):
        return text
    try:
        q=urllib.parse.urlencode({"client":"gtx","sl":"auto","tl":"zh-CN","dt":"t","q":text})
        url="https://translate.googleapis.com/translate_a/single?"+q
        data=json.loads(fetch(url))
        translated=''.join(part[0] for part in (data[0] or []) if part and part[0])
        return translated.strip() or text
    except Exception:
        return text

def scan_html(source):
    html=fetch(source["url"]); parser=AnchorParser(); parser.feed(html); out=[]
    pet_specific=bool(source.get("pet_specific"))
    for href,text in parser.links:
        url=clean_url(source["url"],href)
        if not url or (source.get("same_domain_only",True) and not same_host(url,source["url"])): continue
        text=re.sub(r"\s+"," ",text).strip()
        if len(text)<12 or len(text)>260 or SKIP_TERMS.search(text): continue
        combined=text+" "+urllib.parse.unquote(urllib.parse.urlparse(url).path)
        if not pet_specific and not PET_TERMS.search(combined): continue
        if not NEWS_TERMS.search(combined) and not source.get("include_all_pet_news",False): continue
        out.append({"title":text[:240],"url":url,"published_at":infer_date_from_text_url(text,url),"publisher":source["name"]})
    dedup={}
    for x in out: dedup.setdefault(x["url"],x)
    return list(dedup.values())[:200]

def scan_google_news(source):
    params=urllib.parse.urlencode({"q":source["query"],"hl":"en","gl":"US","ceid":"US:en"})
    root=ET.fromstring(fetch("https://news.google.com/rss/search?"+params)); out=[]
    for item in root.findall(".//item"):
        title=(item.findtext("title") or "").strip(); link=(item.findtext("link") or "").strip(); pub=(item.findtext("pubDate") or "").strip()
        source_el=item.find("source"); publisher=(source_el.text or "").strip() if source_el is not None else source["name"]
        if not title or not link: continue
        published_at=None
        if pub:
            try: published_at=email.utils.parsedate_to_datetime(pub).astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
            except Exception: pass
        out.append({"title":title[:240],"url":link,"published_at":published_at,"publisher":publisher})
    return out[:100]

def parse_scope():
    ap=argparse.ArgumentParser(); ap.add_argument("--channels",default="all"); args=ap.parse_args(); raw=args.channels.strip()
    if raw=="all": return None,"all"
    selected={x.strip() for x in raw.split(",") if x.strip()}; invalid=selected-VALID_CHANNELS
    if invalid: raise SystemExit("Unknown channel(s): "+", ".join(sorted(invalid)))
    return selected,",".join(sorted(selected))

def main():
    selected,scope=parse_scope(); cfg=load_json(CONFIG,{"sources":[]}); old=load_json(OUT,{"items":[]}); state=load_json(STATE,{"sources":{}})
    checked=now_iso(); old_by_url={x.get('url'):x for x in old.get('items',[]) if x.get('url')}; items=[]; source_state=state.setdefault("sources",{}); statuses=[]
    for src in cfg.get("sources",[]):
        if selected is not None and src["channel_type"] not in selected: continue
        try:
            found=scan_google_news(src) if src.get("mode")=="google_news" else scan_html(src)
            for x in found:
                previous=old_by_url.get(x['url'],{})
                published_at=x.get('published_at') or previous.get('published_at')
                title_zh=previous.get('title_zh') or translate_to_zh(x['title'])
                items.append({
                    "id":previous.get('id') or f"{src['id']}-{abs(hash(x['url']))}",
                    "title":x["title"],"title_zh":title_zh,"summary":previous.get('summary',''),"summary_zh":previous.get('summary_zh',''),"url":x["url"],
                    "publisher":x.get("publisher") or src["name"],"source_name":src["name"],"source_id":src["id"],
                    "channel_type":src["channel_type"],"region":src.get("region","Global"),"country":src.get("country","Global"),
                    "topic":topic_for(x["title"]),"published_at":published_at,"discovered_at":previous.get('discovered_at') or checked
                })
            source_state[src["id"]]={"status":"ok","checked_at":checked,"items_found":len(found)}
            statuses.append({"id":src["id"],"name":src["name"],"channel_type":src["channel_type"],"status":"ok","items_found":len(found)})
        except Exception as exc:
            source_state[src["id"]]={"status":"error","checked_at":checked,"error":str(exc)[:240]}
            statuses.append({"id":src["id"],"name":src["name"],"channel_type":src["channel_type"],"status":"error","items_found":0})
        time.sleep(.25)

    # Preserve still-recent items from sources not selected in a partial refresh.
    if selected is not None:
        items.extend(x for x in old.get('items',[]) if x.get('channel_type') not in selected)

    # Enrich original publication dates. Never substitute discovered_at as publication date.
    for i,x in enumerate(items):
        if not x.get('published_at'):
            x['published_at']=infer_date_from_text_url(x.get('title',''),x.get('url',''))
        if not x.get('published_at') and x.get('url') and not x.get('url','').startswith('https://news.google.com/'):
            x['published_at']=extract_date_from_article(x['url'])
            if i % 8 == 0: time.sleep(.08)
        if not x.get('title_zh'):
            x['title_zh']=translate_to_zh(x.get('title',''))

    cutoff=datetime.now(timezone.utc)-timedelta(days=120); by_url={}; by_title={}
    def pub_dt(x):
        raw=x.get("published_at")
        if not raw: return datetime(1970,1,1,tzinfo=timezone.utc)
        try:return datetime.fromisoformat(raw.replace("Z","+00:00"))
        except Exception:return datetime(1970,1,1,tzinfo=timezone.utc)
    for x in sorted(items,key=pub_dt):
        # If publication date is known, keep only recent 120-day news. Unknown dates stay visible but sort last.
        if x.get('published_at') and pub_dt(x)<cutoff: continue
        fp=fingerprint(x.get("title",""))
        if x.get("url") in by_url or (fp and fp in by_title): continue
        by_url[x.get("url")]=x
        if fp: by_title[fp]=x
    final=sorted(by_url.values(),key=pub_dt,reverse=True)[:1500]
    save_json(OUT,{"generated_at":checked,"last_scan_scope":scope,"items":final,"source_status":statuses})
    save_json(STATE,{"generated_at":checked,"last_scan_scope":scope,"sources":source_state})
    print(f"Hotspot scan scope: {scope}; sources: {len(statuses)}; items: {len(final)}; translated: {sum(1 for x in final if x.get('title_zh'))}; dated: {sum(1 for x in final if x.get('published_at'))}")

if __name__=="__main__": main()
