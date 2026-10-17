// Hesap ve cihazlar arası eşitleme (Firebase). Yalnızca Takip sekmesinde, gerektiğinde yüklenir.
// Takip listesi siyasi görüşü dolaylı olarak gösterebileceği için sunucuya ancak ayrı ve açık rızayla gönderilir.
import { tercih, tercihKaydet, VARSAYILAN, okunanlar, esc, kurulu, ios, toast } from './ortak.js';

const SDK = 'https://www.gstatic.com/firebasejs/12.4.0/';
const RIZA_METNI = 'acik-riza-v1-2026-10';
const EPOSTA_KEY = 'tbmm-giris-eposta', RIZA_KEY = 'tbmm-riza-bekliyor', HESAP_KEY = 'tbmm-hesap';
const ls = { al: k => { try { return localStorage.getItem(k); } catch (_) { return null; } },
  koy: (k, v) => { try { localStorage.setItem(k, v); } catch (_) {} }, sil: k => { try { localStorage.removeItem(k); } catch (_) {} } };

let kap, AU, FS, auth, db, kullanici = null, bekleyenLink = null;

function hataMetni(err) {
  const c = err?.code || '';
  if (c.includes('invalid-email')) return 'E-posta adresi geçersiz.';
  if (c.includes('invalid-action-code') || c.includes('expired-action-code')) return 'Bağlantının süresi dolmuş ya da kullanılmış. Yeni bağlantı isteyin.';
  if (c.includes('quota') || c.includes('too-many-requests')) return 'Bugünlük giriş e-postası sınırına ulaşıldı. Lütfen daha sonra tekrar deneyin.';
  if (c.includes('network')) return 'Bağlantı kurulamadı. İnternetinizi kontrol edin.';
  if (c.includes('app-check')) return 'Güvenlik doğrulaması tamamlanamadı. Sayfayı yenileyip tekrar deneyin.';
  return 'Bir hata oluştu (' + (c || err?.message || 'bilinmiyor') + ').';
}

export async function baslat(kapsayici) {
  kap = kapsayici;
  const ayar = JSON.parse(document.getElementById('firebase-ayar').textContent);
  const { initializeApp } = await import(SDK + 'firebase-app.js');
  AU = await import(SDK + 'firebase-auth.js');
  FS = await import(SDK + 'firebase-firestore.js');
  const app = initializeApp(ayar.firebase);
  if (ayar.appcheck) {
    const AC = await import(SDK + 'firebase-app-check.js');
    AC.initializeAppCheck(app, { provider: new AC.ReCaptchaEnterpriseProvider(ayar.appcheck), isTokenAutoRefreshEnabled: true });
  }
  auth = AU.getAuth(app); auth.languageCode = 'tr';
  db = FS.getFirestore(app);

  if (AU.isSignInWithEmailLink(auth, location.href)) {
    const uygulamadan = new URLSearchParams(location.search).get('uyg') === '1';
    if (uygulamadan && ios() && !kurulu()) iosPaneli(); else await girisiTamamla(location.href);
  }
  AU.onAuthStateChanged(auth, u => { kullanici = u; u ? girisliCiz() : girisCiz(); });
}

