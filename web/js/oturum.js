// Oturum sayfası: Özet / Tutanak / Oylamalar sekmeleri ve tutanak okuyucusunun araçları.
import { okundu, altSayfa } from './ortak.js';

const $ = id => document.getElementById(id);
const kok = document.documentElement;
const okunduId = document.querySelector('[data-okundu]')?.dataset.okundu;
if (okunduId) okundu(okunduId);

// ---------- Sekmeler (adres çubuğunda tutulur; geri tuşu çalışır) ----------
const sekmeler = [...document.querySelectorAll('[data-sekme]')];
function sekmeAc(ad, kaydir = true) {
  if (!document.getElementById('p-' + ad)) ad = 'ozet';
  sekmeler.forEach(b => b.setAttribute('aria-selected', b.dataset.sekme === ad));
  document.querySelectorAll('.panel').forEach(p => { p.hidden = p.id !== 'p-' + ad; });
  $('arac') && ($('arac').hidden = ad !== 'tutanak');
  if (kaydir) scrollTo({ top: 0 });
}
sekmeler.forEach(b => b.onclick = e => {
  e.preventDefault();
  history.pushState(null, '', '#' + b.dataset.sekme);
  sekmeAc(b.dataset.sekme);
});
function adrestenAc() {
  const h = location.hash.slice(1);
  if (h.startsWith('konusmaci=')) { sekmeAc('tutanak', false); konusmaciyaGit(h.split('=')[1]); return; }
  sekmeAc(['ozet', 'tutanak', 'oylamalar'].includes(h) ? h : 'ozet', false);
}
addEventListener('popstate', adrestenAc);

// ---------- Konuşmacıya atlama ----------
const sira = {};
function isikla(el) {
  el.scrollIntoView({ block: 'center', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
  el.classList.add('isik'); setTimeout(() => el.classList.remove('isik'), 1800);
}
function konusmaciyaGit(sid, sonraki = false) {
  const liste = [...document.querySelectorAll(`#metin p[data-s="${CSS.escape(sid)}"]`)];
  if (!liste.length) return;
  sira[sid] = sonraki ? ((sira[sid] ?? -1) + 1) % liste.length : 0;
  setTimeout(() => isikla(liste[sira[sid]]), 60);
  return `${sira[sid] + 1}/${liste.length}`;
}

// ---------- Araç çubuğu ----------
if ($('arac')) {
  const icindekiler = $('icindekiler'), konusmacilar = $('konusmacilar'), yazi = $('yazi');
  $('ac-icindekiler').onclick = e => altSayfa(icindekiler, e.currentTarget);
  $('ac-konusmacilar').onclick = e => altSayfa(konusmacilar, e.currentTarget);
  $('ac-yazi').onclick = e => altSayfa(yazi, e.currentTarget);
  icindekiler.addEventListener('click', e => {
    const a = e.target.closest('a[href^="#b"]'); if (!a) return;
    e.preventDefault(); icindekiler.close();
    const hedef = document.getElementById(a.getAttribute('href').slice(1));
    if (hedef) setTimeout(() => isikla(hedef), 80);
  });
  konusmacilar.addEventListener('click', e => {
    const b = e.target.closest('[data-s]'); if (!b) return;
    const sonuc = konusmaciyaGit(b.dataset.s, true);
    b.querySelector('em').textContent = sonuc;
    konusmacilar.close();
  });
  yazi.addEventListener('click', e => {
    const b = e.target.closest('[data-boyut]'); if (!b) return;
    kok.style.setProperty('--okuma', b.dataset.boyut + 'px');
    try { localStorage.setItem('tbmm-boyut', b.dataset.boyut); } catch (_) {}
    yazi.querySelectorAll('[data-boyut]').forEach(x => x.setAttribute('aria-selected', x === b));
  });
  let boyut = '18'; try { boyut = localStorage.getItem('tbmm-boyut') || '18'; } catch (_) {}
  yazi.querySelectorAll('[data-boyut]').forEach(x => x.setAttribute('aria-selected', x.dataset.boyut === boyut));

  // Metinde ara
  const kutu = $('ara-kutu'), q = $('q'), sayac = $('sayac');
  $('ac-ara').onclick = () => { kutu.hidden = !kutu.hidden; if (!kutu.hidden) q.focus(); else temizle(); };
  let isaretler = [], su = -1, zaman;
  const norm = s => s.replace(/I/g, 'ı').replace(/İ/g, 'i').toLocaleLowerCase('tr');
  function temizle() {
    isaretler.forEach(m => { const p = m.parentNode; p.replaceChild(document.createTextNode(m.textContent), m); p.normalize(); });
    isaretler = []; su = -1; sayac.textContent = '';
  }
  function ara() {
    temizle();
    const s = norm(q.value.trim()); if (s.length < 2) return;
    const w = document.createTreeWalker($('metin'), NodeFilter.SHOW_TEXT);
    const dugumler = []; while (w.nextNode()) dugumler.push(w.currentNode);
    for (const n of dugumler) {
      const m = n.textContent, l = norm(m); if (l.length !== m.length) continue;
      let i = l.indexOf(s); if (i < 0) continue;
      const f = document.createDocumentFragment(); let son = 0;
      while (i >= 0) { f.append(m.slice(son, i)); const k = document.createElement('mark'); k.textContent = m.slice(i, i + s.length); f.append(k); isaretler.push(k); son = i + s.length; i = l.indexOf(s, son); }
      f.append(m.slice(son)); n.parentNode.replaceChild(f, n);
    }
    sayac.textContent = isaretler.length ? '' : '0 sonuç';
    if (isaretler.length) git(1);
  }
  function git(yon) {
    if (!isaretler.length) return;
    if (su >= 0) isaretler[su].classList.remove('su-an');
    su = (su + yon + isaretler.length) % isaretler.length;
    isaretler[su].classList.add('su-an'); isaretler[su].scrollIntoView({ block: 'center' });
    sayac.textContent = `${su + 1} / ${isaretler.length}`;
  }
  q.oninput = () => { clearTimeout(zaman); zaman = setTimeout(ara, 250); };
  q.onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); git(e.shiftKey ? -1 : 1); } if (e.key === 'Escape') { kutu.hidden = true; temizle(); } };
  $('onceki').onclick = () => git(-1); $('sonraki').onclick = () => git(1);
}

// ---------- Başa dön (yaklaşık dört ekran sonra) ----------
const basa = $('basa-don');
if (basa) {
  addEventListener('scroll', () => { basa.hidden = scrollY < innerHeight * 4; }, { passive: true });
  basa.onclick = () => { scrollTo({ top: 0 }); document.querySelector('h1')?.focus({ preventScroll: true }); };
}

adrestenAc();
