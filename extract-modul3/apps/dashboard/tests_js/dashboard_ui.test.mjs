import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {runInNewContext} from 'node:vm';
import {validPoint, rankedPlaces, searchPayload, safeURL, placeLink} from '../static/dashboard/maps.mjs';

const script = readFileSync(new URL('../static/dashboard/dashboard.js',import.meta.url),'utf8').replace(/^import .*;\n/,'');
class Element {
  constructor(){this.dataset={};this.children=[];this.listeners={};this.value='';this.open=false;this.disabled=false;this.hidden=false;this.controls=new Map();}
  addEventListener(type,fn){this.listeners[type]=fn;}
  async trigger(type='click'){return this.listeners[type]?.({preventDefault(){}});}
  append(...rows){this.children.push(...rows);}
  replaceChildren(...rows){this.children=rows;}
  querySelector(key){if(!this.controls.has(key))this.controls.set(key,new Element());return this.controls.get(key);}
  showModal(){this.open=true;}
  close(){this.open=false;this.listeners.close?.();}
  set innerHTML(value){throw new Error(`Unsafe HTML ${value}`);}
}
function setup(){
  const rows=new Map(), get=key=>{if(!rows.has(key))rows.set(key,new Element());return rows.get(key);};
  const place={name:'<img onerror=alert(1)>',kind:'market',region:'Garut',address:'Garut',lat:-7.2,lon:107.9,source_url:'https://example.org'};
  get('#map-places').textContent=JSON.stringify({places:[place]});
  get('#map-config').textContent=JSON.stringify({tiles:'https://tile.openstreetmap.org/{z}/{x}/{y}.png'});
  get('#market-form').elements={region:{value:'Garut'},kind:{value:'all'}};
  get('#market-dialog').dataset.url='/modul5/places/';
  let gps=0, callback, next={places:[place],source:'curated'}, malformed=false, requests=[];
  runInNewContext(script,{validPoint,rankedPlaces,searchPayload,safeURL,placeLink,URL,JSON,
    document:{querySelector:get,createElement:()=>new Element(),head:new Element()},window:{},
    setTimeout:()=>1,clearTimeout(){},AbortController,
    navigator:{geolocation:{getCurrentPosition(fn){gps++;callback=fn;}}},
    fetch:async(url,options)=>{requests.push(JSON.parse(options.body));if(next instanceof Error)throw next;return{ok:true,json:async()=>{if(malformed)throw new SyntaxError('HTML response');return next;}};}});
  return{get,requests,setNext:v=>next=v,setMalformed:()=>malformed=true,gps:()=>gps,locate:()=>callback?.({coords:{latitude:-7.2,longitude:107.9}})};
}
test('opening map does not request GPS or geocoding and names are plain text',async()=>{
  const ui=setup(); await ui.get('#open-market').trigger();
  assert.equal(ui.gps(),0);assert.equal(ui.requests.length,0);
  assert.equal(ui.get('#market-results').children[0].children[0].children[0].textContent,'<img onerror=alert(1)>');
});
test('GPS is opt-in and remains absent from subsequent search payload',async()=>{
  const ui=setup();await ui.get('#open-market').trigger();await ui.get('#locate-market').trigger();ui.locate();
  assert.equal(ui.gps(),1);assert.equal(ui.requests.length,0);
  await ui.get('#market-form').trigger('submit');
  assert.deepEqual(ui.requests[0],{region:'Garut',kind:'all',online:false});
});
test('network failure keeps curated list available without HTML injection',async()=>{
  const ui=setup();await ui.get('#open-market').trigger();ui.setNext(new Error('Offline'));
  await ui.get('#market-form').trigger('submit');
  assert.equal(ui.get('#market-message').textContent,'Offline');
  assert.equal(ui.get('#market-results').children.length,1);
});
test('non-JSON response gives a useful error and retains curated places',async()=>{
  const ui=setup();await ui.get('#open-market').trigger();ui.setMalformed();
  await ui.get('#market-form').trigger('submit');
  assert.equal(ui.get('#market-message').textContent,'Sesi atau layanan tidak tersedia. Muat ulang halaman.');
  assert.equal(ui.get('#market-results').children.length,1);
  assert.equal(ui.get('#market-form').querySelector('[type=submit]').disabled,false);
});