// ---------- Giriş yapılmamış ----------
function girisCiz(mesaj = '') {
  if (bekleyenLink) return epostaOnayi();
  kap.innerHTML = `
    <p class="not">Hesap yalnızca takip listenizi ve okuduklarınızı başka cihazlarla eşitlemek içindir. Uygulamayı kullanmak için gerekmez.</p>
    <form id="h-form" style="margin-top:15px;display:grid;gap:12px">
      <label class="gizli-metin" for="h-eposta">E-posta adresiniz</label>
      <input class="alan" id="h-eposta" type="email" required autocomplete="email" placeholder="E-posta adresiniz">
      <label class="kutu"><input type="checkbox" id="h-riza"><span>Takip listemin ve okuduklarımın, cihazlarım arasında eşitlenmesi için Avrupa Birliği'ndeki Firebase sunucularında saklanmasına <b>açık rıza veriyorum</b>. Bu rızayı istediğim zaman hesabımı silerek geri alabilirim. <a href="gizlilik.html#riza">Açık rıza metni</a></span></label>
      <button class="dugme ana" type="submit">Giriş bağlantısı gönder</button>
    </form>
    <p class="not" id="h-durum" role="status" style="margin-top:10px">${esc(mesaj)}</p>
    <details class="on-bilgi" style="margin-top:10px"><summary>E-postadaki bağlantıyı yapıştır (iPhone uygulaması)</summary>
      <form id="h-yapistir" style="display:flex;gap:8px;margin-top:8px"><label class="gizli-metin" for="h-link">Bağlantı</label>
      <input class="alan" id="h-link" placeholder="https://…" autocomplete="off"><button class="dugme" type="submit">Giriş yap</button></form></details>`;
  kap.querySelector('#h-form').onsubmit = async e => {
    e.preventDefault();
    const eposta = kap.querySelector('#h-eposta').value.trim();
    if (!kap.querySelector('#h-riza').checked) { kap.querySelector('#h-durum').textContent = 'Eşitleme için açık rıza kutusunu işaretlemeniz gerekir. Uygulamayı hesapsız kullanmaya devam edebilirsiniz.'; return; }
    const url = new URL('takip.html', location.href); url.searchParams.set('giris', '1');
    if (kurulu() && ios()) url.searchParams.set('uyg', '1');
    try {
      await AU.sendSignInLinkToEmail(auth, eposta, { url: url.href, handleCodeInApp: true });
      ls.koy(EPOSTA_KEY, eposta); ls.koy(RIZA_KEY, RIZA_METNI);
      kap.querySelector('#h-durum').textContent = `Giriş bağlantısı ${eposta} adresine gönderildi. E-postadaki bağlantıya dokunun; gelmezse istenmeyen e-posta klasörüne bakın.`;
    } catch (err) { kap.querySelector('#h-durum').textContent = hataMetni(err); }
  };
  kap.querySelector('#h-yapistir').onsubmit = async e => {
    e.preventDefault();
    const link = kap.querySelector('#h-link').value.trim();
    if (!AU.isSignInWithEmailLink(auth, link)) { kap.querySelector('#h-durum').textContent = 'Bu bir giriş bağlantısı değil.'; return; }
    await girisiTamamla(link);
  };
}

async function girisiTamamla(link) {
  const eposta = ls.al(EPOSTA_KEY);
  if (!eposta) { bekleyenLink = link; epostaOnayi(); return; }
  try {
    await AU.signInWithEmailLink(auth, eposta, link);
    ls.sil(EPOSTA_KEY); bekleyenLink = null;
    history.replaceState(null, '', location.pathname + '#hesap');
  } catch (err) { girisCiz(hataMetni(err)); history.replaceState(null, '', location.pathname); }
}

function epostaOnayi() {
  kap.innerHTML = `<p class="not">Bağlantı başka bir cihazda ya da tarayıcıda açıldı. Güvenlik için bağlantıyı istediğiniz e-posta adresini yazın.</p>
    <form id="h-onay" style="display:grid;gap:12px;margin-top:12px"><label class="gizli-metin" for="h-onay-eposta">E-posta</label>
    <input class="alan" id="h-onay-eposta" type="email" required autocomplete="email">
    <label class="kutu"><input type="checkbox" id="h-onay-riza"><span>Eşitleme için <a href="gizlilik.html#riza">açık rıza</a> veriyorum.</span></label>
    <button class="dugme ana" type="submit">Giriş yap</button></form><p class="not" id="h-durum" role="status"></p>`;
  kap.querySelector('#h-onay').onsubmit = async e => {
    e.preventDefault();
    ls.koy(EPOSTA_KEY, kap.querySelector('#h-onay-eposta').value.trim());
    if (kap.querySelector('#h-onay-riza').checked) ls.koy(RIZA_KEY, RIZA_METNI);
    const link = bekleyenLink; bekleyenLink = null; await girisiTamamla(link);
  };
}

