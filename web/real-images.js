document.addEventListener('DOMContentLoaded',()=>setTimeout(()=>{
  const style=document.createElement('style');
  style.textContent='.photo-hero{background:linear-gradient(90deg,#07111ff4 0%,#07111dcc 50%,#07111d88 100%),url("https://images.unsplash.com/photo-1511512578047-dfb367046420?auto=format&fit=crop&w=1600&q=82") center/cover}.photo-card{position:relative;background-position:center;background-size:cover;isolation:isolate}.photo-card::before{content:"";position:absolute;inset:0;z-index:-1;background:linear-gradient(160deg,#07111db8 5%,#07111fee 88%)}.photo-card>*{position:relative}.photo-fivem{background-image:url("https://images.unsplash.com/photo-1555066931-4365d14bab8c?auto=format&fit=crop&w=900&q=80")}.photo-security{background-image:url("https://images.unsplash.com/photo-1517245386807-bb43f82c33c4?auto=format&fit=crop&w=900&q=80")}.photo-obfuscator{background-image:url("https://images.unsplash.com/photo-1550745165-9bc0b252726f?auto=format&fit=crop&w=900&q=80")}';
  document.head.appendChild(style);
  const hero=document.querySelector('.hero');
  if(hero) hero.classList.add('photo-hero');
  document.querySelectorAll('.card').forEach(card=>{
    const href=card.getAttribute('href')||'';
    if(href.includes('fivem')) card.classList.add('photo-card','photo-fivem');
    if(href.includes('security')) card.classList.add('photo-card','photo-security');
    if(href.includes('obfuscator')) card.classList.add('photo-card','photo-obfuscator');
  });
},120));
