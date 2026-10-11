(function(){
  var seen={},out=[],U=location.href;
  function img(el){var i=el.querySelectorAll('img');for(var k=0;k<i.length;k++){var s=i[k].currentSrc||i[k].src||i[k].getAttribute('data-src')||'';var m=s.match(/item_image\/([0-9a-f-]{36})/);if(m)return m[1];}return '';}
  var pm=U.match(/\/marketplace\/product\/([0-9a-f-]{36})/);
  if(pm){var h=document.querySelector('h1');out.push([pm[1],img(document.body),(h?h.innerText:'').trim()].join('|'));seen[pm[1]]=1;}
  var as=document.querySelectorAll('a[href*="/marketplace/product/"]');
  for(var j=0;j<as.length;j++){
    var m=as[j].href.match(/product\/([0-9a-f-]{36})/);if(!m||seen[m[1]])continue;
    var c=as[j],im='',n=0;while(c&&n<7&&!(im=img(c))){c=c.parentElement;n++;}
    var t=((c||as[j]).innerText||'').replace(/\s+/g,' ').trim().slice(0,220);
    seen[m[1]]=1;out.push([m[1],im,t].join('|'));
  }
  var txt='PAGINA: '+U+'\n'+out.join('\n');
  var d=document.createElement('div');d.style.cssText='position:fixed;inset:0;z-index:2147483647;background:#fff;padding:12px;font:14px sans-serif';
  d.innerHTML='<b>'+out.length+' prodotti trovati.</b> Tocca COPIA e incolla in chat. <button id="xcp" style="font-size:16px;padding:6px 12px">COPIA</button> <button id="xcl" style="font-size:16px;padding:6px 12px">Chiudi</button><textarea id="xta" style="width:100%;height:80%;margin-top:8px;font-size:11px"></textarea>';
  document.body.appendChild(d);var ta=d.querySelector('#xta');ta.value=txt;
  d.querySelector('#xcp').onclick=function(){ta.focus();ta.select();ta.setSelectionRange(0,txt.length);try{navigator.clipboard.writeText(txt);}catch(e){document.execCommand('copy');}this.innerText='COPIATO ✓';};
  d.querySelector('#xcl').onclick=function(){d.remove();};
})();
