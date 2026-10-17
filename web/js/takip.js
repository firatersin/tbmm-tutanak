// Takip sekmesi: takip listesi, bildirim planı, okuma tercihleri, uygulama, veriler ve hesap.
import { tercih, tercihKaydet, VARSAYILAN, veri, esc, slug, kurulu, ios, yuklemeOlayi, toast } from './ortak.js';

const $ = id => document.getElementById(id);
const kopya = o => JSON.parse(JSON.stringify(o));
let d, t = tercih() || kopya(VARSAYILAN);
const kaydet = mesaj => { tercihKaydet(t); if (mesaj) toast(mesaj); };

// ---------- Takip ettikleriniz ----------
function takipleriCiz() {
  const grup = (baslik, liste, satir) => liste.length
    ? `<h3 class="ust-etiket" style="margin:20px 0 0">${baslik}</h3><ul class="liste">${liste.map(satir).join('')}</ul>` : '';
  const kaldir = (tur, id) => `<button class="dugme yalin" data-kaldir="${tur}" data-id="${esc(id)}" aria-label="Takipten çıkar">Çıkar</button>`;
  const sat = (href, ad, alt, tur, id) => `<li class="satir" style="display:flex;justify-content:space-between;align-items:center;gap:10px;padding:8px 0">
    <a href="${href}" style="flex:1"><b style="font-weight:500">${esc(ad)}</b>${alt ? ` <small style="color:var(--murekkep-3)">${esc(alt)}</small>` : ''}</a>${kaldir(tur, id)}</li>`;
  const html =
    grup('İller', t.iller, il => sat(`il-${slug(il)}.html`, il, '', 'iller', il)) +
    grup('Milletvekilleri', t.mv, id => { const m = d.mv[d.mvIndex[id]]; return sat(`mv-${id}.html`, m ? m[1] : id, m ? `${m[2]} · ${m[3]}` : '', 'mv', id); }) +
    grup('Partiler', t.parti, p => sat(`parti-${slug(p)}.html`, p, '', 'parti', p)) +
    grup('Konular', t.konular, k => sat(`ara.html?q=${encodeURIComponent(d.konuMap[k]?.kelimeler[0] || k)}`, d.konuMap[k]?.ad || k, (d.konuMap[k]?.kelimeler || []).join(', '), 'konular', k)) +
    grup('Kelimeler', t.kelime, k => sat(`ara.html?q=${encodeURIComponent(k)}`, `“${k}”`, '', 'kelime', k));
  $('takipler').innerHTML = html || '<p class="not" style="padding:10px 0">Henüz hiçbir şeyi takip etmiyorsunuz. Akışınız tüm kayıtları gösteriyor.</p>';
}
$('takipler').onclick = e => {
  const b = e.target.closest('[data-kaldir]'); if (!b) return;
  const l = t[b.dataset.kaldir]; l.splice(l.indexOf(b.dataset.id), 1);
  kaydet('Takip listenizden çıkarıldı.'); takipleriCiz();
};

// ---------- Bildirim planı ----------
function planiCiz() {
  document.querySelectorAll('#plan [data-tur]').forEach(i => { i.checked = !!t.turler[i.dataset.tur]; });
  document.querySelectorAll('#plan [name="ritim"]').forEach(i => { i.checked = i.value === t.ritim; });
  $('sessiz-bas').value = t.sessiz.bas; $('sessiz-bit').value = t.sessiz.bit;
}
$('plan').onchange = e => {
  const el = e.target;
  if (el.dataset.tur) t.turler[el.dataset.tur] = el.checked;
  if (el.name === 'ritim') t.ritim = el.value;
  if (el.id === 'sessiz-bas') t.sessiz.bas = el.value;
  if (el.id === 'sessiz-bit') t.sessiz.bit = el.value;
  kaydet('Bildirim planınız kaydedildi.');
};

