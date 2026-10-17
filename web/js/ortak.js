// Ortak modül: cihazdaki tercihler, okundu işaretleri, Türkçe metin yardımcıları, veri ve kelime dizini,
// akış eşleştirmesi, "Takip et" düğmeleri, alt sayfa, kısa bildirim, service worker.

// ---------- Depolama (her erişim try/catch: gizli pencerede ya da kapalı depolamada da çalışsın) ----------
const oku = (k, v) => { try { const x = localStorage.getItem(k); return x === null ? v : JSON.parse(x); } catch (_) { return v; } };
const yaz = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); return true; } catch (_) { return false; } };

export const VARSAYILAN = {
  surum: 1, iller: [], mv: [], parti: [], kelime: [], konular: [],
  turler: { oylama: true, ozet: true, konusma: false, teklif: false },
  ritim: 'gunluk', sessiz: { bas: '23:00', bit: '08:00' },
  tamamlandi: null, atlandi: false, guncelleme: null,
};
export function tercih() {
  const t = oku('tbmm-tercih', null);
  return t ? { ...VARSAYILAN, ...t, turler: { ...VARSAYILAN.turler, ...(t.turler || {}) }, sessiz: { ...VARSAYILAN.sessiz, ...(t.sessiz || {}) } } : null;
}
export function tercihKaydet(t) {
  t.guncelleme = Date.now();
  yaz('tbmm-tercih', t);
  window.dispatchEvent(new CustomEvent('tercih-degisti'));
}
export const tercihVarMi = () => oku('tbmm-tercih', null) !== null;
export const takipSayisi = t => t ? t.iller.length + t.mv.length + t.parti.length + t.kelime.length + t.konular.length : 0;

/** Depolama kapalıysa (ör. bazı gizli pencereler) ilk açılış ekranına yönlendirme döngüsü kurulmasın */
export function depolamaVar() { try { localStorage.setItem('tbmm-dene', '1'); localStorage.removeItem('tbmm-dene'); return true; } catch (_) { return false; } }

export const okunanlar = () => oku('tbmm-okundu', {});
export function okundu(id) { const o = okunanlar(); o[id] = Date.now(); yaz('tbmm-okundu', o); }

// ---------- Türkçe metin ----------
export const kucuk = s => String(s ?? '').replace(/I/g, 'ı').replace(/İ/g, 'i').toLocaleLowerCase('tr');
export const norm = s => kucuk(s).replace(/â/g, 'a').replace(/î/g, 'i').replace(/û/g, 'u');
const ASCII = { 'ç': 'c', 'ğ': 'g', 'ı': 'i', 'ö': 'o', 'ş': 's', 'ü': 'u' };
/** Aksan katlama: "ozgur ozel" → "Özgür Özel" ile eşleşsin */
export const katla = s => norm(s).replace(/[çğıöşü]/g, c => ASCII[c]);
export const sirala = new Intl.Collator('tr').compare;
/** Sayfa adları için kısa ad; Python'daki arayuz.slug ile birebir aynı sonucu verir */
const SL = { 'Ç': 'C', 'Ğ': 'G', 'İ': 'I', 'Ö': 'O', 'Ş': 'S', 'Ü': 'U', 'Â': 'A', 'Î': 'I', 'Û': 'U', 'ç': 'c', 'ğ': 'g', 'ı': 'i', 'ö': 'o', 'ş': 's', 'ü': 'u', 'â': 'a', 'î': 'i', 'û': 'u' };
export const slug = s => String(s).replace(/[ÇĞİÖŞÜÂÎÛçğıöşüâîû]/g, c => SL[c]).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
export const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const TARIH = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'long', year: 'numeric', weekday: 'long' });
const KISA = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'long' });
const gunIso = d => d.toISOString().slice(0, 10);
export function tarihYaz(iso) { return TARIH.format(new Date(iso + 'T12:00:00')); }
export function kisaTarih(iso) { return KISA.format(new Date(iso + 'T12:00:00')); }
export function gunEtiketi(iso) {
  const bugun = new Date(); const dun = new Date(Date.now() - 864e5);
  if (iso === gunIso(bugun)) return 'Bugün';
  if (iso === gunIso(dun)) return 'Dün';
  return tarihYaz(iso);
}
/** TDK: saat ile dakika arasına nokta (22.31) */
export const saatYaz = s => s ? s.replace(':', '.') : '';
export const sayi = n => new Intl.NumberFormat('tr-TR').format(n);

