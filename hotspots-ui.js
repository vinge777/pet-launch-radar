(() => {
  const channelCN={brand_official:'品牌官网',specialty_retail:'宠物专业渠道',mass_retail:'商超 / 综合零售',drugstore:'药妆 / 药房',marketplace:'综合电商',trade_media:'行业媒体 / 全网发现'};
  const regionCN={'North America':'美国','Europe':'欧洲','Asia':'亚洲','South America':'南美','Global':'全球'};
  let data={items:[],source_status:[],generated_at:null};
  let active=false;
  const filters={search:'',channel:'all',region:'all',start:'',end:''};
  const $=s=>document.querySelector(s);

  function ensureFilters(){
    if($('#hotspotFilters')) return;
    const box=document.createElement('section');
    box.id='hotspotFilters';box.className='hotspot-filters';
    box.innerHTML=`
      <div class="hotspot-search"><span>⌕</span><input id="hotspotSearch" placeholder="搜索趋势、新闻、品牌、渠道、关键词…"></div>
      <select id="hotspotChannel"><option value="all">全部来源类型</option>${Object.entries(channelCN).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select>
      <select id="hotspotRegion"><option value="all">全部地区</option><option value="North America">美国</option><option value="Europe">欧洲</option><option value="Asia">亚洲</option><option value="South America">南美</option><option value="Global">全球</option></select>
      <label class="hotspot-date-label">开始日期<input id="hotspotStart" type="date"></label>
      <label class="hotspot-date-label">结束日期<input id="hotspotEnd" type="date"></label>
      <button id="hotspotClear" type="button">清空</button>`;
    $('#stats').insertAdjacentElement('afterend',box);
    $('#hotspotSearch').oninput=e=>{filters.search=e.target.value.trim().toLowerCase();renderHotspots()};
    $('#hotspotChannel').onchange=e=>{filters.channel=e.target.value;renderHotspots()};
    $('#hotspotRegion').onchange=e=>{filters.region=e.target.value;renderHotspots()};
    $('#hotspotStart').onchange=e=>{filters.start=e.target.value;if(filters.end&&filters.start>filters.end){filters.end=filters.start;$('#hotspotEnd').value=filters.end}renderHotspots()};
    $('#hotspotEnd').onchange=e=>{filters.end=e.target.value;if(filters.start&&filters.end<filters.start){filters.start=filters.end;$('#hotspotStart').value=filters.start}renderHotspots()};
    $('#hotspotClear').onclick=()=>{filters.search='';filters.channel='all';filters.region='all';filters.start='';filters.end='';$('#hotspotSearch').value='';$('#hotspotChannel').value='all';$('#hotspotRegion').value='all';$('#hotspotStart').value='';$('#hotspotEnd').value='';renderHotspots()};
  }

  const itemDate=x=>String(x.published_at||'').slice(0,10);
  const publishedTime=x=>x.published_at?new Date(x.published_at).getTime():0;
  function filtered(){
    return data.items.filter(x=>{
      if(filters.channel!=='all'&&x.channel_type!==filters.channel)return false;
      if(filters.region!=='all'&&x.region!==filters.region)return false;
      const d=itemDate(x);
      if((filters.start||filters.end)&&!d)return false;
      if(filters.start&&d<filters.start)return false;if(filters.end&&d>filters.end)return false;
      if(filters.search){const hay=JSON.stringify([x.title_zh,x.title,x.summary_zh,x.summary,x.publisher,x.source_name,x.topic,x.country,channelCN[x.channel_type]]).toLowerCase();if(!hay.includes(filters.search))return false}
      return true;
    }).sort((a,b)=>publishedTime(b)-publishedTime(a));
  }

  function renderStatsHot(arr){
    const sources=new Set(arr.map(x=>x.publisher||x.source_name));const channels=new Set(arr.map(x=>x.channel_type));
    const today=new Date().toISOString().slice(0,10);const todayN=arr.filter(x=>itemDate(x)===today).length;
    $('#stats').innerHTML=[['热点结果',arr.length,'按当前筛选条件'],['来源',sources.size,'去重后的发布来源'],['渠道类型',channels.size,'覆盖来源类型'],['今日发布',todayN,'原文发布日期为今天']].map(x=>`<div class="stat-card"><div class="stat-label">${x[0]}</div><div class="stat-value">${x[1]}</div><div class="stat-foot">${x[2]}</div></div>`).join('');
  }

  function renderHotspots(){
    if(!active)return;const arr=filtered();renderStatsHot(arr);const root=$('#content');
    if(!arr.length){root.innerHTML='<div class="hotspot-empty"><strong>当前筛选下暂无热点</strong>可以清空筛选，或在“设置 / 刷新”中重新扫描对应渠道。</div>';return}
    root.innerHTML=`<div class="hotspot-list">${arr.map(x=>{
      const date=itemDate(x);const title=x.title_zh||x.title||'未命名热点';const summary=x.summary_zh||x.summary||'';
      const dateText=date?`原文发布日期 ${date}`:'发布日期未识别';
      return `<article class="hotspot-card"><div><div class="hotspot-kicker"><span class="hotspot-badge hotspot-topic">${x.topic||'行业新闻'}</span><span class="hotspot-badge">${channelCN[x.channel_type]||x.channel_type}</span><span class="hotspot-badge">${regionCN[x.region]||x.region||'全球'}</span></div><h3>${escapeHtml(title)}</h3>${summary?`<p class="hotspot-summary">${escapeHtml(summary)}</p>`:''}<div class="hotspot-meta">${escapeHtml(x.publisher||x.source_name||'未知来源')} · ${dateText}${x.country?` · ${escapeHtml(x.country)}`:''}</div></div><a class="hotspot-link" href="${escapeAttr(x.url||'#')}" target="_blank" rel="noopener noreferrer" title="打开原始发布页面">查看原文 ↗</a></article>`
    }).join('')}</div>`;
  }

  function escapeHtml(s){return String(s).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
  function escapeAttr(s){return escapeHtml(s)}

  async function loadHotspots(){
    try{const r=await fetch('data/hotspots.json?ts='+Date.now(),{cache:'no-store'});if(!r.ok)throw new Error('热点数据读取失败');data=await r.json();renderHotspots()}
    catch(e){if(active)$('#content').innerHTML=`<div class="hotspot-empty"><strong>全球热点加载失败</strong>${escapeHtml(e.message)}</div>`}
  }

  function openHotspots(){
    active=true;ensureFilters();document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));$('#hotspotNav').classList.add('active');
    $('#pageTitle').textContent='全球热点';$('#pageSubtitle').textContent='中文阅读全球宠物行业热点，日期以原文发布日期为准，并保留原始发布页面供核验。';
    $('#regionTabs').style.display='none';$('#filters').style.display='none';$('#hotspotFilters').classList.add('active');
    $('#stats').innerHTML='';$('#content').innerHTML='<div class="hotspot-empty"><strong>正在读取全球热点</strong>正在加载最新情报…</div>';loadHotspots();
  }

  function leaveHotspots(){active=false;$('#hotspotNav')?.classList.remove('active');$('#hotspotFilters')?.classList.remove('active')}

  document.addEventListener('DOMContentLoaded',()=>{
    ensureFilters();$('#hotspotNav').onclick=openHotspots;
    document.querySelectorAll('.nav-item').forEach(n=>n.addEventListener('click',leaveHotspots));
    $('#refreshDataBtn')?.addEventListener('click',()=>{if(active)setTimeout(loadHotspots,700)});
  });
})();
