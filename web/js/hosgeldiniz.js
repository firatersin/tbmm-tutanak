// İlk açılış: dört atlanabilir soru + bildirim planı. Yanıtlar yalnızca bu cihazda saklanır.
import { veri, tercih, tercihKaydet, VARSAYILAN, katla, esc, sirala, dagilim, eslestir, kelimeEsles,
  kurulu, ios, yuklemeOlayi, toast } from './ortak.js';

const $ = id => document.getElementById(id);
const yeniden = new URLSearchParams(location.search).has('yeniden');
const kopya = o => JSON.parse(JSON.stringify(o));
let t = yeniden && tercih() ? tercih() : kopya(VARSAYILAN);
let adim = 0, d;
const ADIMLAR = [ilAdimi, kisiAdimi, konuAdimi, turAdimi, planAdimi];

function kaydet(tamam = false) {
  if (tamam) { t.tamamlandi = Date.now(); t.atlandi = false; }
  tercihKaydet(t);
}

function goster(n) {
  adim = n;
  $('ilerleme').innerHTML = ADIMLAR.map((_, i) => `<i class="${i <= adim ? 'tamam' : ''}"></i>`).join('');
  $('ilerleme').setAttribute('aria-label', `Adım ${adim + 1} / ${ADIMLAR.length}`);
  $('geri').hidden = adim === 0;
  ADIMLAR[adim]();
  const h = document.querySelector('#adim h1'); h?.setAttribute('tabindex', '-1'); h?.focus({ preventScroll: true });
  scrollTo(0, 0);
}
function ileriEtiketi(secimVar, son = false) {
  $('ileri').textContent = son ? 'Akışıma git' : secimVar ? 'Devam' : 'Bu adımı atla';
}

// ---------- 1. İl ----------
function ilAdimi() {
  const sayilar = {}; d.mv.forEach(m => { sayilar[m[2]] = (sayilar[m[2]] || 0) + 1; });
  $('adim').innerHTML = `
    <h1>Hangi ili takip etmek istersiniz?</h1>
    <p class="yardim">Bu ilin milletvekillerinin oylarını ve konuşmalarını öne çıkarırız. Memleketiniz ya da çalıştığınız yer için birden fazla il seçebilirsiniz.</p>
    <div style="margin-top:20px"><label class="gizli-metin" for="il-ara">İl ara</label>
    <input class="alan" id="il-ara" type="search" placeholder="İl adı yazın, ör. izmir" autocomplete="off"></div>
    <div class="secilenler" id="il-secilen"></div>
    <ul class="secim-listesi" id="il-liste"></ul>
    <div class="on-izleme" id="ilk-sonuc" hidden></div>`;
  const ciz = () => {
    const q = katla($('il-ara').value.trim());
    $('il-liste').innerHTML = d.iller.filter(il => !q || katla(il).includes(q)).map(il =>
      `<li><button type="button" data-il="${esc(il)}" aria-pressed="${t.iller.includes(il)}">${esc(il)} <small>${sayilar[il] || 0} milletvekili</small></button></li>`).join('')
      || '<li class="not" style="padding:15px 0">Bu adla bir il bulunamadı.</li>';
    $('il-secilen').innerHTML = t.iller.map(il => `<button type="button" data-cikar="${esc(il)}" aria-label="${esc(il)} seçimini kaldır">${esc(il)} <span aria-hidden="true">×</span></button>`).join('');
    ilkSonuc();
    ileriEtiketi(t.iller.length);
  };
  $('il-ara').oninput = ciz;
  $('adim').onclick = e => {
    const b = e.target.closest('[data-il],[data-cikar]'); if (!b) return;
    const il = b.dataset.il || b.dataset.cikar; const i = t.iller.indexOf(il);
    i < 0 ? t.iller.push(il) : t.iller.splice(i, 1);
    ciz();
  };
  ciz();
}
function ilkSonuc() {
  const k = $('ilk-sonuc');
  const son = [...d.ogeler].reverse().find(o => o.t === 'O');
  if (!t.iller.length || !son) { k.hidden = true; return; }
  const satirlar = t.iller.slice(0, 3).map(il => son.iv[il] ? `<li>${esc(il)} milletvekilleri: <b>${dagilim(son.iv[il])}</b></li>` : '').join('');
  k.innerHTML = `<p class="ust-etiket">Örnek: son açık oylama</p><p style="font:500 17px/24px var(--serif)">${esc(son.b)}</p>
    <ul style="margin:8px 0 0;padding-left:18px;font-size:15px;line-height:24px">${satirlar}</ul>`;
  k.hidden = !satirlar;
}

