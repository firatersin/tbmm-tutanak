# TBMM Tutanak Takip

TBMM Genel Kurul tutanaklarını ve açık oylama sonuçlarını her gün otomatik olarak çeker. Hepsini tarih sırasına
dizen, sunucusuz bir okuma sitesi üretir.

- **Tutanaklar:** Yeni birleşimler ve durum geçişleri (Ham → Tam → Basılmış) takip edilir. Kesin hâl
  yayınlandığında metin güncellenir.
- **Açık oylamalar:** Her oylamanın sonucu, toplamları, parti bazında dağılımı ve milletvekili bazında oy dökümü.
- **Okuma sitesi:** Tutanak ve oylamaları gün gün gösteren zaman çizelgesi, okunmamış işareti, arama. Tutanak
  sayfasında konuşmacıya atlama, içindekiler, özet ve alınan kararlar.

Yalnızca Python standart kütüphanesi kullanılır; kurulacak paket yok.

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
state.json      hangi birleşimin hangi durumda işlendiği
```

PDF ve Word dosyaları repoya konmaz; site bunlar için TBMM'nin kendi bağlantılarını verir. Eski dönemlerin
bazılarında (ör. 26. Dönem) tutanak metni yalnızca PDF olarak yayınlanmıştır. Bu birleşimlerde özet ve oylamalar
yine işlenir, metin için PDF bağlantısı gösterilir.

## Kaynak

Veriler [tbmm.gov.tr](https://www.tbmm.gov.tr/Tutanaklar/TutanakMetinleri) üzerinde kamuya açık olarak yayınlanan
tutanaklardan alınır. İstekler arasında bekleme süresi vardır ve günde iki kez çalışır.
