(() => {
  state.startDate = state.startDate || '';
  state.endDate = state.endDate || '';

  const MARKET_TZ = 'Asia/Shanghai';
  const marketDateKey = value => {
    if (!value) return '';
    const d = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(d.getTime())) return '';
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: MARKET_TZ,
      year: 'numeric', month: '2-digit', day: '2-digit'
    }).formatToParts(d);
    const map = Object.fromEntries(parts.map(x => [x.type, x.value]));
    return `${map.year}-${map.month}-${map.day}`;
  };

  const todayMarket = () => marketDateKey(new Date());
  const daysAgoMarket = n => marketDateKey(new Date(Date.now() - n * 86400000));
  const productDate = p => p.launch_date ? String(p.launch_date).slice(0, 10) : marketDateKey(p.first_seen_at);

  // Replace the browser-local date filter with one stable business timezone.
  // This prevents a product detected in the China morning from disappearing from
  // “今日新品” when the viewer's browser is in the US timezone.
  baseProducts = function () {
    let arr = state.products.filter(isVisibleProduct);
    if (state.view === 'today') arr = arr.filter(p => marketDateKey(p.first_seen_at) === todayMarket());
    if (state.view === 'week') arr = arr.filter(p => marketDateKey(p.first_seen_at) >= daysAgoMarket(6));
    if (state.region !== 'All') arr = arr.filter(p => p.market_region === state.region);
    return arr;
  };

  // Keep the KPI cards on the same date definition as the product list.
  renderStats = function () {
    const arr = baseProducts();
    const brands = new Set(arr.map(x => x.brand));
    const countries = new Set(arr.map(x => x.country));
    const today = state.products.filter(p => isVisibleProduct(p) && marketDateKey(p.first_seen_at) === todayMarket()).length;
    $('#stats').innerHTML = [
      ['当前结果', arr.length, '按北京时间与当前地区范围'],
      ['涉及品牌', brands.size, '已核验非中国品牌'],
      ['市场国家', countries.size, '按上市市场计'],
      ['今日新发现', today, '本轮通过质量闸门的正式新品']
    ].map(x => `<div class="stat-card"><div class="stat-label">${x[0]}</div><div class="stat-value">${x[1]}</div><div class="stat-foot">${x[2]}</div></div>`).join('');
  };

  const ensureStatusBanner = () => {
    if ($('#feedStatusBanner')) return;
    const tabs = $('#regionTabs');
    if (!tabs) return;
    const el = document.createElement('div');
    el.id = 'feedStatusBanner';
    el.className = 'feed-status-banner';
    el.innerHTML = `<strong>新版数据口径</strong><span>新品日期统一按北京时间（UTC+8）</span><span>仅展示通过质量闸门的正式新品</span><span>“渠道新上架”与“新品发布”分开标注</span>`;
    tabs.insertAdjacentElement('afterend', el);
  };

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
      <span class="date-tip">日期按北京时间；同一天请把开始、结束选为同一日期</span>`;
    filters.insertBefore(box, clearBtn);

    if (!document.getElementById('dateFilterStyles')) {
      const style = document.createElement('style');
      style.id = 'dateFilterStyles';
      style.textContent = `
        .feed-status-banner{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:12px 0 4px;padding:10px 12px;border:1px solid #b9ddd3;background:#eef9f5;border-radius:12px;font-size:11px;color:#44635b}
        .feed-status-banner strong{color:#176b5b;font-size:11px}
        .feed-status-banner span{padding-left:10px;border-left:1px solid #cfe7e0}
        .date-filters{grid-column:1/-1;display:none;align-items:flex-end;gap:9px;background:#fff;border:1px solid var(--line);border-radius:11px;padding:9px 11px}
        .date-filters label{display:flex;flex-direction:column;gap:5px;font-size:10px;color:#737d86;font-weight:700}
        .date-filters input{height:34px;border:1px solid var(--line);border-radius:8px;padding:0 9px;color:#374149;background:#fff}
        .date-separator{font-size:11px;color:#8b949d;padding-bottom:9px}
        .date-tip{font-size:10px;color:#929aa2;padding-bottom:9px;margin-left:3px}
        .product-card .chips .chip:first-child{background:#e2f3ed;color:#176b5b;font-weight:800;border:1px solid #c9e6dd}
        @media(max-width:760px){.feed-status-banner{align-items:flex-start;flex-direction:column}.feed-status-banner span{padding-left:0;border-left:0}.date-filters{align-items:stretch;flex-direction:column}.date-separator,.date-tip{display:none}}
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
    ensureStatusBanner();
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
    ensureStatusBanner();
    ensureDateUI();
    const dateFilters = $('#dateFilters');
    if (dateFilters) dateFilters.style.display = (state.view === 'week' || state.view === 'all') ? 'flex' : 'none';
  };
})();