function iosPaneli() {
  kap.innerHTML = `<p><b>Uygulamada giriş yapın.</b> Bu bağlantı ana ekrandaki uygulamadan istendi; iPhone'da uygulama ve Safari ayrı oturum tutar.</p>
    <ol class="not" style="padding-left:18px"><li>Bağlantıyı kopyalayın.</li><li>Ana ekrandaki <b>Meclis</b> uygulamasını açın.</li><li><b>Takip → Hesap → Bağlantıyı yapıştır</b> alanına yapıştırın.</li></ol>
    <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:10px"><button class="dugme ana" id="h-kopyala">Bağlantıyı kopyala</button>
    <button class="dugme" id="h-burada">Bunun yerine Safari'de giriş yap</button></div>`;
  kap.querySelector('#h-kopyala').onclick = async () => {
    try { await navigator.clipboard.writeText(location.href); toast('Kopyalandı. Şimdi uygulamayı açıp yapıştırın.'); }
    catch (_) { toast('Kopyalanamadı; adres çubuğundaki bağlantıyı elle kopyalayın.'); }
  };
  kap.querySelector('#h-burada').onclick = () => girisiTamamla(location.href);
}

// ---------- Giriş yapılmış ----------
const yerelTakip = t => ({ mv: t.mv, parti: t.parti, iller: t.iller, kelime: t.kelime, konular: t.konular });
const yerelTercih = t => ({ turler: t.turler, ritim: t.ritim, sessiz: t.sessiz });
const birlesik = (a = [], b = []) => [...new Set([...a, ...b])];

async function girisliCiz() {
  ls.koy(HESAP_KEY, '1');
  const ref = FS.doc(db, 'users', kullanici.uid);
  let snap;
  try { snap = await FS.getDoc(ref); } catch (err) { kap.innerHTML = `<p class="not">${esc(hataMetni(err))}</p>`; return; }
  if (!snap.exists() && !ls.al(RIZA_KEY)) return rizaIste();
  kap.innerHTML = `<p>Giriş yapılan hesap: <b>${esc(kullanici.email || kullanici.phoneNumber || '')}</b></p>
    <p class="not" id="h-durum" role="status" style="margin-top:6px">Eşitleniyor…</p>
    <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:12px">
      <button class="dugme" id="h-esitle">Şimdi eşitle</button><button class="dugme" id="h-cikis">Çıkış yap</button></div>
    <div style="margin-top:20px"><button class="dugme tehlike" id="h-sil">Hesabımı ve sunucudaki verilerimi sil</button>
    <p class="not" id="h-sil-durum" style="margin-top:6px">Bu cihazdaki takip listeniz silinmez.</p></div>`;
  kap.querySelector('#h-esitle').onclick = esitle;
  kap.querySelector('#h-cikis').onclick = async () => { await AU.signOut(auth); ls.sil(HESAP_KEY); ls.sil(EPOSTA_KEY); toast('Çıkış yapıldı. Bu cihazdaki tercihleriniz duruyor.'); };
  kap.querySelector('#h-sil').onclick = hesabiSil;
  await esitle();
}

