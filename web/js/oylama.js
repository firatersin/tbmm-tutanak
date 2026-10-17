// Oylama sayfası: parti satırına dokununca o partiden kimin ne oy verdiği; milletvekili listesi süzgeçleri; CSV.
import { okundu, tercih, katla, esc } from './ortak.js';

const $ = id => document.getElementById(id);
const V = JSON.parse($('oylama-veri').textContent);   // { id, baslik, oylar: [[ad, il, parti, oy, mvId], ...] }
okundu(V.id);
const OY = [['KABUL', 'Kabul', '✓'], ['RET', 'Ret', '✕'], ['ÇEKİMSER', 'Çekimser', '–'], ['KATILMADI', 'Katılmadı', '·']];

// ---------- Partilere göre: satıra dokununca isimler ----------
document.querySelectorAll('.parti-satir').forEach(b => {
  b.onclick = () => {
    const acik = b.getAttribute('aria-expanded') === 'true';
    const hedef = document.getElementById(b.getAttribute('aria-controls'));
    if (!acik && !hedef.dataset.dolu) {
      const kisiler = V.oylar.filter(o => o[2] === b.dataset.parti);
      hedef.innerHTML = OY.map(([k, ad, isaret]) => {
        const l = kisiler.filter(o => o[3] === k); if (!l.length) return '';
        return `<h4>${isaret} ${ad} (${l.length})</h4><ul>${l.map(o => `<li><a href="mv-${o[4]}.html">${esc(o[0])}</a> <small>${esc(o[1])}</small></li>`).join('')}</ul>`;
      }).join('');
      hedef.dataset.dolu = '1';
    }
    b.setAttribute('aria-expanded', !acik); hedef.hidden = acik;
  };
});

// ---------- Milletvekilleri listesi ----------
const takipte = new Set(tercih()?.mv || []);
const satirlar = [...document.querySelectorAll('#mv-liste tbody tr')];
satirlar.forEach(tr => {
  tr.dataset.q = katla(tr.textContent);
  if (takipte.has(tr.dataset.mv)) { tr.classList.add('takipte'); tr.parentNode.prepend(tr); }
});
let oy = '', parti = '';
function suz() {
  const q = katla($('mv-ara').value.trim()); let n = 0;
  satirlar.forEach(tr => {
    const g = (!oy || tr.dataset.oy === oy) && (!parti || tr.dataset.parti === parti) && (!q || q.split(/\s+/).every(w => tr.dataset.q.includes(w)));
    tr.hidden = !g; if (g) n++;
  });
  $('mv-sayac').textContent = `${n} milletvekili gösteriliyor`;
}
document.querySelectorAll('#oy-segment button').forEach(b => b.onclick = () => {
  oy = b.dataset.v; document.querySelectorAll('#oy-segment button').forEach(x => x.setAttribute('aria-selected', x === b)); suz();
});
$('mv-ara').oninput = suz;
$('parti-sec').onchange = e => { parti = e.target.value; suz(); };
suz();

// ---------- CSV ----------
$('csv').onclick = () => {
  const satir = a => a.map(x => `"${String(x).replace(/"/g, '""')}"`).join(',');
  const metin = '﻿' + [satir(['Milletvekili', 'İl', 'Parti (oylama tarihinde)', 'Oy'])]
    .concat(V.oylar.map(o => satir([o[0], o[1], o[2], OY.find(x => x[0] === o[3])?.[1] || o[3]]))).join('\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([metin], { type: 'text/csv;charset=utf-8' }));
  a.download = `${V.id.replace(/[^a-z0-9-]/gi, '_')}.csv`; a.click(); URL.revokeObjectURL(a.href);
};
