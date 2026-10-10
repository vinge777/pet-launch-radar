#!/usr/bin/env python3
import concurrent.futures
from datetime import datetime, timezone, timedelta

import scan as base


def fetch_source(source):
    try:
        items = base.scan_google_news(source) if source.get('mode') == 'google_news' else base.scan_html(source)
        return source, items, None
    except Exception as exc:
        return source, [], str(exc)[:300]


def main():
    selected_channels, scope_label = base.parse_scope()
    cfg = base.load_json(base.CONFIG, {'sources': []})
    seen = base.load_json(base.SEEN, {'sources': {}})
    discovery = base.load_json(base.DISCOVERY, {'generated_at': None, 'candidates': []})
    previous_status = base.load_json(base.STATUS, {'sources': []})
    previous_by_id = {x.get('id'): x for x in previous_status.get('sources', []) if x.get('id')}
    seen_sources = seen.setdefault('sources', {})
    candidates = discovery.setdefault('candidates', [])
    status_rows = []
    checked_at = base.now_iso()

    selected = []
    for source in cfg.get('sources', []):
        sid = source['id']
        channel = source['channel_type']
        if selected_channels is not None and channel not in selected_channels:
            prior = previous_by_id.get(sid)
            if prior:
                preserved = dict(prior)
                preserved['selected_in_last_run'] = False
                status_rows.append(preserved)
            else:
                status_rows.append({
                    'id': sid, 'name': source['name'], 'region': source['region'],
                    'country': source.get('country'), 'channel_type': channel, 'type': channel,
                    'status': 'not_scanned', 'items_found': 0, 'new_candidates': 0,
                    'checked_at': None,
                    'source_url': source.get('url') or ('Google News: ' + source.get('query', '')),
                    'selected_in_last_run': False
                })
            continue
        selected.append(source)

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(fetch_source, s) for s in selected]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    # Process results in configured priority order so status and new candidates are deterministic.
    results.sort(key=lambda row: (int(row[0].get('priority', 0) or 0), row[0].get('id', '')), reverse=True)

    for source, items, error in results:
        sid = source['id']
        channel = source['channel_type']
        if error:
            status_rows.append({
                'id': sid, 'name': source['name'], 'region': source['region'],
                'country': source.get('country'), 'channel_type': channel, 'type': channel,
                'status': 'error', 'items_found': 0, 'new_candidates': 0,
                'checked_at': checked_at,
                'source_url': source.get('url') or ('Google News: ' + source.get('query', '')),
                'error': error, 'selected_in_last_run': True,
                'priority': source.get('priority', 0), 'focus_group': source.get('focus_group')
            })
            continue

        current_urls = [x['url'] for x in items]
        previous = set(seen_sources.get(sid, []))
        first_run = sid not in seen_sources
        if first_run and source.get('backfill_on_first_run'):
            limit = int(source.get('backfill_limit', 30))
            new_items = items[:limit]
        else:
            new_items = [] if first_run else [x for x in items if x['url'] not in previous]

        for x in new_items:
            candidates.append({
                'id': base.stable_id(sid, x['url']),
                'title': x['title'], 'url': x['url'],
                'source_id': sid, 'source_name': source['name'],
                'region': source['region'], 'country': source.get('country'),
                'channel_type': channel, 'published_at': x.get('published_at'),
                'discovered_at': checked_at, 'review_status': 'pending',
                'priority': source.get('priority', 0),
                'focus_group': source.get('focus_group'),
                'note': 'Auto-discovered candidate. Verify brand origin, launch recency and product-detail URL before moving to products.json.'
            })

        merged = list(dict.fromkeys(list(previous) + current_urls))
        seen_sources[sid] = merged[-6000:]
        status_rows.append({
            'id': sid, 'name': source['name'], 'region': source['region'],
            'country': source.get('country'), 'channel_type': channel, 'type': channel,
            'status': 'ok', 'items_found': len(items), 'new_candidates': len(new_items),
            'checked_at': checked_at,
            'source_url': source.get('url') or ('Google News: ' + source.get('query', '')),
            'baseline_created': first_run, 'selected_in_last_run': True,
            'priority': source.get('priority', 0), 'focus_group': source.get('focus_group')
        })

    cutoff = datetime.now(timezone.utc) - timedelta(days=180)
    by_url = {}
    for c in candidates:
        try:
            dt = datetime.fromisoformat(c.get('discovered_at', '').replace('Z', '+00:00'))
        except Exception:
            dt = datetime.now(timezone.utc)
        if dt < cutoff:
            continue
        by_url[c['url']] = c
    candidates = sorted(
        by_url.values(),
        key=lambda x: (int(x.get('priority', 0) or 0), x.get('discovered_at', '')),
        reverse=True
    )[:3500]

    base.save_json(base.SEEN, {'generated_at': checked_at, 'last_scan_scope': scope_label, 'sources': seen_sources})
    base.save_json(base.DISCOVERY, {'generated_at': checked_at, 'last_scan_scope': scope_label, 'candidates': candidates})
    base.save_json(base.STATUS, {'generated_at': checked_at, 'last_scan_scope': scope_label, 'sources': status_rows})
    focus_sources = sum(1 for s in selected if s.get('focus_group') == 'spectrum_pet_food')
    ok_sources = sum(1 for s in status_rows if s.get('selected_in_last_run') and s.get('status') == 'ok')
    print(f'Parallel scan scope: {scope_label}; sources={len(selected)}; ok={ok_sources}; Spectrum focus sources={focus_sources}; candidates={len(candidates)}')


if __name__ == '__main__':
    main()
