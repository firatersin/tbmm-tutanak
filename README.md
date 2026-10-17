# TBMM Tutanak Takip

TBMM Genel Kurul tutanaklarını ve açık oylama sonuçlarını her gün otomatik olarak çeker. Hepsini tarih sırasına
dizen, sunucusuz bir okuma sitesi üretir.

- **Tutanaklar:** Yeni birleşimler ve durum geçişleri (Ham → Tam → Basılmış) takip edilir. Kesin hâl
  yayınlandığında metin güncellenir.
- **Açık oylamalar:** Her oylamanın sonucu, toplamları, parti bazında dağılımı ve milletvekili bazında oy dökümü.
  Parti kırılımı grafiğinden partiye veya oy türüne tıklayınca ilgili milletvekilleri listelenir.
- **Oylanan metnin resmi gerekçesi:** Oylanan teklifin komisyon raporu (sıra sayısı) bulunur. Gerekçesinden ana
  başlıklar değiştirilmeden çıkarılır: genel gerekçedeki resmi liste ya da amaç cümleleri, madde madde gerekçeler
  ve genel gerekçenin tamamı. Yapay zekâ özeti kullanılmaz.
- **Uygulama:** Telefona kurulabilen, beş sekmeli bir okuma uygulaması (Akış, Oturumlar, Oylamalar, Ara, Takip).
  İlk açılışta il, milletvekili/parti, konu ve bilgi türü/sıklık soran, her adımı atlanabilen bir karşılama akışı;
  yanıtlar yalnızca cihazda saklanır ve kişisel akışı (her kaydın altında "neden görüyorum" ile) belirler.
  Milletvekili, parti ve il sayfaları; tam metin arama; tutanak okuyucusunda içindekiler, konuşmacıya atlama,
  metinde arama ve yazı boyutu.
- **Tasarım:** Kâğıt-mürekkep teması ve tek bir petrol vurgusu (hiçbir partiyle ilişkili değil), Newsreader ve
  IBM Plex Sans (kendi sunucumuzdan), oylar renk körlüğüne uygun mavi/kızıl ve ✓ ✕ – · işaretleriyle. Kaynaklar:
  `web/` (biçem, betikler, yazı tipleri), `sablon.py` (iskelet), `sayfalar.py` (sayfalar), `akis.py` (veri dosyaları).

Python standart kütüphanesi ve PDF okumak için `pypdf` kullanılır (`pip install -r requirements.txt`).

## Mobil uygulama

Site, telefona uygulama olarak kurulabilir (PWA). Kendi ikonuyla tam ekran açılır, açılan sayfalar çevrimdışı
okunabilir ve GitHub her yayın yaptığında kendiliğinden güncellenir.

- **Android (Chrome):** Siteyi açın, ana sayfadaki **Uygulamayı yükle** düğmesine ya da menüdeki
  **Uygulamayı yükle / Ana ekrana ekle**'ye dokunun.
- **iPhone (Safari):** Siteyi açın, **Paylaş** düğmesine, ardından **Ana Ekrana Ekle**'ye dokunun.

Service worker bildirim almaya hazırdır (yük: `{"title", "body", "url", "tag"}`); bildirim gönderen taraf henüz
eklenmedi. İkonlar `tools/ikonlar.py` ile üretilir ve `static/` altında durur.

## GitHub üzerinde çalışma

`.github/workflows/guncelle.yml` her gün Türkiye saatiyle 09:00 ve 21:00'de çalışır:

1. TBMM'yi tarar, yeni ve değişen birleşimleri `data/` altına kaydeder.
2. Değişiklikleri repoya commit'ler.
3. Siteyi üretip GitHub Pages'te yayınlar.

**Actions → "Tutanakları güncelle ve yayınla" → Run workflow** ile elle de çalıştırılabilir. Dönem ve yasama
yılı girilirse o yılı geriye dönük indirir (ör. dönem `26`, yıl `2`).

İlk kurulumda **Settings → Pages → Source: GitHub Actions** seçilmelidir.

## Yerelde çalışma

```bash
python tbmm_tutanak.py                       # günlük tarama + siteyi üret
python tbmm_tutanak.py --donem 28 --yil 4    # bir yasama yılını geriye dönük indir
python tbmm_tutanak.py --dry-run             # neyin yeni olduğunu göster, kaydetme
python tbmm_tutanak.py --orijinaller         # PDF/DOCX/HTML orijinallerini de orijinal/ altına indir
python arayuz.py                             # sadece siteyi yeniden üret
```

Site `site/index.html` dosyasından doğrudan açılır.

