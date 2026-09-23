(() => {
  const channelCN={brand_official:'品牌官网',specialty_retail:'宠物专业渠道',mass_retail:'商超 / 综合零售',drugstore:'药妆 / 药房',marketplace:'综合电商',trade_media:'行业媒体 / 全网发现'};
  const regionCN={'North America':'美国','Europe':'欧洲','Asia':'亚洲','South America':'南美','Global':'全球'};
  const segmentCN={food:'宠物食品',supplies:'宠物用品',industry:'行业综合'};
  const FAVORITES_KEY='petLaunchRadar.hotspotFavorites.v1';
  let data={items:[],source_status:[],generated_at:null};
  let view='none';
  let favorites=loadFavorites();
  const filters={search:'',channel:'all',region:'all',segment:'food',start:'',end:''};
  const $=s=>document.querySelector(s);

  function loadFavorites(){
    try{
      const raw=JSON.parse(localStorage.getItem(FAVORITES_KEY)||'[]');
      return Array.isArray(raw)?raw:[];
    }catch(e){return []}
  }

  function saveFavorites(){
    try{localStorage.setItem(FAVORITES_KEY,JSON.stringify(favorites))}catch(e){}
    updateFavoriteCount();
  }

  const favoriteKey=x=>String(x?.url||x?.id||'');
  const isFavorite=x=>favorites.some(f=>favoriteKey(f)===favoriteKey(x));

  function favoriteSnapshot(x){
    return {
      id:x.id||'',title:x.title||'',title_zh:x.title_zh||'',summary:x.summary||'',summary_zh:x.summary_zh||'',url:x.url||'',
      publisher:x.publisher||'',source_name:x.source_name||'',source_id:x.source_id||'',channel_type:x.channel_type||'',region:x.region||'',country:x.country||'',
      topic:x.topic||'',published_at:x.published_at||'',segment:x.segment||'industry',segment_zh:x.segment_zh||segmentCN[x.segment]||'行业综合',
      subcategory_zh:x.subcategory_zh||'',food_priority:x.food_priority||0,saved_at:new Date().toISOString()
    };
  }

  function toggleFavorite(item){
    const key=favoriteKey(item);if(!key)return;
    const index=favorites.findIndex(f=>favoriteKey(f)===key);
    if(index>=0) favorites.splice(index,1); else favorites.unshift(favoriteSnapshot(item));
    saveFavorites();renderCurrent();
  }

  function updateFavoriteCount(){
    const el=$('#favoriteCount');if(el)el.textContent=favorites.length;
  }

  function syncSegmentButtons(){
    document.querySelectorAll('.hotspot-segment-btn').forEach(btn=>btn.classList.toggle('active',btn.dataset.segment===filters.segment));
  }

  function resetFilters(){
    filters.search='';filters.channel='all';filters.region='all';filters.start='';filters.end='';filters.segment=view==='favorites'?'all':'food';
    if($('#hotspotSearch'))$('#hotspotSearch').value='';
    if($('#hotspotChannel'))$('#hotspotChannel').value='all';
    if($('#hotspotRegion'))$('#hotspotRegion').value='all';
    if($('#hotspotStart'))$('#hotspotStart').value='';
    if($('#hotspotEnd'))$('#hotspotEnd').value='';
    syncSegmentButtons();
  }

  function ensureFilters(){
    if($('#hotspotFilters')) return;
    const box=document.createElement('section');
    box.id='hotspotFilters';box.className='hotspot-filters';
    box.innerHTML=`
      <div class="hotspot-segments" aria-label="热点类别">
        <button type="button" class="hotspot-segment-btn active" data-segment="food"><strong>宠物食品</strong><span>默认优先</span></button>
        <button type="button" class="hotspot-segment-btn" data-segment="supplies"><strong>宠物用品</strong><span>用品单独查看</span></button>
        <button type="button" class="hotspot-segment-btn" data-segment="industry"><strong>行业综合</strong><span>宏观与产业</span></button>
        <button type="button" class="hotspot-segment-btn" data-segment="all"><strong>全部</strong><span>合并查看</span></button>
      </div>
      <div class="hotspot-search"><span>⌕</span><input id="hotspotSearch" placeholder="搜索趋势、新闻、品牌、渠道、关键词…"></div>
      <select id="hotspotChannel"><option value="all">全部来源类型</option>${Object.entries(channelCN).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select>
      <select id="hotspotRegion"><option value="all">全部地区</option><option value="North America">美国</option><option value="Europe">欧洲</option><option value="Asia">亚洲</option><option value="South America">南美</option><option value="Global">全球</option></select>
      <label class="hotspot-date-label">开始日期<input id="hotspotStart" type="date"></label>
      <label class="hotspot-date-label">结束日期<input id="hotspotEnd" type="date"></label>
      <button id="hotspotClear" type="button">清空</button>`;
    $('#stats').insertAdjacentElement('afterend',box);
    box.querySelectorAll('.hotspot-segment-btn').forEach(btn=>btn.onclick=()=>{filters.segment=btn.dataset.segment;syncSegmentButtons();renderCurrent()});
    $('#hotspotSearch').oninput=e=>{filters.search=e.target.value.trim().toLowerCase();renderCurrent()};
    $('#hotspotChannel').onchange=e=>{filters.channel=e.target.value;renderCurrent()};
    $('#hotspotRegion').onchange=e=>{filters.region=e.target.value;renderCurrent()};
    $('#hotspotStart').onchange=e=>{filters.start=e.target.value;if(filters.end&&filters.start>filters.end){filters.end=filters.start;$('#hotspotEnd').value=filters.end}renderCurrent()};
    $('#hotspotEnd').onchange=e=>{filters.end=e.target.value;if(filters.start&&filters.end<filters.start){filters.start=filters.end;$('#hotspotStart').value=filters.start}renderCurrent()};
    $('#hotspotClear').onclick=()=>{resetFilters();renderCurrent()};
  }

  const itemDate=x=>String(x.published_at||'').slice(0,10);
  const publishedTime=x=>x.published_at?new Date(x.published_at).getTime():0;
  const itemSegment=x=>x.segment||'industry';

  function filtered(){
    const source=view==='favorites'?favorites:data.items;
    return source.filter(x=>{
      if(filters.segment!=='all'&&itemSegment(x)!==filters.segment)return false;
      if(filters.channel!=='all'&&x.channel_type!==filters.channel)return false;
      if(filters.region!=='all'&&x.region!==filters.region)return false;
      const d=itemDate(x);
      if((filters.start||filters.end)&&!d)return false;
      if(filters.start&&d<filters.start)return false;if(filters.end&&d>filters.end)return false;
      if(filters.search){
        const hay=JSON.stringify([x.title_zh,x.title,x.summary_zh,x.summary,x.publisher,x.source_name,x.topic,x.country,x.segment_zh,x.subcategory_zh,channelCN[x.channel_type]]).toLowerCase();
        if(!hay.includes(filters.search))return false;
      }
      return true;
    }).sort((a,b)=>publishedTime(b)-publishedTime(a));
  }

  function segmentCounts(source){
    return {
      food:source.filter(x=>itemSegment(x)==='food').length,
      supplies:source.filter(x=>itemSegment(x)==='supplies').length,
      industry:source.filter(x=>itemSegment(x)==='industry').length
    };
  }

  function renderStats(arr){
    const sources=new Set(arr.map(x=>x.publisher||x.source_name));
    const today=new Date().toISOString().slice(0,10);const todayN=arr.filter(x=>itemDate(x)===today).length;
    const source=view==='favorites'?favorites:data.items;const counts=segmentCounts(source);
    if(view==='favorites'){
      $('#stats').innerHTML=[['收藏文章',arr.length,'按当前筛选条件'],['食品收藏',counts.food,'宠物食品相关文章'],['用品收藏',counts.supplies,'宠物用品相关文章'],['收藏夹总数',favorites.length,'保存在当前浏览器']].map(x=>`<div class="stat-card"><div class="stat-label">${x[0]}</div><div class="stat-value">${x[1]}</div><div class="stat-foot">${x[2]}</div></div>`).join('');
    }else{
      const activeLabel=filters.segment==='food'?'食品热点':filters.segment==='supplies'?'用品热点':filters.segment==='industry'?'行业综合':'热点结果';
      $('#stats').innerHTML=[[activeLabel,arr.length,'按当前分类与筛选条件'],['宠物食品',counts.food,'系统优先采集与展示'],['宠物用品',counts.supplies,'与食品分开收集'],['今日发布',todayN,'原文发布日期为今天']].map(x=>`<div class="stat-card"><div class="stat-label">${x[0]}</div><div class="stat-value">${x[1]}</div><div class="stat-foot">${x[2]}</div></div>`).join('');
    }
  }

  function cardHtml(x){
    const date=itemDate(x);const title=x.title_zh||x.title||'未命名热点';const summary=x.summary_zh||'原文摘要暂未识别。';
    const dateText=date?`原文发布日期 ${date}`:'发布日期未识别';const saved=isFavorite(x);const segment=itemSegment(x);
    const segmentLabel=x.segment_zh||segmentCN[segment]||'行业综合';const sub=x.subcategory_zh||'';
    return `<article class="hotspot-card"><div class="hotspot-main"><div class="hotspot-kicker"><span class="hotspot-badge hotspot-segment-badge ${escapeAttr('segment-'+segment)}">${escapeHtml(segmentLabel)}</span>${sub?`<span class="hotspot-badge">${escapeHtml(sub)}</span>`:''}<span class="hotspot-badge hotspot-topic">${escapeHtml(x.topic||'行业新闻')}</span><span class="hotspot-badge">${escapeHtml(channelCN[x.channel_type]||x.channel_type||'未知渠道')}</span><span class="hotspot-badge">${escapeHtml(regionCN[x.region]||x.region||'全球')}</span></div><div class="hotspot-headline-row"><h3>${escapeHtml(title)}</h3><p class="hotspot-summary">${escapeHtml(summary)}</p></div><div class="hotspot-meta">${escapeHtml(x.publisher||x.source_name||'未知来源')} · ${escapeHtml(dateText)}${x.country?` · ${escapeHtml(x.country)}`:''}</div></div><div class="hotspot-actions"><button class="favorite-btn${saved?' saved':''}" type="button" data-favorite-url="${escapeAttr(favoriteKey(x))}" title="${saved?'取消收藏':'收藏到我的收藏夹'}">${saved?'★ 已收藏':'☆ 收藏'}</button><a class="hotspot-link" href="${escapeAttr(x.url||'#')}" target="_blank" rel="noopener noreferrer" title="打开原始发布页面">查看原文 ↗</a></div></article>`;
  }

  function renderCurrent(){
    if(view==='none')return;const arr=filtered();renderStats(arr);const root=$('#content');
    if(!arr.length){
      const label=filters.segment==='food'?'宠物食品':filters.segment==='supplies'?'宠物用品':filters.segment==='industry'?'行业综合':'';
      root.innerHTML=view==='favorites'?`<div class="hotspot-empty"><strong>${label?label+'暂无收藏':'收藏夹还是空的'}</strong>在「全球热点」中点击 ☆ 收藏，文章会保存在这里。</div>`:`<div class="hotspot-empty"><strong>${label||'当前筛选'}暂无热点</strong>可以切换类别、清空筛选，或在“设置 / 刷新”中重新扫描对应渠道。</div>`;
      return;
    }
    root.innerHTML=`<div class="hotspot-list">${arr.map(cardHtml).join('')}</div>`;
  }

  function escapeHtml(s){return String(s).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
  function escapeAttr(s){return escapeHtml(s)}

  async function loadHotspots(){
    try{
      const r=await fetch('data/hotspots.json?ts='+Date.now(),{cache:'no-store'});if(!r.ok)throw new Error('热点数据读取失败');data=await r.json();
      const latestByUrl=new Map((data.items||[]).map(x=>[favoriteKey(x),x]));
      let changed=false;
      favorites=favorites.map(f=>{const latest=latestByUrl.get(favoriteKey(f));if(!latest)return f;changed=true;return {...favoriteSnapshot(latest),saved_at:f.saved_at||new Date().toISOString()}});
      if(changed)saveFavorites();
      renderCurrent();
    }catch(e){if(view==='hotspots')$('#content').innerHTML=`<div class="hotspot-empty"><strong>全球热点加载失败</strong>${escapeHtml(e.message)}</div>`}
  }

  function prepareSpecialView(){
    ensureFilters();document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));$('#hotspotNav')?.classList.remove('active');$('#favoriteNav')?.classList.remove('active');
    $('#regionTabs').style.display='none';$('#filters').style.display='none';$('#hotspotFilters').classList.add('active');$('#stats').innerHTML='';
  }

  function openHotspots(){
    view='hotspots';filters.segment='food';prepareSpecialView();syncSegmentButtons();$('#hotspotNav').classList.add('active');
    $('#pageTitle').textContent='全球热点';$('#pageSubtitle').textContent='宠物食品与宠物用品分开监测；默认优先展示宠物食品，并提高食品新品、营养、原料、加工与市场趋势的采集权重。';
    $('#content').innerHTML='<div class="hotspot-empty"><strong>正在读取全球热点</strong>正在加载最新情报…</div>';loadHotspots();
  }

  function openFavorites(){
    view='favorites';filters.segment='all';prepareSpecialView();syncSegmentButtons();$('#favoriteNav').classList.add('active');
    $('#pageTitle').textContent='我的收藏夹';$('#pageSubtitle').textContent='你在“全球热点”中收藏的文章，可继续按宠物食品、宠物用品和行业综合分类查看。';
    renderCurrent();
  }

  function leaveSpecialViews(){view='none';$('#hotspotNav')?.classList.remove('active');$('#favoriteNav')?.classList.remove('active');$('#hotspotFilters')?.classList.remove('active')}

  document.addEventListener('DOMContentLoaded',()=>{
    ensureFilters();updateFavoriteCount();$('#hotspotNav').onclick=openHotspots;$('#favoriteNav').onclick=openFavorites;
    document.querySelectorAll('.nav-item').forEach(n=>n.addEventListener('click',leaveSpecialViews));
    $('#content').addEventListener('click',e=>{
      const btn=e.target.closest('.favorite-btn');if(!btn)return;
      const key=btn.dataset.favoriteUrl||'';
      const source=(view==='favorites'?favorites:data.items);const item=source.find(x=>favoriteKey(x)===key)||favorites.find(x=>favoriteKey(x)===key);
      if(item)toggleFavorite(item);
    });
    $('#refreshDataBtn')?.addEventListener('click',()=>{if(view==='hotspots')setTimeout(loadHotspots,700);if(view==='favorites')setTimeout(renderCurrent,700)});
  });
})();
