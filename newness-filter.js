(() => {
  const typeCN = {
    new_product: '全新品',
    new_product_line: '新产品线',
    new_flavor: '新口味',
    new_formula: '新配方',
    new_sku: '新SKU/规格',
    new_packaging: '新包装',
    new_market: '新市场上市',
    new_retailer_listing: '渠道新上架',
    existing_product: '既有产品'
  };
  const visibleStatuses = new Set(['verified', 'variant']);
  const isQualifiedNew = p => visibleStatuses.has(p.newness_status || 'verified');

  const originalBaseProducts = baseProducts;
  baseProducts = function () {
    return originalBaseProducts().filter(isQualifiedNew);
  };

  renderCounts = function () {
    const all = state.products.filter(p => p.brand_origin_country !== 'China' && p.origin_verified !== false && isQualifiedNew(p));
    const map = {'All': all.length, 'North America': 0, 'Europe': 0, 'Asia': 0, 'South America': 0};
    all.forEach(p => map[p.market_region] = (map[p.market_region] || 0) + 1);
    Object.entries(map).forEach(([k, v]) => {
      const el = document.getElementById('count-' + k.replaceAll(' ', '-'));
      if (el) el.textContent = v;
    });
  };

  renderStats = function () {
    const arr = baseProducts();
    const brands = new Set(arr.map(x => x.brand));
    const countries = new Set(arr.map(x => x.country));
    const today = state.products.filter(p =>
      isQualifiedNew(p) &&
      new Date(p.first_seen_at) >= daysAgo(0) &&
      p.origin_verified !== false &&
      p.brand_origin_country !== 'China'
    ).length;
    $('#stats').innerHTML = [
      ['当前结果', arr.length, '仅含已核验新品/明确新变体'],
      ['涉及品牌', brands.size, '已核验非中国品牌'],
      ['市场国家', countries.size, '按上市市场计'],
      ['今日新发现', today, '不把旧品新上架计作全新品']
    ].map(x => `<div class="stat-card"><div class="stat-label">${x[0]}</div><div class="stat-value">${x[1]}</div><div class="stat-foot">${x[2]}</div></div>`).join('');
  };

  const originalCard = card;
  card = function (p) {
    const node = originalCard(p);
    const chips = node.querySelector('.chips');
    const label = typeCN[p.newness_type] || '新品';
    if (chips) {
      const badge = document.createElement('span');
      badge.className = 'chip';
      badge.style.fontWeight = '800';
      badge.textContent = label;
      chips.prepend(badge);
    }
    const dateEl = node.querySelector('.launch-date');
    if (dateEl) {
      if (p.launch_date_verified && p.launch_date) dateEl.textContent = `上市 ${fmt(p.launch_date)}`;
      else dateEl.textContent = `发现 ${fmt(p.first_seen_at)}`;
    }
    return node;
  };
})();
