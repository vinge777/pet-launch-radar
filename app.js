const state={products:[],sources:[],brands:[],view:'today',region:'All',search:'',species:'All',category:'All',confidence:'All'};
const $=s=>document.querySelector(s); const $$=s=>[...document.querySelectorAll(s)];
const regionCN={'North America':'美国','Europe':'欧洲','Asia':'亚洲','South America':'南美'};
const fmt=d=>new Intl.DateTimeFormat('zh-CN',{month:'2-digit',day:'2-digit'}).format(new Date(d));
const daysAgo=(n)=>{const d=new Date();d.setHours(0,0,0,0);d.setDate(d.getDate()-n);return d};
const safeImg=(u,brand)=>u||`https://placehold.co/800x480/f0f3f2/31403c?text=${encodeURIComponent(brand||'Pet Product')}`;

async function load(){
  const [p,s,b]=await Promise.all([
    fetch('data/products.json?ts='+Date.now()).then(r=>r.json()),
    fetch('data/source-status.json?ts='+Date.now()).then(r=>r.json()),
    fetch('data/brands.json?ts='+Date.now()).then(r=>r.json())
  ]);
  state.products=p.products||[]; state.sources=s.sources||[]; state.brands=b.brands||[];
  $('#lastScan').textContent=p.generated_at?new Date(p.generated_at).toLocaleString('zh-CN',{hour12:false}):'暂无';
  setupCategories(); bind(); render();
}
function setupCategories(){
 const cats=[...new Set(state.products.map(x=>x.category).filter(Boolean))].sort();
 $('#categoryFilter').innerHTML='<option value="All">全部品类</option>'+cats.map(x=>`<option>${x}</option>`).join('');
}
function bind(){
 $$('.nav-item').forEach(x=>x.onclick=()=>{state.view=x.dataset.view;$$('.nav-item').forEach(n=>n.classList.remove('active'));x.classList.add('active');render()});
 $$('.region-tab').forEach(x=>x.onclick=()=>{state.region=x.dataset.region;$$('.region-tab').forEach(n=>n.classList.remove('active'));x.classList.add('active');render()});
 $('#searchInput').oninput=e=>{state.search=e.target.value.trim().toLowerCase();renderContent()};
 $('#speciesFilter').onchange=e=>{state.species=e.target.value;renderContent()};
 $('#categoryFilter').onchange=e=>{state.category=e.target.value;renderContent()};
 $('#confidenceFilter').onchange=e=>{state.confidence=e.target.value;renderContent()};
 $('#clearBtn').onclick=()=>{state.search='';state.species='All';state.category='All';state.confidence='All';$('#searchInput').value='';$('#speciesFilter').value='All';$('#categoryFilter').value='All';$('#confidenceFilter').value='All';renderContent()};
}
function baseProducts(){
 const now=new Date(); const today=new Date(now.getFullYear(),now.getMonth(),now.getDate());
 let arr=state.products.filter(p=>p.brand_origin_country!=='China'&&p.origin_verified!==false);
 if(state.view==='today') arr=arr.filter(p=>new Date(p.first_seen_at)>=today);
 if(state.view==='week') arr=arr.filter(p=>new Date(p.first_seen_at)>=daysAgo(6));
 if(state.region!=='All') arr=arr.filter(p=>p.market_region===state.region);
 return arr;
}
function filtered(){
 let arr=baseProducts();
 if(state.species!=='All') arr=arr.filter(p=>p.species===state.species);
 if(state.category!=='All') arr=arr.filter(p=>p.category===state.category);
 if(state.confidence!=='All') arr=arr.filter(p=>(p.evidence||[]).includes(state.confidence));
 if(state.search) arr=arr.filter(p=>JSON.stringify([p.brand,p.product_name,p.summary,p.country,p.category,p.tags,p.sources]).toLowerCase().includes(state.search));
 return arr.sort((a,b)=>new Date(b.first_seen_at)-new Date(a.first_seen_at));
}
function render(){
 const titles={today:['今日新品','今天新发现的非中国宠物品牌产品。'],week:['近 7 天','过去 7 天进入监测池的新品。'],all:['全部新品','按首次发现时间倒序查看历史新品。'],brands:['品牌雷达','查看已核验品牌及其市场覆盖。'],coverage:['来源覆盖','检查每天实际扫描了哪些来源以及抓取状态。']};
 $('#pageTitle').textContent=titles[state.view][0];$('#pageSubtitle').textContent=titles[state.view][1];
 const productsView=!['brands','coverage'].includes(state.view);$('#regionTabs').style.display=productsView?'flex':'none';$('#filters').style.display=productsView?'grid':'none';
 renderStats();renderCounts();renderContent();
}
function renderCounts(){
 const all=state.products.filter(p=>p.brand_origin_country!=='China'&&p.origin_verified!==false);
 const map={'All':all.length,'North America':0,'Europe':0,'Asia':0,'South America':0};all.forEach(p=>map[p.market_region]=(map[p.market_region]||0)+1);
 Object.entries(map).forEach(([k,v])=>{const el=document.getElementById('count-'+k.replaceAll(' ','-'));if(el)el.textContent=v});
}
function renderStats(){
 const arr=baseProducts(); const brands=new Set(arr.map(x=>x.brand)); const countries=new Set(arr.map(x=>x.country));
 const today=state.products.filter(p=>new Date(p.first_seen_at)>=daysAgo(0)&&p.origin_verified!==false&&p.brand_origin_country!=='China').length;
 $('#stats').innerHTML=[
  ['当前结果',arr.length,'按当前时间与地区范围'],['涉及品牌',brands.size,'已核验非中国品牌'],['市场国家',countries.size,'按上市市场计'],['今日新发现',today,'每日扫描自动更新']
 ].map(x=>`<div class="stat-card"><div class="stat-label">${x[0]}</div><div class="stat-value">${x[1]}</div><div class="stat-foot">${x[2]}</div></div>`).join('');
}
function renderContent(){
 if(state.view==='brands')return renderBrands(); if(state.view==='coverage')return renderCoverage();
 const arr=filtered(); const root=$('#content'); if(!arr.length){root.innerHTML='<div class="empty"><strong>当前筛选下暂无新品</strong>这不代表市场没有新品，可到“来源覆盖”查看最近抓取状态。</div>';return}
 const groups={};arr.forEach(p=>{const k=(p.launch_date||p.first_seen_at).slice(0,10);(groups[k]??=[]).push(p)});
 root.innerHTML='';Object.keys(groups).sort().reverse().forEach(date=>{
  const sec=document.createElement('section');sec.className='day-group';sec.innerHTML=`<div class="day-heading"><h2>${date}</h2><span>${groups[date].length} 个新品</span><div class="day-line"></div></div><div class="product-grid"></div>`;
  const grid=sec.querySelector('.product-grid');groups[date].forEach(p=>grid.appendChild(card(p)));root.appendChild(sec)
 });
}
function card(p){
 const node=$('#productCardTemplate').content.firstElementChild.cloneNode(true);const img=node.querySelector('.product-image');img.src=safeImg(p.image_url,p.brand);img.alt=p.product_name;img.onerror=()=>img.src=safeImg('',p.brand);
 node.querySelector('.region-pill').textContent=`${regionCN[p.market_region]||p.market_region} · ${p.country}`;node.querySelector('.brand-name').textContent=p.brand;node.querySelector('.launch-date').textContent=`发现 ${fmt(p.first_seen_at)}`;node.querySelector('.product-name').textContent=p.product_name;node.querySelector('.product-summary').textContent=p.summary||'暂无摘要';
 node.querySelector('.chips').innerHTML=[p.species,p.category,...(p.tags||[]).slice(0,2)].filter(Boolean).map(x=>`<span class="chip">${x}</span>`).join('');
 node.querySelector('.source-stack').innerHTML=(p.evidence||[]).map(x=>`<span class="evidence ${x}">${x==='official'?'官方':x==='retailer'?'零售商':'行业媒体'}</span>`).join('');
 const detailSource=(p.sources||[]).find(s=>s.page_type==='product_detail');
 const fallbackSource=(p.sources||[]).find(s=>s.page_type==='launch_announcement')||(p.sources||[]).find(s=>s.page_type==='catalog')||(p.sources||[])[0];
 const detailUrl=p.product_url||detailSource?.url;
 const a=node.querySelector('.source-link');
 a.href=detailUrl||fallbackSource?.url||'#';
 if(detailUrl){a.textContent='产品详情 ↗';a.title='打开该产品的具体详情页';}
 else if(fallbackSource?.page_type==='launch_announcement'){a.textContent='新品发布页 ↗';a.title='该产品暂未找到独立详情页，打开官方新品发布页';}
 else{a.textContent='发现来源 ↗';a.title='该产品暂未找到独立详情页，打开发现来源';}
 return node;
}
function renderBrands(){
 const root=$('#content');const rows=state.brands.filter(b=>b.origin_country!=='China').sort((a,b)=>a.name.localeCompare(b.name));
 root.innerHTML=`<div class="panel"><h3>已核验品牌库 · ${rows.length}</h3><table class="brand-table"><tr><th>品牌</th><th>品牌原产地</th><th>重点市场</th><th>分类</th><th>监测状态</th></tr>${rows.map(b=>`<tr><td><strong>${b.name}</strong></td><td>${b.origin_country}</td><td>${(b.market_regions||[]).map(x=>regionCN[x]||x).join(' / ')}</td><td>${(b.categories||[]).join(', ')}</td><td>${b.active?'监测中':'暂停'}</td></tr>`).join('')}</table></div>`
}
function renderCoverage(){
 const root=$('#content');const ok=state.sources.filter(s=>s.status==='ok').length;
 root.innerHTML=`<div class="coverage-grid"><div class="panel"><h3>抓取来源 · ${state.sources.length}</h3>${state.sources.map(s=>`<div class="source-row"><div><strong>${s.name}</strong><br><span style="color:#7d8790">${s.type}</span></div><div>${regionCN[s.region]||s.region}</div><div>${s.items_found||0} 条</div><div class="${s.status==='ok'?'status-ok':'status-warn'}">${s.status==='ok'?'正常':'需检查'}</div></div>`).join('')}</div><div class="panel"><h3>今日覆盖健康度</h3><div class="stat-value">${state.sources.length?Math.round(ok/state.sources.length*100):0}%</div><p style="color:#707a83;font-size:12px;line-height:1.7">“全球全部新品”无法由单一来源保证。本站通过官方、零售商、行业媒体三层交叉覆盖，并把失效来源直接暴露出来，避免数据黑箱。</p><div class="chips"><span class="chip">官方优先</span><span class="chip">来源可追溯</span><span class="chip">未知中国来源隐藏</span><span class="chip">每日去重</span></div></div></div>`
}
load().catch(e=>{$('#content').innerHTML=`<div class="empty"><strong>数据加载失败</strong>${e.message}</div>`});