// ---------- Okuma ----------
const kok = document.documentElement;
function okumayiCiz() {
  let boyut = '18', tema = '';
  try { boyut = localStorage.getItem('tbmm-boyut') || '18'; tema = localStorage.getItem('tbmm-tema') || ''; } catch (_) {}
  document.querySelectorAll('#boyut button').forEach(b => b.setAttribute('aria-selected', b.dataset.v === boyut));
  document.querySelectorAll('#tema button').forEach(b => b.setAttribute('aria-selected', b.dataset.v === tema));
}
$('boyut').onclick = e => {
  const b = e.target.closest('button'); if (!b) return;
  try { localStorage.setItem('tbmm-boyut', b.dataset.v); } catch (_) {}
  kok.style.setProperty('--okuma', b.dataset.v + 'px'); okumayiCiz();
};
$('tema').onclick = e => {
  const b = e.target.closest('button'); if (!b) return;
  try { b.dataset.v ? localStorage.setItem('tbmm-tema', b.dataset.v) : localStorage.removeItem('tbmm-tema'); } catch (_) {}
  b.dataset.v ? (kok.dataset.tema = b.dataset.v) : delete kok.dataset.tema; okumayiCiz();
};

// ---------- Uygulama ----------
function uygulamayiCiz() {
  const u = $('uygulama-durum');
  if (kurulu()) u.textContent = 'Uygulama olarak kullanıyorsunuz.';
  else if (ios()) u.innerHTML = 'Safari\'de <b>Paylaş</b> düğmesine, ardından <b>Ana Ekrana Ekle</b>\'ye dokunun. Bildirimler iPhone\'da yalnızca ana ekrandan açılan uygulamada çalışır.';
  else if (yuklemeOlayi) { u.textContent = 'Ana ekrandan açılır, çevrimdışı da okunur.'; $('yukle').hidden = false; }
  else u.textContent = 'Tarayıcınızın menüsünden “Uygulamayı yükle” ya da “Ana ekrana ekle” seçeneğini kullanabilirsiniz.';
}
$('yukle').onclick = async () => { if (!yuklemeOlayi) return; yuklemeOlayi.prompt(); await yuklemeOlayi.userChoice; $('yukle').hidden = true; uygulamayiCiz(); };
addEventListener('yuklenebilir', uygulamayiCiz);

// ---------- Verileriniz ----------
$('indir').onclick = () => {
  const veriler = {};
  try { for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); if (k.startsWith('tbmm-')) veriler[k] = JSON.parse(localStorage.getItem(k) ?? 'null'); } } catch (_) {}
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify(veriler, null, 2)], { type: 'application/json' }));
  a.download = 'meclis-tutanaklari-verilerim.json'; a.click(); URL.revokeObjectURL(a.href);
};
$('sil').onclick = () => {
  if (!confirm('Bu cihazdaki takip listeniz, tercihleriniz ve okundu işaretleriniz silinecek. Devam edilsin mi?')) return;
  try { Object.keys(localStorage).filter(k => k.startsWith('tbmm-')).forEach(k => localStorage.removeItem(k)); } catch (_) {}
  location.href = 'hosgeldiniz.html';
};

// ---------- Hesap (Firebase yalnızca gerektiğinde yüklenir) ----------
let hesapYuklendi = false;
async function hesabiYukle() {
  if (hesapYuklendi) return; hesapYuklendi = true;
  $('hesap-ic').innerHTML = '<p class="not">Yükleniyor…</p>';
  try { (await import('./hesap.js')).baslat($('hesap-ic')); }
  catch (_) { $('hesap-ic').innerHTML = '<p class="not">Hesap bölümü yüklenemedi. Bağlantınızı kontrol edin.</p>'; hesapYuklendi = false; }
}
$('hesap-ac').onclick = hesabiYukle;
const girisDonusu = /[?&](mode=signIn|oobCode=)/.test(location.search);
let hesapVar = false; try { hesapVar = !!localStorage.getItem('tbmm-hesap'); } catch (_) {}
if (girisDonusu || hesapVar) { hesabiYukle(); if (girisDonusu) $('hesap').scrollIntoView(); }

window.addEventListener('tercih-degisti', () => { t = tercih() || kopya(VARSAYILAN); if (d) takipleriCiz(); planiCiz(); });

(async () => {
  planiCiz(); okumayiCiz(); uygulamayiCiz();
  try { d = await veri(); takipleriCiz(); }
  catch (_) { $('takipler').innerHTML = '<p class="not">Liste yüklenemedi. Bağlantınızı kontrol edin.</p>'; }
})();
