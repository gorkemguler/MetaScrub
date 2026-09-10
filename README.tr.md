<p align="center">
  <img src="assets/banner.svg" alt="MetaScrub" width="100%">
</p>

<p align="center">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-2dd4a7.svg">
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-2dd4a7.svg">
  <img alt="Platforms" src="https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-7dd88f.svg">
  <img alt="Status" src="https://img.shields.io/badge/status-aktif%20geli%C5%9Ftirme-f6c454.svg">
</p>

<p align="center">
  PDF, Office ve görsel dosyalarından toplu metadata temizliği.<br>
  Metadata'yı sil, belgeyi koru — öncesi/sonrası kanıt raporuyla.
</p>

<p align="center">
  <sub><a href="https://github.com/gorkemguler/MetaScout">MetaScout</a> ile birlikte çalışır: MetaScout sızıntıyı <i>bulur</i>, MetaScrub <i>giderir</i>.</sub>
</p>

<p align="center"><sub><a href="README.md">🇬🇧 English</a> · 🇹🇷 Türkçe</sub></p>

<p align="center">
  <img src="assets/screenshot-report.png" alt="MetaScrub öncesi/sonrası raporu — 3 dosya, 18 metadata alanı silindi, 0 artık" width="90%">
</p>

---

## Bu nedir?

Bir kurum kendi sitesine karşı MetaScout çalıştırır ve internete açılmış bir yığın PDF/Office
belgesinin yazar adı, iç dosya yolu, yazılım/OS parmak izi ve GPS koordinatı sızdırdığını
görür. Şimdi birilerinin bu dosyaları **gerçekten temizlemesi** gerekir. İşte MetaScrub bu.

Bir klasöre yönlendirin (ya da web arayüzüne dosya sürükleyin, ya da API'ye POST edin) ve:

1. Desteklenen her dosyada gömülü metadata'yı **tarar**,
2. Varsayılan olarak **agresif** biçimde **siler** — temizlenmiş kopyalar yazar (orijinaller
   dokunulmaz) ya da yerinde üzerine yazar,
3. Her temizlenmiş dosyayı yeniden tarayarak **doğrular**, ve
4. Dosya bazında ne silindiğini JSON ve şık bir HTML sayfası olarak **raporlar** — güvenlik
   ekibine kanıt olarak verebilirsiniz.

Yalnızca **metadata**'ya dokunur — belgenin görünür içeriği (gövde metni, görseller, taranmış
imza) asla değiştirilmez.

## Ne siler?

