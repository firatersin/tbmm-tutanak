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
- **Okuma sitesi:** Tutanak ve oylamaları gün gün gösteren zaman çizelgesi, okunmamış işareti, arama. Tutanak
  sayfasında konuşmacıya atlama, içindekiler, özet ve alınan kararlar.

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

## Kaynak

Veriler [tbmm.gov.tr](https://www.tbmm.gov.tr/Tutanaklar/TutanakMetinleri) üzerinde kamuya açık olarak yayınlanan
tutanaklardan alınır. İstekler arasında bekleme süresi vardır ve günde iki kez çalışır.