// ---------- 2. Milletvekilleri ve partiler ----------
function kisiAdimi() {
  $('adim').innerHTML = `
    <h1>Hangi milletvekillerini ve partileri takip etmek istersiniz?</h1>
    <p class="yardim">Takip etmek destek anlamına gelmez; farklı görüşlerden istediğiniz kadar seçebilirsiniz.</p>
    <div class="konu-grup"><h2>Partiler</h2>
      <p class="not" style="margin-bottom:10px">Sıralama: TBMM'deki güncel sandalye sayısı (bağımsızlar sonda).</p>
      <div class="cipler" id="partiler"></div>
      <button type="button" class="dugme yalin" id="tum-partiler" style="margin-top:6px">Tüm partileri seç</button></div>
    <div class="konu-grup"><h2>Milletvekilleri</h2>
      <label class="gizli-metin" for="mv-ara">Milletvekili ara</label>
      <input class="alan" id="mv-ara" type="search" placeholder="Ad, il ya da parti yazın" autocomplete="off">
      <div class="secilenler" id="mv-secilen"></div>
      <p class="ust-etiket" id="mv-baslik" style="margin:15px 0 0"></p>
      <ul class="secim-listesi" id="mv-liste"></ul></div>`;
  const partiSira = Object.fromEntries(d.partiler.map((p, i) => [p, i]));
  const cizPartiler = () => {
    $('partiler').innerHTML = d.partiler.map(p =>
      `<button type="button" class="cip" data-parti="${esc(p)}" aria-pressed="${t.parti.includes(p)}"><i class="sw ${d.ps[p]}" aria-hidden="true"></i>${esc(p)} <span class="say">${d.koltuk[p]}</span></button>`).join('');
  };
  const cizMv = () => {
    const q = katla($('mv-ara').value.trim());
    let liste, baslik;
    if (q.length >= 2) {
      liste = d.mv.filter(m => katla(`${m[1]} ${m[2]} ${m[3]}`).includes(q)).slice(0, 40); baslik = `${liste.length} sonuç`;
    } else if (t.iller.length) {
      liste = d.mv.filter(m => t.iller.includes(m[2])); baslik = `${t.iller.join(', ')} milletvekilleri`;
    } else { liste = []; baslik = 'Aramak için bir ad yazın'; }
    liste.sort((a, b) => (partiSira[a[3]] - partiSira[b[3]]) || sirala(a[1], b[1]));
    $('mv-baslik').textContent = baslik;
    $('mv-liste').innerHTML = liste.map(m =>
      `<li><button type="button" data-mv="${esc(m[0])}" aria-pressed="${t.mv.includes(m[0])}"><span>${esc(m[1])} <small>${esc(m[2])} · ${esc(m[3])}</small></span></button></li>`).join('');
    $('mv-secilen').innerHTML = t.mv.map(id => { const m = d.mv[d.mvIndex[id]]; return m ? `<button type="button" data-cikar="${esc(id)}" aria-label="${esc(m[1])} seçimini kaldır">${esc(m[1])} <span aria-hidden="true">×</span></button>` : ''; }).join('');
    ileriEtiketi(t.mv.length || t.parti.length);
  };
  $('mv-ara').oninput = cizMv;
  $('tum-partiler').onclick = () => { t.parti = t.parti.length === d.partiler.length ? [] : [...d.partiler]; cizPartiler(); ileriEtiketi(t.mv.length || t.parti.length); };
  $('adim').onclick = e => {
    const p = e.target.closest('[data-parti]');
    if (p) { const i = t.parti.indexOf(p.dataset.parti); i < 0 ? t.parti.push(p.dataset.parti) : t.parti.splice(i, 1); cizPartiler(); ileriEtiketi(t.mv.length || t.parti.length); return; }
    const m = e.target.closest('[data-mv],[data-cikar]'); if (!m) return;
    const id = m.dataset.mv || m.dataset.cikar; const i = t.mv.indexOf(id);
    i < 0 ? t.mv.push(id) : t.mv.splice(i, 1); cizMv();
  };
  cizPartiler(); cizMv();
}

