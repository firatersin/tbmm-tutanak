// Ara sekmesi: milletvekilleri, oylamalar ve tutanaklarda arama (tam metin dizini, aksan katlamalı).
import { veri, katla, esc, kelimeEsles, satirHTML, okunanlar } from './ortak.js';

const $ = id => document.getElementById(id);
const SON = 'tbmm-son-aramalar';
let d, kapsam = '', zaman, sonSorgu = '';
const sonAramalar = () => { try { return JSON.parse(localStorage.getItem(SON) || '[]'); } catch (_) { return []; } };
const sonKaydet = l => { try { localStorage.setItem(SON, JSON.stringify(l.slice(0, 8))); } catch (_) {} };

function sonlariGoster() {
  const l = sonAramalar();
  $('son').hidden = !l.length || !!$('q').value.trim();
  $('son-liste').innerHTML = l.map(q => `<li style="display:flex;justify-content:space-between;border-bottom:1px solid var(--cizgi)">
    <button class="dugme yalin" data-ara="${esc(q)}" style="text-decoration:none;color:var(--murekkep)">${esc(q)}</button>
    <button class="dugme yalin" data-sil="${esc(q)}" aria-label="${esc(q)} aramasını sil">×</button></li>`).join('');
}

async function ara() {
  const q = $('q').value.trim();
  history.replaceState(null, '', q ? `?q=${encodeURIComponent(q)}` : location.pathname);
  sonlariGoster();
  if (q.length < 2) { $('sonuc').innerHTML = ''; $('kapsam').hidden = true; return; }
  sonSorgu = q;
  const k = katla(q);
  const mv = d.mv.filter(m => katla(`${m[1]} ${m[2]} ${m[3]}`).includes(k)).slice(0, 50);
  const ids = k.replace(/[^a-z0-9]/g, '').length >= 3 ? await kelimeEsles(q, d.surum) : new Set();
  if (q !== sonSorgu) return;
  const oy = [], tu = [];
  for (let i = d.ogeler.length - 1; i >= 0; i--) {
    const o = d.ogeler[i];
    if (o.t === 'O' && (ids.has(i) || katla(o.b).includes(k))) oy.push(o);
    if (o.t === 'T' && ids.has(i)) tu.push(o);
  }
  const sayilar = { '': mv.length + oy.length + tu.length, mv: mv.length, O: oy.length, T: tu.length };
  document.querySelectorAll('#kapsam button').forEach(b => { b.querySelector('.say').textContent = sayilar[b.dataset.v]; });
  $('kapsam').hidden = false;
  const ok = okunanlar();
  const bolum = (baslik, html, n) => n ? `<section class="bolum"><h2>${baslik} <span class="say">(${n})</span></h2><ul class="liste">${html}</ul></section>` : '';
  const mvHtml = mv.map(m => `<li class="satir"><a href="mv-${m[0]}.html"><div class="bilgi"><span class="tur">Milletvekili</span><span>${esc(m[2])} · ${esc(m[3])}</span></div><h3>${esc(m[1])}</h3></a></li>`).join('');
  const kes = l => l.slice(0, 60).map(o => satirHTML(o, null, ok)).join('');
  let html = '';
  if (!kapsam || kapsam === 'mv') html += bolum('Milletvekilleri', mvHtml, mv.length);
  if (!kapsam || kapsam === 'O') html += bolum('Oylamalar', kes(oy), oy.length);
  if (!kapsam || kapsam === 'T') html += bolum('Tutanaklar', kes(tu), tu.length);
  $('sonuc').innerHTML = html || `<div class="bos"><h2>“${esc(q)}” için sonuç yok</h2><p>Yazımı kontrol edin ya da daha kısa bir kelime deneyin. Arama Türkçe karakterlere duyarlı değildir.</p></div>`;
  if (sayilar[''] && !sonAramalar().includes(q)) sonKaydet([q, ...sonAramalar()]);
}

$('q').oninput = () => { clearTimeout(zaman); zaman = setTimeout(ara, 250); };
$('ara-form').onsubmit = e => { e.preventDefault(); clearTimeout(zaman); ara(); $('q').blur(); };
document.querySelectorAll('#kapsam button').forEach(b => b.onclick = () => {
  kapsam = b.dataset.v;
  document.querySelectorAll('#kapsam button').forEach(x => x.setAttribute('aria-pressed', x === b));
  ara();
});
$('son').onclick = e => {
  const a = e.target.closest('[data-ara]'); if (a) { $('q').value = a.dataset.ara; ara(); return; }
  const s = e.target.closest('[data-sil]'); if (s) { sonKaydet(sonAramalar().filter(x => x !== s.dataset.sil)); sonlariGoster(); }
};

(async () => {
  try { d = await veri(); } catch (_) { $('sonuc').innerHTML = '<div class="bos"><h2>Arama dizini yüklenemedi</h2><p>Bağlantınızı kontrol edin.</p></div>'; return; }
  const q = new URLSearchParams(location.search).get('q');
  if (q) { $('q').value = q; ara(); } else sonlariGoster();
})();
