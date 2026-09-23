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
