#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_SOURCES = ROOT / 'config' / 'sources.json'
EXTRA_SOURCES = ROOT / 'config' / 'sources-expanded.json'
BASE_BRANDS = ROOT / 'data' / 'brands.json'
FOCUS_BRANDS = ROOT / 'config' / 'focus-brands.json'


def load(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
    except Exception:
        return default


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def merge_unique(base, extra, key):
    merged = {x.get(key): x for x in base if x.get(key)}
    for item in extra:
        if not item.get(key):
            continue
        old = merged.get(item[key], {})
        merged[item[key]] = {**old, **item}
    return list(merged.values())


def main():
    base_sources = load(BASE_SOURCES, {'sources': []})
    extra_sources = load(EXTRA_SOURCES, {'sources': []})
    sources = merge_unique(base_sources.get('sources', []), extra_sources.get('sources', []), 'id')
    base_sources['sources'] = sources
    base_sources['runtime_expanded'] = True
    base_sources['runtime_source_count'] = len(sources)
    save(BASE_SOURCES, base_sources)

    base_brands = load(BASE_BRANDS, {'brands': []})
    focus_brands = load(FOCUS_BRANDS, {'brands': []})
    brands = merge_unique(base_brands.get('brands', []), focus_brands.get('brands', []), 'name')
    base_brands['brands'] = brands
    base_brands['runtime_focus_merged'] = True
    save(BASE_BRANDS, base_brands)

    spectrum_sources = [s for s in sources if s.get('focus_group') == 'spectrum_pet_food']
    print(f'Monitoring config merged: sources={len(sources)}; Spectrum focus sources={len(spectrum_sources)}; brands={len(brands)}')


if __name__ == '__main__':
    main()