function rizaIste() {
  kap.innerHTML = `<p>Giriş yaptınız: <b>${esc(kullanici.email || '')}</b></p>
    <label class="kutu" style="margin-top:12px"><input type="checkbox" id="h-riza2"><span>Takip listemin ve okuduklarımın eşitleme için Avrupa Birliği'ndeki Firebase sunucularında saklanmasına <a href="gizlilik.html#riza">açık rıza veriyorum</a>.</span></label>
    <div style="display:flex;gap:8px;margin-top:12px"><button class="dugme ana" id="h-onayla">Eşitlemeyi başlat</button><button class="dugme" id="h-vazgec">Vazgeç ve çıkış yap</button></div>`;
  kap.querySelector('#h-onayla').onclick = () => { if (!kap.querySelector('#h-riza2').checked) { toast('Önce açık rıza kutusunu işaretleyin.'); return; } ls.koy(RIZA_KEY, RIZA_METNI); girisliCiz(); };
  kap.querySelector('#h-vazgec').onclick = async () => { await AU.signOut(auth); ls.sil(HESAP_KEY); };
}

async function esitle() {
  const durum = kap.querySelector('#h-durum');
  const ref = FS.doc(db, 'users', kullanici.uid);
  try {
    const snap = await FS.getDoc(ref);
    let t = tercih() || JSON.parse(JSON.stringify(VARSAYILAN));
    if (snap.exists()) {
      const u = snap.data();
      const r = u.takip || {};
      t.mv = birlesik(t.mv, r.mv); t.parti = birlesik(t.parti, r.parti); t.iller = birlesik(t.iller, r.iller);
      t.kelime = birlesik(t.kelime, r.kelime); t.konular = birlesik(t.konular, r.konular);
      if (!t.tamamlandi && u.tercih) Object.assign(t, u.tercih);
      tercihKaydet(t);
      await FS.updateDoc(ref, { takip: yerelTakip(t), tercih: yerelTercih(t), guncelleme: FS.serverTimestamp() });
    } else {
      tercihKaydet(t);
      await FS.setDoc(ref, { eposta: kullanici.email || null, telefon: kullanici.phoneNumber || null,
        olusturma: FS.serverTimestamp(), takip: yerelTakip(t), tercih: yerelTercih(t),
        riza: { metin: ls.al(RIZA_KEY) || RIZA_METNI, zaman: FS.serverTimestamp() } });
      ls.sil(RIZA_KEY);
    }
    // Okundu işaretleri: iki taraftaki en yeni zaman korunur
    const oref = FS.doc(db, 'users', kullanici.uid, 'veri', 'okundu');
    const uzak = (await FS.getDoc(oref)).data()?.ids || {};
    const yerel = okunanlar(), hepsi = { ...uzak };
    for (const [k, z] of Object.entries(yerel)) hepsi[k] = Math.max(hepsi[k] || 0, z);
    try { localStorage.setItem('tbmm-okundu', JSON.stringify(hepsi)); } catch (_) {}
    if (Object.keys(hepsi).length !== Object.keys(uzak).length) await FS.setDoc(oref, { ids: hepsi, guncelleme: FS.serverTimestamp() });
    durum.textContent = `Eşitlendi · ${new Intl.DateTimeFormat('tr-TR', { hour: '2-digit', minute: '2-digit' }).format(new Date())}`;
  } catch (err) { durum.textContent = hataMetni(err); }
}

async function hesabiSil() {
  const d = kap.querySelector('#h-sil-durum');
  const son = Date.parse(kullanici.metadata.lastSignInTime || 0);
  if (Date.now() - son > 5 * 60 * 1000) { d.textContent = 'Güvenlik için önce çıkış yapıp yeniden giriş yapın, sonra tekrar deneyin.'; return; }
  if (!confirm('Hesabınız ve sunucudaki takip listeniz ile okundu işaretleriniz kalıcı olarak silinecek. Bu cihazdaki veriler kalır. Emin misiniz?')) return;
  try {
    await FS.deleteDoc(FS.doc(db, 'users', kullanici.uid, 'veri', 'okundu'));
    await FS.deleteDoc(FS.doc(db, 'users', kullanici.uid));
    await AU.deleteUser(kullanici);
    ls.sil(HESAP_KEY); toast('Hesabınız ve sunucudaki verileriniz silindi.');
  } catch (err) { d.textContent = hataMetni(err); }
}