| Biçim | Motor | Silinen |
| --- | --- | --- |
| **PDF** | [pikepdf](https://github.com/pikepdf/pikepdf) (QPDF) | `/Info` sözlüğü (Author, Title, Producer, Creator, CreationDate, …), XMP metadata paketi, `/PieceInfo` ve diğer uygulamaya özel veriler, sayfa düzeyi metadata, annotation yazar + zaman damgaları (`/T` `/M` `/CreationDate`), ve gömülü dosya eklerinin açıklama + zaman damgaları. Dosya **tamamen yeniden yazılır**, böylece eski xref bölümlerinde kalan değerler çıktıdan kurtarılamaz. Şifreli PDF'ler `--password` ister. |
| **Office** `.docx .xlsx .pptx` | stdlib `zipfile` | `docProps/core.xml` (creator, lastModifiedBy, revizyon, zaman damgaları), `docProps/app.xml` (Company, Manager, Template yolu), `docProps/custom.xml`, gömülü küçük resim, ve `settings.xml`'deki Word revizyon-kayıt-kimliği parmak izleri (`w:rsids`). Dangling ilişki ve content-type override'ları temizlenir; dosya bazlı zip zaman damgaları normalize edilir. |
| **OpenDocument** `.odt .ods .odp` | stdlib `zipfile` | `meta.xml` — initial-creator, creator, generator, editing-cycles/duration, zaman damgaları, belge istatistikleri, kullanıcı tanımlı alanlar. |
| **Eski Office** `.doc .xls .ppt` | `olefile` (saf Python) | `\x05SummaryInformation` / `\x05DocumentSummaryInformation` property akışları — yazar, son kaydeden, şirket, yönetici, şablon, başlık, zaman damgaları, özel özellikler — **yerinde** yamalanır: aynı boyut, aynı biçim, aynı yapı. `--in-place` çalışır. Bir konteyner ayrıştırılamazsa MetaScrub LibreOffice (`soffice`) ile `.docx/.xlsx/.pptx`'e yeniden render'a düşer. |
| **SVG** `.svg` | stdlib `xml` | `<metadata>` (RDF/Dublin-Core yazar/başlık/lisans), `sodipodi:` / `inkscape:` / Adobe-Illustrator element ve öznitelikleri, ve editör yorumları (`<!-- Created with … -->`). Çizimin kendisine dokunulmaz. |
| **Görseller** `.jpg .jpeg .png .tif .tiff .heic .webp` | [ExifTool](https://exiftool.org) | Tüm EXIF / IPTC / XMP / GPS / MakerNotes ve PNG/WebP metin blokları. ICC renk profili ve EXIF yönlendirmesi varsayılan olarak korunur ki görsel doğru görünsün (`--no-keep-color-profile` / `--no-keep-orientation` ile onlar da silinir). |

`--keep Title` (tekrarlanabilir) belirtilen bir alanı agresif temizlikten muaf tutar.
`--backup`, `--in-place` temizlikte `<ad>.orig` bırakır.

İki **opt-in** bayrak metadata'nın ötesine, teknik olarak içerik olan kimlik verisine geçer:
`--strip-form-values` PDF form alanı değerlerini (`/V` `/DV`) ve önbellekli görünümlerini boşaltır;
`--strip-office-authors` Office değişiklik-takibi / yorum **yazar adları ve tarihlerini** boşaltır
(değişiklik ve yorum metni kalır, kabul/ret hâlâ çalışır).

## Kurulum

```bash
pip install metascrub                     # çekirdek: PDF + Office temizliği
pip install 'metascrub[api]'              # + REST API servisi
pip install 'metascrub[image-fallback]'   # + Pillow (exiftool yoksa zayıf görsel yedeği)
```

Görsel temizliği için **exiftool** binary'si `PATH`'te olmalı:

```bash
brew install exiftool                        # macOS
sudo apt install libimage-exiftool-perl      # Debian / Ubuntu
```

PDF, Office (modern **ve** eski `.doc/.xls/.ppt`), ODF ve SVG temizliği saf Python'dur, ek
bir şey gerekmez. **LibreOffice** (`soffice`) yalnızca yerinde yamalayıcının
ayrıştıramadığı eski bir konteyner için yedek olarak kullanılır.

> Python 3.10+ desteklenir. `pikepdf` için henüz wheel'i olmayan yepyeni bir Python'da 3.12
> altında kurun.

## CLI

<p align="center">
  <img src="assets/screenshot-cli.svg" alt="terminalde metascrub inspect ve metascrub clean" width="90%">
</p>

### Inspect — dosyalarda ne var, göster (salt-okunur)

```bash
metascrub inspect ./yayinlanan-belgeler
metascrub inspect sizinti.pdf rapor.docx --json
```

Temizlemeden önce, MetaScout'un işaretlediği dosyalarda tam olarak ne olduğunu görmek için bunu çalıştırın.

### Clean (temizle)

```bash
# varsayılan: orijinaller dokunulmaz, temizlenmiş kopyalar ./metascrub_cleaned/ altına
# girdi ağacını yansıtarak yazılır + report.json + report.html
metascrub clean ./yayinlanan-belgeler

# bunun yerine orijinallerin üzerine yaz (önce sorar; -y ile atlanır)
metascrub clean ./yayinlanan-belgeler --in-place

# yalnızca önizleme, hiçbir şey değiştirme
metascrub clean ./yayinlanan-belgeler --dry-run

# belge başlıklarını koru, Türkçe rapor
metascrub clean ./yayinlanan-belgeler --keep Title --report-lang tr

# sadece bazı dosyalar
metascrub clean a.pdf b.docx c.jpg --out ./temiz
```

Faydalı bayraklar: `--filetypes`, `--no-recursive`, `--out DIR`, `--keep FIELD`, `--dry-run`,
`--no-verify`, `--no-keep-color-profile`, `--no-keep-orientation`, `--report-lang en|tr`,
`--password` (şifreli PDF'ler — temizlenmiş kopya şifresiz yazılır),
`--strip-pdf-id` (her çalıştırmada taze rastgele `/ID`), `--backup` (`--in-place` ile `<ad>.orig` sakla),
`--strip-form-values`, `--strip-office-authors` (opt-in — yukarıya bakın).

**Çıkış kodları** (CI kapısı olarak kullanılabilsin diye): `0` temiz · `1` bir dosya hata
verdi · `2` bir temizlenmiş dosya doğrulama taramasında hâlâ metadata taşıyordu.

## Web arayüzü

```bash
metascrub web           # http://127.0.0.1:8770/ açılır
```

Dosyaları sayfaya sürükleyin, temizlenmiş halde geri alın — tek tek ya da zip olarak — dosya
bazında öncesi/sonrası görünümü ve tam raporla birlikte. Önceki çalıştırmalar **Geçmiş**
altında listelenir. Yerel, tek kullanıcılık, **kimlik doğrulama yok** — ağa açmayın.

<p align="center">
  <img src="assets/screenshot-web.png" alt="MetaScrub yerel web arayüzü — sürükle-bırak dosya alanı" width="90%">
</p>

## REST API

Linux sunucusu, FTP bırakma kutusu, ya da temizlenmesi için dosya devreden bir CI hattı için:

```bash
pip install 'metascrub[api]'
metascrub api           # http://127.0.0.1:8000/  ·  interaktif dokümanlar /docs
```

```bash
# gönder
curl -sS -X POST http://127.0.0.1:8000/v1/clean \
  -F files=@sizinti.pdf -F files=@rapor.docx -F report_lang=tr
# -> {"job_id": "...", "links": {...}}

# durum sorgula
curl -sS http://127.0.0.1:8000/v1/clean/<job_id>

# temizlenmiş dosyaları + raporu zip olarak çek
curl -sSL -o temiz.zip http://127.0.0.1:8000/v1/clean/<job_id>/download
```

İşler sınırlı bir arka plan thread havuzunda çalışır; `--max-workers` / `--max-pending` ile
boyutlandırılır. **Yerleşik kimlik doğrulama yoktur** — önüne API anahtarı / mTLS'li bir
reverse proxy koyun, ya da yalnızca özel (Tailscale/WireGuard) bir ağda çalıştırın.

## Docker

```bash
docker build -t metascrub .

# web arayüzü
docker run --rm -p 127.0.0.1:8770:8770 -v "$(pwd)/metascrub_cleaned:/data" metascrub

# REST API
docker run --rm -p 127.0.0.1:8000:8000 -v "$(pwd)/metascrub_cleaned:/data" metascrub \
  api --host 0.0.0.0 --port 8000 --output-dir /data

# tek seferlik: bağlanmış bir klasörü temizle
docker run --rm -v "$(pwd)/belgeler:/work" metascrub clean /work --out /work/cleaned
```

Ya da `docker compose up --build` (web arayüzü); `docker compose --profile api up metascrub-api` (API).

## Ne kadar kapsamlı?

- **PDF** — incremental update değil, tam bir QPDF yeniden yazımı; böylece silinen `/Info` ve
  XMP eski bir xref bölümünde geride kalmaz. Annotation yazar/tarihleri ve gömülü-dosya
  metadata'sı da gider; annotation'ın görünür metni ve ekli dosyanın kendisi kalır.
  **İmzalı PDF'ler bozulmadan atlanır** — temizlik imzayı geçersiz kılardı; temizlenmiş hali
  gerekiyorsa imzasız bir kopya yeniden dışa aktarın. **Şifreli PDF'ler** `--password`
  olmadan atlanır; onunla, temizlenmiş kopya şifresiz yazılır (sonuç bunu belirtir).
- **Office / ODF** — metadata parçaları pakette yalnızca boşaltılmaz, silinir (ODF'de
  boşaltılır) ve onlara giden referanslar temizlenir ki hiçbir şey boşa sarkmasın.
- **Görseller** — bu iş için referans araç olan `exiftool -all=`.
- **`--verify`** (varsayılan açık) her temizlenmiş dosyayı yeniden tarar ve hâlâ duran her şeyi
  rapora yazar; öyleyse CLI `2` ile çıkar.

### Sınırlamalar

- İçerik tasarım gereği kapsam dışı: belge gövdesindeki metin, görünür/taranmış imza, bir
  görselin içine gömülü metin — MetaScrub bunlara dokunmaz. (MetaScout'un `--scan-content`'i
  bunları bulur; kaldırılması manuel bir düzenlemedir.)
- Eski `.doc / .xls / .ppt` temizlenmez (önce dönüştürün).
- Sertifikalı bir sanitizasyon aracı değildir. Kritik işlerde çıktıyı kendiniz doğrulayın —
  `metascrub inspect` ile ya da MetaScout ile ikinci bir geçiş tam da bunun içindir.

## Yol haritası

Tüm yapılacaklar listesi ve v0.1'in bilinen sınırlamaları için **[ROADMAP.tr.md](ROADMAP.tr.md)**.
Başlıklar: daha derin PDF/Office kapsamı, eski `.doc/.xls/.ppt`, API kimlik doğrulaması,
SFTP/FTP bırakma dizinleri için `metascrub watch` daemon'u, macOS Finder Quick Action,
Windows Explorer girdisi, ve pre-commit hook + GitHub Action.

## Lisans

MIT — bkz. [LICENSE](LICENSE).
