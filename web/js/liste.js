// Oturumlar ve Oylamalar listeleri: süzgeç çipleri ve metin süzgeci (satırlarda data-f ve data-q).
import { katla, okunanlar } from './ortak.js';

const $ = id => document.getElementById(id);
const satirlar = [...document.querySelectorAll('.liste > .satir[data-q]')];
const ok = okunanlar();
satirlar.forEach(s => { s.dataset.q = katla(s.dataset.q); if (!ok[s.dataset.id]) s.classList.add('yeni'); });
let filtre = '';
function suz() {
  const q = katla($('suz')?.value.trim() || '');
  satirlar.forEach(s => {
    s.hidden = !((!filtre || (s.dataset.f || '').split(' ').includes(filtre)) && (!q || q.split(/\s+/).every(w => s.dataset.q.includes(w))));
  });
  document.querySelectorAll('[data-grup]').forEach(g => {
    g.hidden = ![...g.querySelectorAll('.satir[data-q]')].some(s => !s.hidden);
  });
  const n = satirlar.filter(s => !s.hidden).length;
  if ($('sayac')) $('sayac').textContent = `${n} kayıt`;
}
document.querySelectorAll('#filtre button').forEach(b => b.onclick = () => {
  filtre = b.dataset.v; document.querySelectorAll('#filtre button').forEach(x => x.setAttribute('aria-pressed', x === b)); suz();
});
if ($('suz')) $('suz').oninput = suz;
suz();
