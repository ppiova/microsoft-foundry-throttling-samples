const $=id=>document.getElementById(id);
let all=[],current=null,busy=false,timer=null,elapsed=Infinity,loading=false,ready=false,hasDotnet=true;
const names={burst:'Burst',retry:'Retry with backoff',paced:'Paced requests',preflight:'Preflight',baseline:'Baseline',guarded:'Guarded'};
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=n=>Number(n||0).toFixed(1);
function filtered(){return all.filter(r=>r.runtime===$('runtime').value&&r.provider===$('target').value&&r.mode===$('source').value)}
function stop(){if(timer)clearInterval(timer);timer=null;elapsed=Infinity;$('replay').textContent='▶ Replay'}
function choose(id){stop();current=filtered().find(r=>r.id===id)||filtered()[0]||null;render()}
function histories(preferred){const list=filtered();$('history').innerHTML=list.length?list.map(r=>`<option value="${r.id}">${esc(names[r.scenario]||r.scenario)} · ${esc(new Date(r.started).toLocaleString('en-US',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit'}))}</option>`).join(''):'<option>No saved executions</option>';if(preferred&&list.some(r=>r.id===preferred))$('history').value=preferred;choose($('history').value);const live=$('source').value==='LIVE_AZURE';recordedControls(live,list);$('run').disabled=busy||live||($('runtime').value==='dotnet'&&!hasDotnet);$('run-note').textContent=live?'Read-only playback of saved Azure evidence. No live requests are sent.':'6 requests · 3 workers · 128 output cap. Loopback HTTP only. No Azure calls.'}
async function requestJson(path, options={}, timeout=15000) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);
    try {
        const response = await fetch(path, {...options, signal:controller.signal});
        const data = await response.json();
        if (!response.ok) throw Error(data.error || `Request failed (HTTP ${response.status})`);
        if (!Array.isArray(data.runs) || typeof data.dotnet !== 'boolean') throw Error('Invalid evidence response. Refresh to try again.');
        return data;
    } catch (error) {
        if (error.name === 'AbortError') throw Error(path === '/api/run'
            ? 'The simulation response timed out. It may still finish on the server. Refresh evidence before retrying.'
            : 'The evidence request timed out. Check the local server, then Refresh.');
        if (error instanceof TypeError) throw Error('Cannot reach the local server. Check that it is running, then Refresh.');
        throw error;
    } finally { clearTimeout(timeoutId); }
}
function syncControls() {
    const locked = busy || loading;
    for (const id of ['runtime','target','source','scenario','history']) $(id).disabled = locked || !ready;
    $('scenario').disabled ||= $('source').value === 'LIVE_AZURE';
    $('history').disabled ||= filtered().length === 0;
    $('run').disabled = locked || !ready || $('source').value === 'LIVE_AZURE' || ($('runtime').value === 'dotnet' && !hasDotnet);
    $('refresh').disabled = locked;
    $('command-refresh').disabled = locked;
    $('command-new').disabled = locked || !ready;
    $('replay').disabled = locked || !current;
    $('experiment')?.setAttribute('aria-busy', String(locked));
    if (!hasDotnet && $('runtime').value === 'dotnet' && $('source').value === 'LOCAL_HTTP_MOCK') {
        $('run-note').textContent = '.NET is not installed on this server. Recorded .NET evidence remains available; use Python for local simulation.';
    }
}
async function load(preferred=current?.id) {
    if (busy || loading) return;
    loading = true; stop(); syncControls(); $('status').textContent = 'Loading saved evidence…';
    try {
        const data = await requestJson('/api/runs');
        all = data.runs; ready = true;
        hasDotnet = data.dotnet;
        histories(preferred);
        if (data.skipped) $('status').textContent = `${data.skipped} unsupported or incomplete report(s) omitted.`;
        else if ($('source').value !== 'LIVE_AZURE') $('status').textContent = 'Evidence loaded.';
    } catch(error) { $('status').textContent = error.message; }
    finally { loading = false; syncControls(); }
}
function render(){const r=current;const live=(r?.mode||$('source').value)==='LIVE_AZURE';$('mode').textContent=live?'RECORDED AZURE · READ ONLY':'LOCAL SIMULATION';$('mode').classList.toggle('azure',live);$('run-title').textContent=r?`${names[r.scenario]||r.scenario} / ${r.runtime==='python'?'Python':'C# · .NET 10'}`:(live?'No Azure recording selected':'Your next experiment starts here');$('context').textContent=r?`${r.provider==='azure_openai'?'Azure OpenAI':'Microsoft MAI'} · ${r.count} requests · ${r.concurrency} workers · output cap ${r.outputLimit} · ${live?'recorded evidence':'synthetic service responses'}`:(live?'Select a runtime and model with saved Azure evidence, or switch to the local simulator.':'Choose a strategy and run a local simulation. No cloud credentials needed.');$('replay').disabled=!r;
const s=r?.summary||{};$('metrics').innerHTML=[['Completed',`${s.completed_responses||0} / ${r?.count||0}`,'Generation completed','success'],['HTTP attempts',s.http_attempts||0,'Includes retries',''],['Rate limited',s.http_429||0,'HTTP 429 responses',s.http_429?'alert':''],['E2E p95',`${fmt(s.p95_e2e_seconds)}s`,'Queue + waits + HTTP','']].map(([label,value,note,cls])=>`<div class="metric ${cls}"><label>${label}</label><strong>${value}</strong><small>${note}</small></div>`).join('');
$('insight').innerHTML=!r&&live?'No recorded evidence is available for this selection.':!r?'Start with <strong>Burst</strong>, then run <strong>Retry</strong> and <strong>Paced</strong> with the same settings.':live?(s.http_429?'A 429 was recorded. Inspect the service evidence before attributing a cause.':'<strong>No 429 was observed in this run.</strong> This workload did not reproduce throttling. It does not show that the service has no limits.'):(s.http_429?`<strong>${s.http_429} synthetic 429 responses.</strong> ${s.retries?`${s.retries} retries added HTTP attempts while retaining ${r.count} logical requests.`:'A burst can exceed the mock service window. Compare retry and pacing using the same workload.'}`:'<strong>No synthetic 429 responses.</strong> Inspect the send intervals and compare with a matching burst. This is a local simulation, not Azure capacity evidence.');draw();comparison()}
function draw(){const r=current;if(!r){$('timeline').innerHTML='<div class="empty">No execution selected</div>';$('logs').innerHTML='';$('clock').textContent='0.0 s';return}const end=Math.max(.1,r.summary.elapsed_seconds,...r.attempts.map(a=>a.sent_after_seconds+a.http_seconds));$('clock').textContent=`${fmt(Math.min(elapsed,end))} s`;
$('timeline').innerHTML=Array.from({length:Math.min(r.count,200)},(_,i)=>{const attempts=r.attempts.filter(a=>a.job===i+1&&a.sent_after_seconds<=elapsed);return `<div class="lane"><span class="lane-label">REQ ${String(i+1).padStart(2,'0')}</span><div class="track">${attempts.map(a=>{const done=a.sent_after_seconds+a.http_seconds<=elapsed;const cls=!done?'other':a.status===429?'fail':a.status>=200&&a.status<300?'ok':'other';const duration=Math.min(a.http_seconds,Math.max(0,elapsed-a.sent_after_seconds));return `<span class="attempt ${cls}" style="left:${Math.min(99,a.sent_after_seconds/end*100)}%;width:${Math.min(100,duration/end*100)}%" title="${esc(`Request ${a.job}, attempt ${a.attempt}: ${done?'HTTP '+a.status:'in flight'}; ${fmt(a.http_seconds)}s`)}"></span>`}).join('')}</div></div>`}).join('')+`<div class="axis">${[0,.25,.5,.75,1].map(f=>`<span>${fmt(end*f)}s</span>`).join('')}</div>`;
$('logs').innerHTML=r.attempts.filter(a=>a.sent_after_seconds+a.http_seconds<=elapsed).sort((a,b)=>a.sent_after_seconds-b.sent_after_seconds).map(a=>`<tr><td>${fmt(a.sent_after_seconds)}</td><td>${a.job}</td><td>${a.attempt}</td><td>${a.status}</td><td>${fmt(a.http_seconds)}s</td><td>${esc(a.outcome)}</td></tr>`).join('');if(timer&&elapsed>=end){clearInterval(timer);timer=null;$('replay').textContent='▶ Replay'}}
function comparison(){if(!current){$('comparison').innerHTML='<p class="empty">Matching experiments will appear here.</p>';return}const matching=filtered().filter(r=>r.signature===current.signature);$('comparison').innerHTML='<div class="comparison-row comparison-head"><span>Strategy</span><span>Completed / requested</span><span class="count">Attempts</span><span class="count">429s</span></div>'+['burst','retry','paced'].map(s=>{const r=matching.find(r=>r.scenario===s);return `<div class="comparison-row ${r?.id===current.id?'current':''}"><span>${names[s]}</span><div>${r?`<div class="bar-track"><div class="bar-fill" style="width:${Math.min(100,100*r.summary.completed_responses/r.count)}%"></div></div><small>${r.summary.completed_responses} / ${r.count}</small>`:'<span class="muted small">No matching run</span>'}</div><span class="count">${r?r.summary.http_attempts:'—'}</span><span class="count">${r?r.summary.http_429:'—'}</span></div>`}).join('')}
for(const id of ['runtime','target','source'])$(id).addEventListener('change',()=>{ $('status').textContent=''; histories(); syncControls(); });
$('history').addEventListener('change',()=>choose($('history').value));
$('refresh').onclick=()=>load(current?.id);
$('presentation').onclick=()=>{document.body.classList.toggle('present');$('presentation').textContent=document.body.classList.contains('present')?'Exit presentation':'Presentation mode'};
$('replay').onclick=()=>{if(busy||loading||!current)return;if(timer){stop();draw();return}elapsed=0;$('replay').textContent='■ End replay';let last=performance.now();timer=setInterval(()=>{const now=performance.now();elapsed+=(now-last)/1000*Number($('speed').value);last=now;draw()},50);draw()};
$('run').onclick=async()=>{
    if(busy||loading||!ready||$('source').value==='LIVE_AZURE')return;
    stop(); draw(); busy=true; syncControls();
    $('status').textContent='Running the local CLI… Results appear when the experiment finishes.';
    const runtime=$('runtime').value,target=$('target').value==='azure_openai'?'aoai':'mai',scenario=$('scenario').value;
    try {
        const data=await requestJson('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({runtime,target,scenario})},190000);
        all=data.runs;
        histories();
        $('status').textContent='Simulation finished. Replay the evidence or compare strategies.';
    } catch(error) { $('status').textContent=error.message; }
    finally { busy=false; syncControls(); }
};

// Portal shell navigation: all commands operate on the existing local console.
document.querySelector('.controls').id = 'experiment';
document.querySelector('.compare').id = 'comparison-panel';
document.querySelector('.logs').id = 'attempt-log';
$('command-new').onclick = () => {
    $('experiment').scrollIntoView({behavior:'smooth', block:'start'});
    $('runtime').focus({preventScroll:true});
};
$('command-refresh').onclick = () => $('refresh').click();
$('command-compare').onclick = () => $('comparison-panel').scrollIntoView({behavior:'smooth'});
for (const id of ['nav-logs','tab-logs']) {
    $(id).addEventListener('click', () => { $('attempt-log').open = true; });
}
for (const link of document.querySelectorAll('.portal-nav a[href^="#"], .blade-tabs a')) {
    link.addEventListener('click', () => {
        const href = link.getAttribute('href');
        document.querySelectorAll('.portal-nav a[href^="#"]').forEach(item => {
            const active = item.getAttribute('href') === href;
            item.classList.toggle('active', active);
            if (active) item.setAttribute('aria-current','location');
            else item.removeAttribute('aria-current');
        });
        document.querySelectorAll('.blade-tabs a').forEach(item => item.classList.toggle('selected',item.getAttribute('href')===href));
    });
}

function recordedControls(recorded, recordings) {
    // Strategy configures a future mock run; it never changes recorded evidence.
    $('scenario').hidden = recorded;
    $('scenario').disabled = recorded;
    document.querySelector('label[for="scenario"]').hidden = recorded;
    $('run').hidden = recorded;
    document.querySelector('label[for="history"]').textContent = recorded ? 'Available Azure recordings' : 'Saved execution';
    $('history').disabled = recordings.length === 0;
    if (recorded) {
        const strategies = [...new Set(recordings.map(run => names[run.scenario] || run.scenario))];
        $('status').textContent = recordings.length
            ? `Available recorded scenarios: ${strategies.join(', ')}. Select a recording, then press Replay. Other strategies require a separately collected run.`
            : 'No Azure recordings exist for this runtime and model. Select another combination or use the local simulator.';
    }
}

render();
load();