## Veri yapısı

```
data/donem28/yil4/birlesim125/
  meta.json     kimlik, tarih, durum, TBMM'deki orijinal dosyaların adresleri
  tutanak.txt   tutanak metni
  ozet.txt      tutanak özeti
  oylama.json   açık oylamalar: başlık, sonuç, toplamlar ve
                oylar: [il, soyadı, adı, parti, sistem, pusula, sonuç, tarih, saat]
data/sira_sayilari/donem28/290.json
                oylanan teklifin komisyon raporu: PDF adresi, Kanun No, genel gerekçe,
                resmi liste (esaslar), amaç cümleleri, madde gerekçeleri
state.json      hangi birleşimin hangi durumda işlendiği
```

100 MB'ı aşan raporların (bütçe, kesin hesap) gerekçesi çıkarılmaz; sitede rapora bağlantı verilir.
PDF ve Word dosyaları repoya konmaz; site bunlar için TBMM'nin kendi bağlantılarını verir. Eski dönemlerin
bazılarında (ör. 26. Dönem) tutanak metni yalnızca PDF olarak yayınlanmıştır. Bu birleşimlerde özet ve oylamalar
yine işlenir, metin için PDF bağlantısı gösterilir.

## Güvenlik

Repoda sır yoktur. `firebase-web.json` içindeki Firebase web anahtarı ve reCAPTCHA site anahtarı tasarım gereği
herkese açıktır (sitenin kaynağında da görünür); koruma aşağıdaki kısıtlamalarla sağlanır.

**Firebase / Google Cloud (meclis-ce5d2)**
- API anahtarı yalnızca `firatersin.github.io` ve `meclis-ce5d2.firebaseapp.com`'dan, yalnızca Identity Toolkit,
  Token Service, Firestore ve App Check API'leri için çalışır.
- App Check (reCAPTCHA Enterprise) Firestore ve Authentication için **zorunlu**: istek gerçek siteden gelmiyorsa reddedilir.
- Yetkili giriş alan adları: yalnızca site ve Firebase giriş sayfası (`localhost` kapalı; yerel geliştirmede
  geçici olarak eklenip sonra kaldırılmalı).
- Firestore kuralları (`firestore.rules`): yalnızca e-postası doğrulanmış ya da telefonla giriş yapmış kullanıcı,
  yalnızca kendi iki belgesine erişir; listeleme kapalı; e-posta/telefon değiştirilemez; zaman damgaları sunucudan.
- Firestore `eur3` (Avrupa), silme koruması açık. Faturalandırma kapalı (Spark): kötüye kullanım ücret doğuramaz.
- E-posta numaralandırma koruması açık; SMS hiçbir ülkeye açık değil (telefon girişi kapalı).

**GitHub**
- İş akışında varsayılan yetki yok; tarama işi yalnızca `contents: write`, yayın işi yalnızca Pages yetkisi alır.
- Eylemler commit kimliğine sabit; `pypdf` sürüm ve sağlama toplamıyla sabit; Dependabot haftalık günceller.
- Yalnızca GitHub'ın kendi eylemleri çalışabilir; varsayılan iş akışı jetonu salt okunur.
- Sır tarama ve push koruması açık; `main` silinemez ve zorla push edilemez.

**Site**
- Her sayfada İçerik Güvenliği Politikası: satır içi betikler SHA-256 özetiyle sabit, başka betik çalışmaz;
  dış kaynak yalnızca giriş sayfasında (Firebase, reCAPTCHA).
- Dış bağlantılar yalnızca `https://*.tbmm.gov.tr`; giriş sayfası başka sitenin çerçevesinde açılmaz.

**Denetim ve testler** (`tools/guvenlik/`, proje sahibinin `firebase login` oturumuyla çalışır):
```bash
node tools/guvenlik/denetim.js                                  # ayarların salt okunur dökümü
node tools/guvenlik/kural_testi.js firebase-web.json            # 19 senaryoluk Firestore kural testi
node tools/guvenlik/appcheck_testi.js firebase-web.json         # App Check zorunluluğu testi
node tools/guvenlik/temizle.js                                  # testlerden kalan her şeyi siler
```
Testler geçici `@example.com` hesapları ve geçici App Check belgeleri oluşturup sonunda siler.

## Kaynak

Veriler [tbmm.gov.tr](https://www.tbmm.gov.tr/Tutanaklar/TutanakMetinleri) üzerinde kamuya açık olarak yayınlanan
tutanaklardan alınır. İstekler arasında bekleme süresi vardır ve günde iki kez çalışır.