// ---------- Veri ----------
let _veri = null;
export function veri() {
  return _veri ||= fetch('veri/akis.json').then(r => { if (!r.ok) throw new Error('veri'); return r.json(); })
    .then(d => {
      d.mvIndex = Object.fromEntries(d.mv.map((m, i) => [m[0], i]));
      d.konuMap = Object.fromEntries(d.konular.map(([k, ad, kelimeler]) => [k, { ad, kelimeler }]));
      return d;
    });
}

const _parca = {};
const parcaYukle = (k, surum) => _parca[k] ||= fetch(`veri/kelime/${encodeURIComponent(k)}.json?v=${surum}`)
  .then(r => r.ok ? r.json() : {}).catch(() => ({}));
const _eslesme = {};
/** Bir ifadedeki tüm kelimelerin (kelime başı, aksan katlamalı) geçtiği kayıtların sıra numaraları */
export async function kelimeEsles(ifade, surum) {
  const anahtar = katla(ifade);
  if (_eslesme[anahtar]) return _eslesme[anahtar];
  const ws = (anahtar.match(/[a-z0-9]+/g) || []).filter(w => w.length >= 3);
  let sonuc = null;
  for (const w of ws) {
    const p = await parcaYukle(w.slice(0, 2), surum);
    const s = new Set();
    for (const [tok, ids] of Object.entries(p)) if (katla(tok).startsWith(w)) ids.forEach(i => s.add(i));
    sonuc = sonuc ? new Set([...sonuc].filter(x => s.has(x))) : s;
  }
  return (_eslesme[anahtar] = sonuc || new Set());
}

// ---------- Akış eşleştirmesi ----------
const OY = { K: 'Kabul', R: 'Ret', C: 'Çekimser', X: 'Katılmadı' };
export const dagilim = a => ['kabul', 'ret', 'çekimser', 'katılmadı'].map((l, i) => a[i] ? `${a[i]} ${l}` : '').filter(Boolean).join(' · ');

/** Her kayıt için "neden görüyorum" gerekçeleri; takip yoksa null döner (genel akış) */
export async function eslestir(d, t) {
  if (!t || !takipSayisi(t)) return null;
  const kelimeler = [...t.kelime.map(k => [k, `“${k}”`]),
    ...t.konular.flatMap(k => (d.konuMap[k]?.kelimeler || []).map(w => [w, d.konuMap[k].ad]))];
  const kelimeSet = [];
  for (const [w, etiket] of kelimeler) kelimeSet.push([await kelimeEsles(w, d.surum), etiket]);
  const sonuc = new Map();
  d.ogeler.forEach((o, idx) => {
    const n = [];
    if (o.t === 'T' && !(t.turler.ozet || t.turler.konusma)) return;
    if (o.t === 'O' && !t.turler.oylama) return;
    for (const id of t.mv) {
      const i = d.mvIndex[id]; if (i === undefined) continue;
      const ad = d.mv[i][1];
      if (o.t === 'T' && o.k[i]) n.push({ m: `<b>${esc(ad)}</b> konuştu (${o.k[i][0]})`, u: `${o.p}#konusmaci=${o.k[i][1]}` });
      if (o.t === 'O' && o.v[i] && o.v[i] !== '-') n.push({ m: `<b>${esc(ad)}</b>: ${OY[o.v[i]]}` });
    }
    for (const il of t.iller) {
      if (o.t === 'T' && o.ik[il]) n.push({ m: `${esc(il)}: ${o.ik[il]} konuşmacı` });
      if (o.t === 'O' && o.iv[il]) n.push({ m: `${esc(il)}: ${dagilim(o.iv[il])}` });
    }
    for (const p of t.parti) {
      if (o.t === 'T' && o.pk[p]) n.push({ m: `${esc(p)}: ${o.pk[p]} konuşmacı` });
      if (o.t === 'O' && o.pv[p]) n.push({ m: `${esc(p)}: ${dagilim(o.pv[p])}` });
    }
    const goruldu = new Set();
    for (const [s, etiket] of kelimeSet) if (s.has(idx) && !goruldu.has(etiket)) { goruldu.add(etiket); n.push({ m: `${esc(etiket)} geçiyor` }); }
    if (n.length) sonuc.set(idx, n);
  });
  return sonuc;
}