// ---------- 3. Konular ----------
function konuAdimi() {
  $('adim').innerHTML = `
    <h1>Hangi konular sizin için önemli?</h1>
    <p class="yardim">Bu konular tutanaklarda ya da oylanan tekliflerin gerekçelerinde geçtiğinde akışınızda öne çıkar. Üç konu öneririz; zorunlu değildir.</p>
    <div class="cipler" id="konular" style="margin-top:20px"></div>
    <p class="not" id="konu-kelimeler" style="margin-top:10px"></p>
    <div class="konu-grup"><h2>Kendi kelimeniz</h2>
      <form id="kelime-form" style="display:flex;gap:8px"><label class="gizli-metin" for="kelime">Kelime ekle</label>
        <input class="alan" id="kelime" placeholder="ör. asgari ücret, deprem, kooperatif" maxlength="60" autocomplete="off">
        <button class="dugme" type="submit">Ekle</button></form>
      <div class="secilenler" id="kelime-secilen"></div></div>
    <div class="on-izleme" aria-live="polite"><p class="ust-etiket">Önizleme · son 30 gün</p><p id="onizleme" class="not">Hesaplanıyor…</p></div>`;
  const ciz = () => {
    $('konular').innerHTML = d.konular.map(([k, ad]) => `<button type="button" class="cip" data-konu="${k}" aria-pressed="${t.konular.includes(k)}">${esc(ad)}</button>`).join('');
    const secili = t.konular.map(k => d.konuMap[k]).filter(Boolean);
    $('konu-kelimeler').innerHTML = secili.length ? 'Aranan kelimeler: ' + secili.map(k => `<b>${esc(k.ad)}</b>: ${esc(k.kelimeler.join(', '))}`).join(' · ') : '';
    $('kelime-secilen').innerHTML = t.kelime.map(k => `<button type="button" data-cikar="${esc(k)}" aria-label="${esc(k)} kelimesini kaldır">“${esc(k)}” <span aria-hidden="true">×</span></button>`).join('');
    ileriEtiketi(t.konular.length || t.kelime.length);
    onizleme();
  };
  $('adim').onclick = e => {
    const k = e.target.closest('[data-konu]');
    if (k) { const i = t.konular.indexOf(k.dataset.konu); i < 0 ? t.konular.push(k.dataset.konu) : t.konular.splice(i, 1); ciz(); return; }
    const c = e.target.closest('[data-cikar]'); if (c) { t.kelime.splice(t.kelime.indexOf(c.dataset.cikar), 1); ciz(); }
  };
  $('kelime-form').onsubmit = async e => {
    e.preventDefault();
    const k = $('kelime').value.trim().replace(/\s+/g, ' ');
    if (k.length < 3) { toast('En az 3 harf yazın.'); return; }
    if (!t.kelime.includes(k)) t.kelime.push(k);
    $('kelime').value = ''; ciz();
    if (!(await kelimeEsles(k, d.surum)).size) toast(`“${k}” henüz hiçbir kayıtta geçmiyor; yine de takip edilir.`);
  };
  ciz();
}
let onizlemeSirasi = 0;
async function onizleme() {
  const benim = ++onizlemeSirasi;
  const sinir = new Date(Date.now() - 30 * 864e5).toISOString().slice(0, 10);
  const es = await eslestir(d, { ...t, turler: { oylama: true, ozet: true, konusma: true, teklif: true } });
  if (benim !== onizlemeSirasi || !$('onizleme')) return;
  if (!es) { $('onizleme').textContent = 'Henüz bir seçim yapmadınız; akışınızda tüm kayıtlar görünür.'; return; }
  let o = 0, tu = 0;
  es.forEach((_, i) => { const x = d.ogeler[i]; if (x.d >= sinir) x.t === 'O' ? o++ : tu++; });
  $('onizleme').innerHTML = `Seçimlerinizle eşleşen: <b>${o} açık oylama</b> · <b>${tu} tutanak</b>`
    + (o + tu === 0 ? '<br>Son 30 günde eşleşme yok; Meclis tatildeyse ya da konu nadir geçiyorsa bu normaldir.' : '');
}

