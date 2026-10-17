// Akış sekmesi: takip edilenlere göre kişisel akış (cihazda hesaplanır) ya da genel zaman çizelgesi.
import { veri, tercih, tercihVarMi, depolamaVar, takipSayisi, eslestir, okunanlar, satirHTML, gunEtiketi,
  esc, kurulu, ios, yuklemeOlayi, toast } from './ortak.js';

if (!tercihVarMi() && depolamaVar()) location.replace('hosgeldiniz.html');

const $ = id => document.getElementById(id);
const SAYFA = 40;
let tur = '', sadeceYeni = false, goster = SAYFA, d, eslesme, t;

function ozetSatiri() {
  if (t && takipSayisi(t)) {
    const parcalar = [];
    if (t.iller.length) parcalar.push(t.iller.length === 1 ? t.iller[0] : `${t.iller.length} il`);
    if (t.mv.length) parcalar.push(`${t.mv.length} milletvekili`);
    if (t.parti.length) parcalar.push(`${t.parti.length} parti`);
    const konu = t.kelime.length + t.konular.length;
    if (konu) parcalar.push(`${konu} konu`);
    $('alt').innerHTML = `Takip ettikleriniz: ${esc(parcalar.join(', '))} · <a href="takip.html">Düzenle</a>`;
  } else {
    $('alt').innerHTML = 'Tüm tutanak ve oylamalar, en yenisi üstte · <a href="hosgeldiniz.html">Akışınızı kişiselleştirin</a>';
  }
}

function ciz() {
  const ok = okunanlar();
  const kisisel = !!eslesme;
  const satirlar = [];
  for (let i = d.ogeler.length - 1; i >= 0; i--) {
    const o = d.ogeler[i];
    if (tur && o.t !== tur) continue;
    if (kisisel && !eslesme.has(i)) continue;
    if (sadeceYeni && ok[o.id]) continue;
    satirlar.push([o, kisisel ? eslesme.get(i) : null]);
  }
  if (!satirlar.length) {
    $('liste').innerHTML = kisisel
      ? `<div class="bos"><h2>Seçimlerinizle eşleşen kayıt yok</h2><p>${sadeceYeni ? 'Okunmamış kayıt kalmadı.' : 'Takip listenize il, milletvekili ya da konu ekleyebilirsiniz.'}</p><a class="dugme" href="takip.html">Takip ettiklerimi düzenle</a></div>`
      : '<div class="bos"><h2>Gösterilecek kayıt yok</h2><p>Filtreleri değiştirmeyi deneyin.</p></div>';
    $('daha').hidden = true; return;
  }
  let html = '', gun = '';
  for (const [o, n] of satirlar.slice(0, goster)) {
    if (o.d !== gun) {
      if (gun) html += '</ul>';
      gun = o.d; html += `<h2 class="gun">${gunEtiketi(o.d)}</h2><ul class="liste">`;
    }
    html += satirHTML(o, n, ok, { ozetGoster: !kisisel || t.turler.teklif });
  }
  $('liste').innerHTML = html + '</ul>';
  $('daha').hidden = satirlar.length <= goster;
  $('daha').textContent = `Daha fazla göster (${satirlar.length - goster})`;
}

async function hazirla() {
  t = tercih();
  ozetSatiri();
  try { d = await veri(); }
  catch (_) { $('liste').innerHTML = '<div class="bos"><h2>Kayıtlar yüklenemedi</h2><p>Bağlantınızı kontrol edip yeniden deneyin.</p><a class="dugme" href="index.html">Tekrar dene</a></div>'; return; }
  eslesme = await eslestir(d, t);
  ciz();
}

document.querySelectorAll('#tur button').forEach(b => b.onclick = () => {
  tur = b.dataset.v; goster = SAYFA;
  document.querySelectorAll('#tur button').forEach(x => x.setAttribute('aria-pressed', x === b));
  ciz();
});
$('sadeceYeni').onchange = e => { sadeceYeni = e.target.checked; goster = SAYFA; ciz(); };
$('daha').onclick = () => { goster += SAYFA; ciz(); };
addEventListener('pageshow', e => { if (e.persisted && d) ciz(); });

// Uygulama olarak yükleme önerisi (bir kez kapatılabilir)
function yuklemeIpucu() {
  let kapali = false; try { kapali = !!localStorage.getItem('tbmm-yukle-kapat'); } catch (_) {}
  if (kurulu() || kapali) return;
  const k = $('yukle');
  if (ios()) {
    k.querySelector('p').innerHTML = 'Uygulama gibi kullanmak ve ileride bildirim alabilmek için Safari\'de <b>Paylaş</b>, ardından <b>Ana Ekrana Ekle</b>\'ye dokunun.';
    k.hidden = false;
  } else if (yuklemeOlayi) {
    k.querySelector('p').textContent = 'Meclis Tutanakları\'nı uygulama olarak yükleyebilirsiniz; ana ekrandan açılır ve çevrimdışı da okunur.';
    $('yukle-dugme').hidden = false; k.hidden = false;
  }
}
$('yukle-dugme').onclick = async () => { if (!yuklemeOlayi) return; yuklemeOlayi.prompt(); await yuklemeOlayi.userChoice; $('yukle').hidden = true; };
$('yukle-kapat').onclick = () => { $('yukle').hidden = true; try { localStorage.setItem('tbmm-yukle-kapat', '1'); } catch (_) {} toast('Takip sekmesinden sonra da yükleyebilirsiniz.'); };
addEventListener('yuklenebilir', yuklemeIpucu);

yuklemeIpucu();
hazirla();
