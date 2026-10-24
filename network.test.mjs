import {test} from 'node:test';
import assert from 'node:assert/strict';
import {publicAddress,publicUrl} from './network.mjs';
test('reject private, loopback, mapped and reserved network addresses',()=>{
  for(const ip of ['127.0.0.1','10.0.0.1','172.16.0.1','192.168.1.1','169.254.169.254','100.64.0.1','0.0.0.0','::1','fc00::1','fe80::1','::ffff:127.0.0.1'])assert.equal(publicAddress(ip),false,ip);
  assert(publicAddress('1.1.1.1'));assert(publicAddress('2606:4700:4700::1111'));
});
test('reject credentials, private parameters and local protocols',()=>{
  for(const url of ['file:///etc/passwd','http://localhost','http://x.local','https://u:p@example.com','https://example.com:444','https://example.com/?token=x'])assert.throws(()=>publicUrl(url));
  assert.equal(publicUrl('https://example.com/products/food').hostname,'example.com');
});