// ---------- 4. Bilgi türleri ve sıklık ----------
const TURLER = [
  ['oylama', 'Oylamalar', 'Kim nasıl oy verdi; partilere ve illere göre dağılım'],
  ['ozet', 'Oturum özetleri ve kararlar', 'Genel Kurul\'da o gün neler kararlaştırıldı'],
  ['konusma', 'Konuşmalar', 'Takip ettiğiniz milletvekillerinin Genel Kurul konuşmaları'],
  ['teklif', 'Kanun teklifleri ve gerekçeleri', 'Oylanan teklifin resmî gerekçesinden ana başlıklar'],
];
const RITIM = [
  ['yakindan', 'Yakından takip', 'Oturum sırasında, takip ettiğiniz milletvekillerinin oylarında anlık bildirim (oturum başına en fazla 3)'],
  ['gunluk', 'Günlük özet (önerilen)', 'Oturum günlerinin ertesi sabahı tek bir özet'],
  ['haftalik', 'Haftalık özet', 'Haftada bir toplu özet'],
];
function turAdimi() {
  $('adim').innerHTML = `
    <h1>Ne tür bilgiler, ne sıklıkla?</h1>
    <p class="yardim">Akışınızda ve ileride bildirimlerinizde neyin yer alacağını belirler.</p>
    <fieldset style="border:0;margin:20px 0 0;padding:0"><legend class="ust-etiket">Bilgi türleri</legend>
      ${TURLER.map(([k, ad, aciklama]) => `<div class="secenek"><label class="kutu"><input type="checkbox" data-tur="${k}" ${t.turler[k] ? 'checked' : ''}><span><b>${ad}</b><span>${aciklama}</span></span></label></div>`).join('')}
    </fieldset>
    <fieldset style="border:0;margin:30px 0 0;padding:0"><legend class="ust-etiket">Ne sıklıkla</legend>
      ${RITIM.map(([k, ad, aciklama]) => `<div class="secenek"><label class="kutu"><input type="radio" name="ritim" value="${k}" ${t.ritim === k ? 'checked' : ''}><span><b>${ad}</b><span>${aciklama}</span></span></label></div>`).join('')}
      <p class="not" style="margin-top:10px">Oturum günlerinde çok sayıda oylama olabilir; özet seçenekleri bunları tek bildirimde toplar.</p>
    </fieldset>`;
  $('adim').onchange = e => {
    if (e.target.dataset.tur) t.turler[e.target.dataset.tur] = e.target.checked;
    if (e.target.name === 'ritim') t.ritim = e.target.value;
    ileriEtiketi(true);
  };
  $('adim').onclick = null;
  ileriEtiketi(true);
}

