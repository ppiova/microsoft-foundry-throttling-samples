// Dependency-free state regression tests. Actual browser walkthroughs complement these tests.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync(__dirname + '/app.js', 'utf8');
const settle = () => new Promise(resolve => setImmediate(resolve));
function harness() {
  const elements = new Map(), pending = [], timers = new Map();
  let sequence = 0;
  function element(id) {
    if (!elements.has(id)) {
      const classes = new Set();
      elements.set(id, {value: '', textContent: '', hidden: false, disabled: false,
        classList: {toggle(c, force) {const on = force ?? !classes.has(c); on ? classes.add(c) : classes.delete(c);}, contains: c => classes.has(c)},
        addEventListener(event, handler) {this[event] = handler;},
        setAttribute() {}, removeAttribute() {}, scrollIntoView() {}, focus() {},
        click() {if (!this.disabled) return this.onclick?.();},
        set innerHTML(value) {this.html = value; const first = value.match(/<option value="([^"]+)"/); if (first) this.value = first[1];},
        get innerHTML() {return this.html || '';}
      });
    }
    return elements.get(id);
  }
  for (const [id, value] of Object.entries({runtime:'python',target:'azure_openai',source:'LOCAL_HTTP_MOCK',scenario:'burst',speed:'10'})) element(id).value = value;
  const context = vm.createContext({document:{getElementById:element, body:element('body'), querySelector:element, querySelectorAll:()=>[]},
    AbortController, TypeError, performance:{now:()=>0},
    setTimeout(fn, ms) {const id=++sequence;timers.set(id,{fn,ms});return id;}, clearTimeout:id=>timers.delete(id),
    setInterval:()=>++sequence, clearInterval:()=>{},
    fetch(path, options) {return new Promise((resolve,reject)=> {
      options.signal.addEventListener('abort',()=>reject(Object.assign(new Error(),{name:'AbortError'})));
      pending.push({path, options, resolve(data, status=200) {resolve({ok:status<400,status,json:async()=>data});}, reject});
    });}
  });
  vm.runInContext(source, context);
  return {element, pending, timers, async ready(runs=[], dotnet=true) {pending[0].resolve({runs,dotnet});await settle();},
    change(id,value) {element(id).value=value;element(id).change();}};
}
function run(overrides={}) {return {id:'sample',signature:'same',runtime:'python',provider:'azure_openai',mode:'LOCAL_HTTP_MOCK',scenario:'burst',started:'2026-09-10T00:00:00Z',count:6,concurrency:3,outputLimit:128,summary:{completed_responses:2,http_attempts:6,http_429:4,elapsed_seconds:1},attempts:[],...overrides};}

test('connection failure exits loading and Refresh recovers',async()=>{
  const h=harness(); assert.equal(h.element('run').disabled,true);
  h.pending[0].reject(new TypeError('Failed to fetch'));await settle();
  assert.match(h.element('status').textContent,/Cannot reach/);
  assert.equal(h.element('refresh').disabled,false);
  h.element('refresh').click();h.pending[1].resolve({runs:[run()],dotnet:true});await settle();
  assert.equal(h.element('run').disabled,false);assert.equal(h.element('status').textContent,'Evidence loaded.');
});
test('recorded MAI is read only, including when .NET is unavailable',async()=>{
  const h=harness();await h.ready([run({runtime:'dotnet',provider:'mai_thinking',mode:'LIVE_AZURE',scenario:'preflight'})],false);
  h.change('runtime','dotnet');h.change('target','mai_thinking');h.change('source','LIVE_AZURE');
  assert.equal(h.element('runtime').disabled,false);assert.equal(h.element('history').disabled,false);
  assert.equal(h.element('scenario').hidden,true);assert.equal(h.element('run').hidden,true);
  await h.element('run').onclick();assert.equal(h.pending.length,1);
  assert.match(h.element('status').textContent,/Preflight/);
  h.change('source','LOCAL_HTTP_MOCK');assert.equal(h.element('run').disabled,true);
  assert.match(h.element('run-note').textContent,/not installed/);
});
test('pending simulation locks filters and prevents duplicate requests; errors survive cleanup',async()=>{
  const h=harness();await h.ready([run()]);const task=h.element('run').click();
  for(const id of ['runtime','target','source','scenario','history','refresh','command-refresh','run','replay']) assert.equal(h.element(id).disabled,true,id);
  await h.element('run').onclick();h.element('refresh').click();assert.equal(h.pending.length,2);
  h.pending[1].resolve({error:'A simulation is already running'},409);await task;
  assert.match(h.element('status').textContent,/already running/);assert.equal(h.element('runtime').disabled,false);
  assert.match(h.element('run-title').textContent,/Burst/);
});
test('evidence timeout is actionable and refresh requests are serialized',async()=>{
  const h=harness();h.element('refresh').onclick();assert.equal(h.pending.length,1);
  [...h.timers.values()].find(t=>t.ms===15000).fn();await settle();
  assert.match(h.element('status').textContent,/timed out/);assert.equal(h.element('refresh').disabled,false);
});
test('simulation timeout never retries automatically',async()=>{
  const h=harness();await h.ready();const task=h.element('run').click();
  [...h.timers.values()].find(t=>t.ms===190000).fn();await task;
  assert.match(h.element('status').textContent,/Refresh evidence before retrying/);assert.equal(h.pending.length,2);
  assert.equal(h.element('run').disabled,false);
});
test('invalid evidence response produces a recoverable error',async()=>{
  const h=harness();h.pending[0].resolve({runs:null,dotnet:true});await settle();
  assert.match(h.element('status').textContent,/Invalid evidence/);assert.equal(h.element('refresh').disabled,false);
});
test('empty recorded history disables replay and never suggests running Azure from the UI',async()=>{
  const h=harness();await h.ready();h.change('source','LIVE_AZURE');
  assert.equal(h.element('history').disabled,true);assert.equal(h.element('replay').disabled,true);
  assert.match(h.element('status').textContent,/No Azure recordings/);
});
test('successful simulation replaces the evidence and unlocks controls',async()=>{
  const h=harness();await h.ready();const task=h.element('run').click();
  h.pending[1].resolve({runs:[run()],dotnet:true});await task;
  assert.match(h.element('status').textContent,/Simulation finished/);assert.equal(h.element('replay').disabled,false);
  assert.match(h.element('metrics').innerHTML,/2 \/ 6/);
});
