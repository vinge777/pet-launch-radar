(() => {
  function enhanceResearchUI(){
    const select=document.querySelector('#hotspotChannel');
    if(select&&!select.querySelector('option[value="research_institute"]')){
      const opt=document.createElement('option');
      opt.value='research_institute';
      opt.textContent='研究机构 / 数据机构';
      select.appendChild(opt);
    }

    document.querySelectorAll('.hotspot-badge').forEach(el=>{
      if(el.textContent.trim()==='research_institute'){
        el.textContent='研究机构';
        el.classList.add('research-source-badge');
      }
    });
  }

  document.addEventListener('DOMContentLoaded',()=>{
    const style=document.createElement('style');
    style.textContent='.research-source-badge{background:#eef0ff!important;color:#37409a!important;border:1px solid #d9ddff!important}';
    document.head.appendChild(style);
    enhanceResearchUI();
    const root=document.querySelector('#content')||document.body;
    new MutationObserver(enhanceResearchUI).observe(root,{childList:true,subtree:true});
  });
})();
