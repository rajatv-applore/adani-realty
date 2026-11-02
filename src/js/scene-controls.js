/* ============================================================
   4c. SCENE CONTROLS, floor explorer, camera presets, reveal, evening
   ============================================================ */
(function(){
  const floorNav=$("#floorNav"),viewPresets=$("#viewPresets"),revealBtn=$("#revealBtn"),eveningBtn=$("#eveningBtn");
  const fnBtns=[...floorNav.querySelectorAll(".fn-btn")],vpBtns=[...viewPresets.querySelectorAll(".vp-btn")];
  const fullBtn=floorNav.querySelector(".fn-full");
  const evLabel=[...eveningBtn.childNodes].find(n=>n.nodeType===3);
  function setFloorActive(floor){fnBtns.forEach(b=>b.classList.toggle("active",b.dataset.floor===floor&&floor!==""));fullBtn.disabled=!floor;$("#sceneWrap").classList.toggle("floor-mode",!!floor);}
  function setViewActive(v){vpBtns.forEach(b=>b.classList.toggle("active",b.dataset.view===v));}
  function clearReveal(){revealBtn.setAttribute("aria-pressed","false");}
  fnBtns.forEach(b=>b.addEventListener("click",()=>{if(!scene3d)return;const f=b.dataset.floor;closeZone();clearReveal();
    if(f){scene3d.explodeFloor(f);setFloorActive(f);setViewActive("");}else{scene3d.fullVilla();setFloorActive("");setViewActive("overall");}}));
  vpBtns.forEach(b=>b.addEventListener("click",()=>{if(!scene3d)return;const v=b.dataset.view;closeZone();clearReveal();scene3d.goTo(v);setViewActive(v);setFloorActive("");}));
  revealBtn.addEventListener("click",()=>{if(!scene3d)return;const on=revealBtn.getAttribute("aria-pressed")!=="true";revealBtn.setAttribute("aria-pressed",String(on));if(on){setFloorActive("");}scene3d.setReveal(on);});
  eveningBtn.addEventListener("click",()=>{if(!scene3d)return;const on=eveningBtn.getAttribute("aria-pressed")!=="true";eveningBtn.setAttribute("aria-pressed",String(on));if(evLabel)evLabel.nodeValue=on?"Day":"Evening";scene3d.setEvening(on);});
  window.__resetControls=function(){setFloorActive("");setViewActive("overall");clearReveal();};
})();

