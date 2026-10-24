import dns from 'node:dns/promises';
import http from 'node:http';
import https from 'node:https';
import ipaddr from 'ipaddr.js';
export function publicAddress(address) {
  try {let ip=ipaddr.parse(address);if(ip.kind()==='ipv6'&&ip.isIPv4MappedAddress())ip=ip.toIPv4Address();return ip.range()==='unicast';}catch{return false;}
}
export function publicUrl(raw) {
  const url=new URL(raw);
  if(!['http:','https:'].includes(url.protocol)||url.username||url.password||url.port&&!['80','443'].includes(url.port)||/^(localhost)$|\.(localhost|local|internal)$/i.test(url.hostname))throw Error('Only public HTTP URLs are supported');
  if([...url.searchParams.keys()].some(k=>/token|password|secret|session|authorization|api.?key/i.test(k)))throw Error('Private query parameters are not supported');
  return url;
}
export async function publicFetch(raw) {
  const url=publicUrl(raw),hostname=url.hostname.replace(/^\[|\]$/g,'');
  const addresses=await dns.lookup(hostname,{all:true});
  if(!addresses.length||addresses.some(a=>!publicAddress(a.address)))throw Error('Non-public destination blocked');
  // Pin the checked address for the connection, including every redirect.
  const target=addresses[0];
  return new Promise((resolve,reject)=>{
    const request=(url.protocol==='https:'?https:http).request(url,{method:'GET',lookup:(_host,_options,cb)=>cb(null,target.address,target.family),headers:{accept:'text/html,application/json,application/javascript,text/css,*/*;q=0.5','user-agent':'Mozilla/5.0 (compatible; PetCatalogResearch/1.0)'}},response=>{
      const chunks=[];let bytes=0;
      response.on('data',chunk=>{bytes+=chunk.length;if(bytes>3_000_000){response.destroy(Error('Page too large'));return;}chunks.push(chunk);});
      response.on('error',reject);response.on('end',()=>resolve({status:response.statusCode||502,headers:response.headers,body:Buffer.concat(chunks)}));
    });
    request.on('error',reject);request.setTimeout(12000,()=>request.destroy(Error('Upstream timeout')));request.end();
  });
}
