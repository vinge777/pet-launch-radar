import http from 'node:http';
import {timingSafeEqual} from 'node:crypto';
import {chromium} from 'playwright';
import {publicUrl,publicFetch} from './network.mjs';
const token=process.env.BROWSER_RELAY_TOKEN;
if(!token||token.length<32)throw Error('Set BROWSER_RELAY_TOKEN to a random secret of at least 32 characters');
let active=0,browserPromise;
const browser=()=>browserPromise ||= chromium.launch({headless:true}).then(b=>{b.on('disconnected',()=>{browserPromise=undefined;});return b;}).catch(e=>{browserPromise=undefined;throw e;});
function authorized(header){const a=Buffer.from(header||''),b=Buffer.from(`Bearer ${token}`);return a.length===b.length&&timingSafeEqual(a,b);}
http.createServer(async(req,res)=>{
  const send=(status,body,type='text/plain')=>{res.writeHead(status,{'content-type':type,'cache-control':'no-store'});res.end(body);};
  if(req.url==='/health'&&req.method==='GET')return send(200,'ok');
  if(!authorized(req.headers.authorization))return send(401,'Unauthorized');
  if(req.url!=='/scrape'||req.method!=='POST')return send(404,'Not found');
  if(active>=1)return send(429,'Browser busy; retry later');
  active++;let context,timer;
  try {
    let raw='';for await(const chunk of req){raw+=chunk;if(raw.length>8192)throw Error('Request too large');}
    const url=publicUrl(JSON.parse(raw).url).href;
    context=await (await browser()).newContext({serviceWorkers:'block',acceptDownloads:false});
    timer=setTimeout(()=>void context.close(),28000);
    let bytes=0,requests=0;
    await context.route('**/*',async route=>{
      try {
        const request=route.request();
        if(request.method()!=='GET'||['image','media','font'].includes(request.resourceType())||++requests>80)return route.abort();
        const response=await publicFetch(request.url());bytes+=response.body.length;
        if(bytes>12_000_000)return route.abort();
        const headers={};for(const key of ['content-type','location'])if(typeof response.headers[key]==='string')headers[key]=response.headers[key];
        await route.fulfill({status:response.status,headers,body:response.body});
      }catch{await route.abort().catch(()=>{});}
    });
    await context.routeWebSocket('**/*',socket=>socket.close());
    const page=await context.newPage();
    const response=await page.goto(url,{waitUntil:'domcontentloaded',timeout:22000});
    if(!response||response.status()>=400)throw Error('Source did not return a readable page');
    await page.waitForLoadState('networkidle',{timeout:3500}).catch(()=>{});
    const html=await page.content();
    if(Buffer.byteLength(html)>3_000_000)throw Error('Rendered page too large');
    if(/<title[^>]*>\s*(?:Access Denied|Just a moment|Robot Check|Security Check)/i.test(html))throw Error('Source requires verification');
    const base=page.url().replaceAll('&','&amp;').replaceAll('"','&quot;');
    send(200,`<base href="${base}">${html}`,'text/html; charset=utf-8');
  }catch(error){console.error('Browser read failed:',error instanceof Error?error.message:'unknown');send(502,'Browser could not read this public page; retain for retry');}
  finally{clearTimeout(timer);await context?.close().catch(()=>{});active--;}
}).listen(Number(process.env.PORT||10000),'0.0.0.0');
