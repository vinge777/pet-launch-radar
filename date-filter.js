(() => {
  state.startDate = state.startDate || '';
  state.endDate = state.endDate || '';

  const productDate = p => String(p.launch_date || p.first_seen_at || '').slice(0, 10);

  const ensureDateUI = () => {
    if ($('#dateFilters')) return;
    const filters = $('#filters');
    const clearBtn = $('#clearBtn');
    if (!filters || !clearBtn) return;

    const box = document.createElement('div');
    box.id = 'dateFilters';
    box.className = 'date-filters';
    box.innerHTML = `
      <label><span>开始日期</span><input id="startDateFilter" type="date" /></label>
      <span class="date-separator">至</span>
      <label><span>结束日期</span><input id="endDateFilter" type="date" /></label>
      <span class="date-tip">同一天：开始和结束选择相同日期</span>`;
    filters.insertBefore(box, clearBtn);

    if (!document.getElementById('dateFilterStyles')) {
      const style = document.createElement('style');
      style.id = 'dateFilterStyles';
      style.textContent = `
        .date-filters{grid-column:1/-1;display:none;align-items:flex-end;gap:9px;background:#fff;border:1px solid var(--line);border-radius:11px;padding:9px 11px}
        .date-filters label{display:flex;flex-direction:column;gap:5px;font-size:10px;color:#737d86;font-weight:700}
        .date-filters input{height:34px;border:1px solid var(--line);border-radius:8px;padding:0 9px;color:#374149;background:#fff}
        .date-separator{font-size:11px;color:#8b949d;padding-bottom:9px}
        .date-tip{font-size:10px;color:#929aa2;padding-bottom:9px;margin-left:3px}
        @media(max-width:760px){.date-filters{align-items:stretch;flex-direction:column}.date-separator,.date-tip{display:none}}
      `;
      document.head.appendChild(style);
    }
  };

  const originalFiltered = filtered;
  filtered = function () {
    let arr = originalFiltered();
    if (state.view !== 'week' && state.view !== 'all') return arr;
    if (state.startDate) arr = arr.filter(p => productDate(p) >= state.startDate);
    if (state.endDate) arr = arr.filter(p => productDate(p) <= state.endDate);
    return arr;
  };

  const originalBind = bind;
  bind = function () {
    originalBind();
    ensureDateUI();

    const start = $('#startDateFilter');
    const end = $('#endDateFilter');
    start.value = state.startDate;
    end.value = state.endDate;

    start.onchange = e => {
      state.startDate = e.target.value;
      if (state.startDate && state.endDate && state.startDate > state.endDate) {
        state.endDate = state.startDate;
        end.value = state.endDate;
      }
      renderContent();
    };
    end.onchange = e => {
      state.endDate = e.target.value;
      if (state.startDate && state.endDate && state.endDate < state.startDate) {
        state.startDate = state.endDate;
        start.value = state.startDate;
      }
      renderContent();
    };

    const clear = $('#clearBtn');
    const originalClear = clear.onclick;
    clear.onclick = e => {
      if (originalClear) originalClear(e);
      state.startDate = '';
      state.endDate = '';
      start.value = '';
      end.value = '';
      renderContent();
    };
  };

  const originalRender = render;
  render = function () {
    originalRender();
    ensureDateUI();
    const dateFilters = $('#dateFilters');
    if (dateFilters) dateFilters.style.display = (state.view === 'week' || state.view === 'all') ? 'flex' : 'none';
  };
})();

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
