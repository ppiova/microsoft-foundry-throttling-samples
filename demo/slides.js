'use strict';
const slides = [...document.querySelectorAll('.slide')];
const previous = document.getElementById('previous');
const next = document.getElementById('next');
const jump = document.getElementById('jump');
let position = 0;
slides.forEach((slide,index) => {const option=document.createElement('option');option.value=index;option.textContent=`${index+1}`;jump.append(option);});
function show(index, updateHash=true) {
  position=Math.max(0,Math.min(slides.length-1,index));
  slides.forEach((slide,i)=>{slide.hidden=i!==position;});
  previous.disabled=position===0;next.disabled=position===slides.length-1;
  jump.value=position;
  document.getElementById('counter').textContent=`${position+1} / ${slides.length}`;
  document.title=`${position+1}. ${slides[position].querySelector('h1,h2').innerText.replace(/\s+/g,' ')} | Foundry Lab`;
  if(updateHash) history.replaceState(null,'',`#slide-${position+1}`);
  window.scrollTo({top:0,behavior:'instant'});
}
function fromHash(){const match=location.hash.match(/^#slide-(\d+)$/);show(match?Number(match[1])-1:0,false);}
async function fullscreen(){try {if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();}catch{document.getElementById('fullscreen').textContent='Use your browser full screen';}}
previous.onclick=()=>show(position-1);next.onclick=()=>show(position+1);
jump.onchange=()=>show(Number(jump.value));
document.getElementById('fullscreen').onclick=fullscreen;
document.addEventListener('fullscreenchange',()=>{document.getElementById('fullscreen').textContent=document.fullscreenElement?'Exit full screen':'Full screen';});
window.addEventListener('hashchange',fromHash);
document.addEventListener('keydown',event=>{
  if(event.altKey||event.ctrlKey||event.metaKey||/^(INPUT|SELECT|TEXTAREA)$/.test(event.target.tagName))return;
  if(event.key===' ' && /^(BUTTON|A)$/.test(event.target.tagName))return;
  if(['ArrowRight','PageDown',' '].includes(event.key)){event.preventDefault();show(position+1);}
  else if(['ArrowLeft','PageUp'].includes(event.key)){event.preventDefault();show(position-1);}
  else if(event.key==='Home'){event.preventDefault();show(0);}
  else if(event.key==='End'){event.preventDefault();show(slides.length-1);}
  else if(event.key.toLowerCase()==='f')fullscreen();
});
fromHash();