// ---------- 5. Bildirim planı ----------
function planAdimi() {
  const ritimAdi = { yakindan: 'Anlık (oturum başına en fazla 3)', gunluk: 'Ertesi sabah özeti', haftalik: 'Haftalık özet' }[t.ritim];
  const ozetAdi = t.ritim === 'haftalik' ? 'Haftalık özet' : 'Ertesi sabah özeti';
  const satirlar = [];
  if (t.mv.length && t.turler.oylama) satirlar.push(['Takip ettiğiniz milletvekillerinin oyları', `${t.mv.length} milletvekili`, ritimAdi]);
  if (t.mv.length && t.turler.konusma) satirlar.push(['Takip ettiğiniz milletvekillerinin konuşmaları', 'Tutanaklar ertesi gün yayımlanır', ozetAdi]);
  if (t.iller.length && (t.turler.oylama || t.turler.konusma)) satirlar.push(['İl milletvekilleri', t.iller.join(', '), ozetAdi]);
  if (t.parti.length && t.turler.oylama) satirlar.push(['Parti grup oy dağılımları', t.parti.join(', '), ozetAdi]);
  if (t.kelime.length || t.konular.length) satirlar.push(['Konu ve kelime eşleşmeleri', [...t.konular.map(k => d.konuMap[k]?.ad), ...t.kelime.map(k => `“${k}”`)].join(', '), t.ritim === 'haftalik' ? 'Haftalık özet' : 'Günlük özet']);
  if (t.turler.ozet) satirlar.push(['Oturum özetleri ve kararlar', 'Genel Kurul\'un toplandığı günler', ozetAdi]);
  const saatler = Array.from({ length: 24 }, (_, h) => `${String(h).padStart(2, '0')}:00`);
  const sec = (id, deger) => `<select class="alan" id="${id}" style="width:auto">${saatler.map(s => `<option ${s === deger ? 'selected' : ''}>${s}</option>`).join('')}</select>`;
  let platform = '';
  if (ios() && !kurulu()) platform = `<div class="on-izleme"><p class="ust-etiket">iPhone ve iPad</p><p class="not">Bildirim alabilmek için uygulamayı ana ekrana eklemeniz gerekir: Safari'de <b>Paylaş</b> düğmesine, ardından <b>Ana Ekrana Ekle</b>'ye dokunun. Sonra uygulamayı ana ekrandan açın.</p></div>`;
  else if (yuklemeOlayi && !kurulu()) platform = `<div class="on-izleme"><p class="not">Uygulamayı yüklerseniz ana ekrandan açılır ve bildirimler daha güvenilir çalışır.</p><button class="dugme" id="yukle" type="button" style="margin-top:10px">Uygulamayı yükle</button></div>`;
  $('adim').innerHTML = `
    <h1>Bildirim planınız</h1>
    <p class="yardim">Seçimlerinize göre şunları göndereceğiz:</p>
    <div style="margin-top:15px;border-top:1px solid var(--murekkep)">${satirlar.map(([a, b, c]) => `<div class="plan-satir"><b>${esc(a)}</b><span>${esc(b)}</span><em>${esc(c)}</em></div>`).join('')
      || '<p class="not" style="padding:15px 0">Takip seçimi yapmadınız; yalnızca genel akışı göreceksiniz.</p>'}</div>
    <div class="secenek" style="display:flex;flex-wrap:wrap;gap:10px;align-items:center"><span><b>Sessiz saatler</b></span>${sec('sessiz-bas', t.sessiz.bas)}<span aria-hidden="true">–</span>${sec('sessiz-bit', t.sessiz.bit)}</div>
    <p class="not" style="margin-top:10px">Bu saatlerde gelen her şey sabah özetine eklenir. Oturum günlerinde en fazla 3 anlık bildirim ve bir sabah özeti.</p>
    <div class="on-izleme"><p class="ust-etiket">Bildirimler</p><p class="not">Bildirim gönderimi çok yakında açılacak. Planınız kaydedildi; gönderim başladığında izninizi buradan isteyeceğiz.</p></div>
    ${platform}
    <p class="not" style="margin-top:20px">Seçimleriniz yalnızca bu cihazda saklanır. Başka cihazlarla eşitlemek isterseniz Takip sekmesindeki Hesap bölümünden ayrıca onay verebilirsiniz. <a href="gizlilik.html">Gizlilik</a></p>`;
  $('sessiz-bas').onchange = e => { t.sessiz.bas = e.target.value; };
  $('sessiz-bit').onchange = e => { t.sessiz.bit = e.target.value; };
  $('adim').onclick = async e => {
    if (e.target.id === 'yukle' && yuklemeOlayi) { yuklemeOlayi.prompt(); await yuklemeOlayi.userChoice; e.target.closest('.on-izleme').hidden = true; }
  };
  ileriEtiketi(true, true);
}

// ---------- Gezinme ----------
$('ileri').onclick = () => {
  kaydet(adim === ADIMLAR.length - 1);
  if (adim === ADIMLAR.length - 1) location.href = 'index.html';
  else goster(adim + 1);
};
$('geri').onclick = () => goster(adim - 1);
$('atla-hepsi').onclick = () => {
  if (!t.tamamlandi) t.atlandi = true;
  kaydet(false);
  location.href = 'index.html';
};

(async () => {
  try { d = await veri(); }
  catch (_) { $('adim').innerHTML = '<div class="bos"><h2>Veriler yüklenemedi</h2><p>Bağlantınızı kontrol edin. İsterseniz şimdilik atlayıp daha sonra Takip sekmesinden ayarlayabilirsiniz.</p></div>'; return; }
  goster(0);
})();