// ---------- Satır görünümü (akış ve arama) ----------
const OY_TURLERI = [['k', 'Kabul', '✓'], ['r', 'Ret', '✕'], ['c', 'Çekimser', '–'], ['x', 'Katılmadı', '·']];
export function sayimHTML(to, ince = true) {
  const dilim = OY_TURLERI.map(([c, ad], i) => to[i] ? `<i class="${c}" style="flex:${to[i]}" title="${ad}: ${to[i]}"></i>` : '').join('');
  const ozet = OY_TURLERI.map(([, ad], i) => to[i] ? `${ad} ${to[i]}` : '').filter(Boolean).join(', ');
  const yazi = OY_TURLERI.map(([c, ad, isaret], i) => (to[i] || i < 2)
    ? `<span><span class="isaret ${c}" aria-hidden="true">${isaret}</span>${ad} <b>${to[i] || 0}</b></span>` : '').join('');
  return `<div class="sayim${ince ? ' ince' : ''}" role="img" aria-label="${ozet}">${dilim}</div><div class="sayilar" aria-hidden="true">${yazi}</div>`;
}
const durumEtiketi = du => /^bas/i.test(du) ? '<span class="etiket kesin">Basılmış</span>'
  : /^tam/i.test(du) ? '<span class="etiket kesin">Tam tutanak</span>' : '<span class="etiket ham">Ham tutanak</span>';

export function satirHTML(o, nedenler, okundu, { ozetGoster = true } = {}) {
  const yeni = !okundu[o.id];
  let ust, govde = '';
  if (o.t === 'O') {
    ust = `<span class="tur">Oylama</span><span>${o.bn}. Birleşim${o.s ? ' · ' + saatYaz(o.s) : ''}</span>`;
    govde = `<p class="govde" style="-webkit-line-clamp:1">${esc(o.so || '')}</p>${sayimHTML(o.to)}`
      + (ozetGoster && o.l ? `<p class="govde" style="-webkit-line-clamp:2">${esc(o.l)}</p>` : '');
  } else {
    ust = `<span class="tur">Tutanak</span><span>${o.bn}. Birleşim</span>${durumEtiketi(o.du)}`;
    govde = `<div class="bilgi" style="margin-top:6px">${o.ko} konuşmacı${o.n ? ` · ${o.n} açık oylama` : ''}</div>`;
  }
  // Tutanakta başlık, o gün alınan son karardır (TBMM özetinden, değiştirilmeden)
  const baslik = o.t === 'O' ? esc(o.b) : (o.l ? esc(o.l) : 'Genel Kurul toplandı');
  const neden = nedenler?.length
    ? `<div class="neden"><span class="gizli-metin">Akışınızda olma nedeni:</span>${nedenler.slice(0, 6).map(n => n.u ? `<a href="${n.u}">${n.m}</a>` : `<span>${n.m}</span>`).join('')}${nedenler.length > 6 ? `<span>+${nedenler.length - 6}</span>` : ''}</div>` : '';
  return `<li class="satir${yeni ? ' yeni' : ''}"><a href="${o.p}"><div class="bilgi">${ust}${yeni ? '<span class="gizli-metin">okunmadı</span>' : ''}</div><h3>${baslik}</h3>${govde}</a>${neden}</li>`;
}

