(() => {
  const originalCard = card;
  card = function (p) {
    const node = originalCard(p);
    if (p && p.focus_group === 'spectrum_pet_food') {
      const chips = node.querySelector('.chips');
      if (chips && ![...chips.children].some(x => x.textContent === 'Spectrum 重点')) {
        const badge = document.createElement('span');
        badge.className = 'chip';
        badge.style.fontWeight = '800';
        badge.style.background = '#e8ff7b';
        badge.style.color = '#17201e';
        badge.textContent = 'Spectrum 重点';
        chips.prepend(badge);
      }
    }
    return node;
  };

  const originalCoverage = renderCoverage;
  renderCoverage = function () {
    originalCoverage();
    const count = (state.sources || []).filter(s => s.focus_group === 'spectrum_pet_food').length;
    if (!count) return;
    const panel = document.querySelector('.coverage-grid .panel');
    const chips = panel && panel.querySelector('.chips');
    if (chips && !document.getElementById('spectrumCoverageChip')) {
      const badge = document.createElement('span');
      badge.id = 'spectrumCoverageChip';
      badge.className = 'chip';
      badge.style.fontWeight = '800';
      badge.style.background = '#e8ff7b';
      badge.style.color = '#17201e';
      badge.textContent = `Spectrum 重点源 ${count}`;
      chips.prepend(badge);
    }
  };
})();
