import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {runInNewContext} from 'node:vm';
const script=readFileSync(new URL('../static/recipe_book/reviews.js',import.meta.url),'utf8');
class Element{
  constructor(){this.dataset={};this.listeners={};this.controls=new Map();this.disabled=false;this.value='';}
  addEventListener(t,f){this.listeners[t]=f;}
  querySelector(k){if(!this.controls.has(k))this.controls.set(k,new Element());return this.controls.get(k);}
  querySelectorAll(){return[this.querySelector('button')];}
  async trigger(t='click'){return this.listeners[t]?.({preventDefault(){}});}
  set innerHTML(v){throw new Error(`Unsafe HTML ${v}`);}
}
function setup(){
  const rows=new Map(),get=k=>{if(!rows.has(k))rows.set(k,new Element());return rows.get(k);};
  get('#review-form').dataset={code:'TEST',url:'/modul4/review/',version:'2'};
  get('#review-form').elements={rating:{value:'5'},comment:{value:'<script>user text</script>'}};
  let requests=[],ok=false,reloads=0;
  runInNewContext(script,{document:{querySelector:get},window:{confirm:()=>true},location:{reload:()=>reloads++},
    fetch:async(url,o)=>{requests.push(JSON.parse(o.body));return{ok,json:async()=>ok?{version:3}:{error:'<img onerror=alert(1)>'}};}});
  return{get,requests,setOK:v=>ok=v,reloads:()=>reloads};
}
test('review edits include own version and errors render as text',async()=>{
  const ui=setup();ui.get('#review-form').listeners.submit({preventDefault(){}});await new Promise(r=>setImmediate(r));
  assert.equal(ui.requests[0].version,2);assert.equal(ui.requests[0].rating,5);
  assert.equal(ui.get('#review-error').textContent,'<img onerror=alert(1)>');assert.equal(ui.reloads(),0);
});
test('delete is explicit and preserves required version',async()=>{
  const ui=setup();ui.setOK(true);ui.get('#delete-review').listeners.click();await new Promise(r=>setImmediate(r));
  assert.equal(ui.requests[0].action,'delete');assert.equal(ui.requests[0].version,2);assert.equal(ui.reloads(),1);
});