// ---------- Takip düğmeleri: data-tur (mv|parti|il|kelime|konu) + data-id ----------
const ALAN = { mv: 'mv', parti: 'parti', il: 'iller', kelime: 'kelime', konu: 'konular' };
export function takipteMi(tur, id) { const t = tercih(); return !!t && t[ALAN[tur]].includes(id); }
export function takipDegistir(tur, id) {
  const t = tercih() || { ...VARSAYILAN, turler: { ...VARSAYILAN.turler }, sessiz: { ...VARSAYILAN.sessiz } };
  const liste = t[ALAN[tur]]; const i = liste.indexOf(id);
  i < 0 ? liste.push(id) : liste.splice(i, 1);
  tercihKaydet(t);
  return i < 0;
}
function takipDugmeleri() {
  document.querySelectorAll('.takip-dugme').forEach(b => {
    const guncelle = () => {
      const on = takipteMi(b.dataset.tur, b.dataset.id);
      b.setAttribute('aria-pressed', on); b.textContent = on ? 'Takip ediliyor' : 'Takip et';
    };
    guncelle();
    b.onclick = () => {
      const on = takipDegistir(b.dataset.tur, b.dataset.id);
      guncelle();
      toast(on ? 'Takip listenize eklendi. Bu cihazda saklanır.' : 'Takip listenizden çıkarıldı.');
    };
  });
}

// ---------- Kısa bildirim ve kopyalama ----------
let _toastZaman;
export function toast(mesaj) {
  let t = document.querySelector('.toast');
  if (!t) { t = document.createElement('div'); t.className = 'toast'; t.setAttribute('role', 'status'); document.body.append(t); }
  t.textContent = mesaj; t.hidden = false;
  clearTimeout(_toastZaman); _toastZaman = setTimeout(() => { t.hidden = true; }, 3200);
}
document.addEventListener('click', async e => {
  const b = e.target.closest('[data-kopyala]'); if (!b) return;
  try { await navigator.clipboard.writeText(b.dataset.kopyala); toast('Kaynak gösterimi kopyalandı.'); }
  catch (_) { toast('Kopyalanamadı.'); }
});

// ---------- Alt sayfa: geri tuşu/hareketi kapatır, odak açan düğmeye döner ----------
export function altSayfa(dialog, acan) {
  dialog.showModal();
  history.pushState({ altSayfa: true }, '');
  const kapat = () => { if (dialog.open) dialog.close(); };
  const geri = () => kapat();
  window.addEventListener('popstate', geri, { once: true });
  dialog.addEventListener('close', () => {
    window.removeEventListener('popstate', geri);
    if (history.state?.altSayfa) history.back();
    acan?.focus();
  }, { once: true });
  dialog.querySelectorAll('[data-kapat]').forEach(b => b.onclick = kapat);
  dialog.onclick = e => { if (e.target === dialog) kapat(); };
}

// ---------- Platform ----------
export const kurulu = () => matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
export const ios = () => /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
export let yuklemeOlayi = null;
addEventListener('beforeinstallprompt', e => { e.preventDefault(); yuklemeOlayi = e; window.dispatchEvent(new Event('yuklenebilir')); });
addEventListener('appinstalled', () => { yuklemeOlayi = null; });

// ---------- Service worker ve çevrimdışı durumu ----------
if ('serviceWorker' in navigator && location.protocol.startsWith('http')) navigator.serviceWorker.register('sw.js').catch(() => {});
function cevrimDurumu() {
  let c = document.getElementById('cevrimdisi');
  if (navigator.onLine) { c?.remove(); return; }
  if (!c) {
    c = document.createElement('p'); c.id = 'cevrimdisi'; c.className = 'kap';
    c.innerHTML = '<span class="etiket cizgili">Çevrimdışı · daha önce açtığınız sayfalar okunabilir</span>';
    document.getElementById('ana')?.prepend(c);
  }
}
addEventListener('online', cevrimDurumu); addEventListener('offline', cevrimDurumu);

cevrimDurumu();
takipDugmeleri();
window.addEventListener('tercih-degisti', takipDugmeleri);
