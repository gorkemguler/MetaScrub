<p align="center">
  <img src="https://raw.githubusercontent.com/gorkemguler/MetaCLS/main/assets/banner.svg" alt="MetaCLS" width="100%">
</p>

<p align="center">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-2dd4a7.svg">
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-2dd4a7.svg">
  <img alt="Platforms" src="https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-7dd88f.svg">
  <img alt="Status" src="https://img.shields.io/badge/status-aktif%20geli%C5%9Ftirme-f6c454.svg">
</p>

<p align="center">
  PDF, Office ve görsel dosyalarından toplu metadata temizliği.<br>
  Metadata'yı sil, belgeyi koru, öncesi/sonrası kanıt raporuyla.
</p>

<p align="center">
  <sub><a href="https://github.com/gorkemguler/MetaScout">MetaScout</a> ile birlikte çalışır: MetaScout sızıntıyı <i>bulur</i>, MetaCLS <i>giderir</i>.</sub>
</p>

<p align="center"><sub><a href="https://github.com/gorkemguler/MetaCLS/blob/main/README.md">🇬🇧 English</a> · 🇹🇷 Türkçe</sub></p>

<p align="center">
  <img src="https://raw.githubusercontent.com/gorkemguler/MetaCLS/main/assets/screenshot-report.png" alt="MetaCLS öncesi/sonrası raporu, 3 dosya, 18 metadata alanı silindi, 0 artık" width="90%">
</p>

---

## Bu nedir?

Bir kurum kendi sitesine karşı MetaScout çalıştırır ve internete açılmış bir yığın PDF/Office
belgesinin yazar adı, iç dosya yolu, yazılım/OS parmak izi ve GPS koordinatı sızdırdığını
görür. Şimdi birilerinin bu dosyaları **gerçekten temizlemesi** gerekir. İşte MetaCLS bu.

Bir klasöre yönlendirin (ya da web arayüzüne dosya sürükleyin, ya da API'ye POST edin) ve:

1. Desteklenen her dosyada gömülü metadata'yı **tarar**,
2. Varsayılan olarak **agresif** biçimde **siler**, temizlenmiş kopyalar yazar (orijinaller
   dokunulmaz) ya da yerinde üzerine yazar,
3. Her temizlenmiş dosyayı yeniden tarayarak **doğrular**, ve
4. Dosya bazında ne silindiğini JSON ve şık bir HTML sayfası olarak **raporlar**, güvenlik
   ekibine kanıt olarak verebilirsiniz.

Yalnızca **metadata**'ya dokunur: belgenin görünür içeriği (gövde metni, görseller, taranmış
imza) asla değiştirilmez.

## Ne siler?

| Biçim | Motor | Silinen |
| --- | --- | --- |
| **PDF** | [pikepdf](https://github.com/pikepdf/pikepdf) (QPDF) | `/Info` sözlüğü (Author, Title, Producer, Creator, CreationDate, …), XMP metadata paketi, `/PieceInfo` ve diğer uygulamaya özel veriler, sayfa düzeyi metadata, annotation yazar + zaman damgaları (`/T` `/M` `/CreationDate`), ve gömülü dosya eklerinin açıklama + zaman damgaları. Dosya **tamamen yeniden yazılır**, böylece eski xref bölümlerinde kalan değerler çıktıdan kurtarılamaz. Şifreli PDF'ler `--password` ister. `--strip-form-values` ile: AcroForm alan değerleri ve XFA `<xfa:data>` paketi de. |
| **Office** `.docx .xlsx .pptx` (+ makro içeren `.docm .xlsm .pptm` ve şablonlar `.dotx .dotm .xltx .xltm .potx .potm`) | stdlib `zipfile` | `docProps/core.xml` (creator, lastModifiedBy, revizyon, zaman damgaları), `docProps/app.xml` (Company, Manager, Template yolu), `docProps/custom.xml`, gömülü küçük resim, ve `settings.xml`'deki Word revizyon-kayıt-kimliği parmak izleri (`w:rsids`). Dangling ilişki ve content-type override'ları temizlenir; dosya bazlı zip zaman damgaları normalize edilir. `vbaProject.bin` **korunur** (makroyu bozmak, içinde bir isim saklanma ihtimalinden kötüdür) ve rapor dosyanın kısmen temizlendiğini bildirir. |
| **OpenDocument** `.odt .ods .odp` | stdlib `zipfile` | `meta.xml`: initial-creator, creator, generator, editing-cycles/duration, zaman damgaları, belge istatistikleri, kullanıcı tanımlı alanlar, ayrıca `Thumbnails/` önizleme görseli (ilk sayfanın render edilmiş anlık görüntüsü) ve `META-INF/manifest.xml` içindeki girdisi. |
| **Eski Office** `.doc .xls .ppt` | `olefile` (saf Python) | `\x05SummaryInformation` / `\x05DocumentSummaryInformation` property akışları (yazar, son kaydeden, şirket, yönetici, şablon, başlık, zaman damgaları, özel özellikler) **yerinde** yamalanır: aynı boyut, aynı biçim, aynı yapı. `--in-place` çalışır. Bir konteyner ayrıştırılamazsa MetaCLS LibreOffice (`soffice`) ile `.docx/.xlsx/.pptx`'e yeniden render'a düşer. |
| **SVG** `.svg` | stdlib `xml` | `<metadata>` (RDF/Dublin-Core yazar/başlık/lisans), `sodipodi:` / `inkscape:` / Adobe-Illustrator element ve öznitelikleri, ve editör yorumları (`<!-- Created with … -->`). Çizimin kendisine dokunulmaz. |
| **Görseller** `.jpg .jpeg .png .gif .tif .tiff .heic .heif .webp` | [ExifTool](https://exiftool.org) | Tüm EXIF / IPTC / XMP / GPS / MakerNotes, PNG/WebP metin blokları ve JPEG/GIF yorum bloğu. ICC renk profili ve EXIF yönlendirmesi varsayılan olarak korunur (`--no-keep-color-profile` / `--no-keep-orientation` ile onlar da silinir). exiftool yoksa HEIC `pillow-heif` ile de çalışır. |
| **Ses / video** `.mp3 .m4a .flac .ogg .opus .wav .aiff` / `.mp4 .mov .m4v .3gp .mkv .webm .avi` | `mutagen` / ExifTool / saf Python | Ses: tüm etiketler (ID3 / Vorbis / iTunes) ve gömülü kapak resmi, `pip install 'metacls[media]'`. MP4 ailesi video: exiftool metadata atom'larını temizler (`ItemList`, `Keys`, `UserData`, XMP, sanatçı, telefondan `Make`/`Model`, GPS, `CreationDate`). **Matroska / WebM / AVI** (exiftool bunlara yazamaz): tüm EBML `Tags` bloğu ve `Info` başlığı / tarihleri / muxer-ve-writer uygulama adları yerinde boşaltılır, aynı uzunlukta `Void` / `JUNK` dolgusuyla üzerine yazılır, böylece dosya uzunluğu değişmez ve `--in-place` çalışır; track verisine dokunulmaz. Varsayılan taranmaz, **`--media`** verin (ya da uzantıları `--filetypes`'a ekleyin). Oynatmayı kontrol edin. |
| **Konteynerler** `.zip .eml .tar .tar.gz .tgz .tar.bz2 .tar.xz .7z .msg` | stdlib `zipfile` / `tarfile` / `email`; `py7zr` / `extract-msg` (opsiyonel) | **`--recurse`** ile: bir arşivin desteklenen her üyesi ve bir e-postanın her eki kendi motoruyla temizlenir, arşiv/mesaj yeniden paketlenir. `.tar*` ayrıca üye başına uid/gid/kullanıcı-adı/mtime başlıklarını normalize eder (paketleyenin kimlik sızıntısı). `.7z` için `pip install 'metacls[archive]'` gerekir. `.msg` (Outlook) **salt-okunur**: `metacls inspect --recurse` içindekileri listeler (`metacls[msg]` gerekir); temizlemek için `.eml`'e aktarın. Temizlenemeyen üyeler dokunulmadan geçer. İç içe konteynerler izlenir (derinlik sınırlı). |

`--keep Title` (tekrarlanabilir) belirtilen bir alanı agresif temizlikten muaf tutar.
`--backup`, `--in-place` temizlikte `<ad>.orig` bırakır.

İki **opt-in** bayrak metadata'nın ötesine, teknik olarak içerik olan kimlik verisine geçer:
`--strip-form-values` PDF form değerlerini boşaltır, AcroForm alanları (`/V` `/DV`) ve önbellekli
görünümleri, artı bir XFA formunun `<xfa:data>` paketi (XFA şablonu ve şeması korunur);
`--strip-office-authors` Office değişiklik-takibi / yorum **yazar adları ve tarihlerini** boşaltır
(değişiklik ve yorum metni kalır, kabul/ret hâlâ çalışır).

## Kurulum

```bash
pip install metacls                     # çekirdek: PDF + Office temizliği
pip install 'metacls[api]'              # + REST API servisi
pip install 'metacls[media]'            # + ses etiketi temizliği (mutagen)
pip install 'metacls[archive]'          # + .7z özyinelemesi (py7zr)
pip install 'metacls[msg]'              # + salt-okunur .msg incelemesi (extract-msg)
pip install 'metacls[image-fallback]'   # + Pillow (exiftool yoksa zayıf görsel yedeği)
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
  <img src="https://raw.githubusercontent.com/gorkemguler/MetaCLS/main/assets/screenshot-cli.svg" alt="terminalde metacls inspect ve metacls clean" width="90%">
</p>

### Inspect: dosyalarda ne var, göster (salt-okunur)

```bash
metacls inspect ./yayinlanan-belgeler
metacls inspect sizinti.pdf rapor.docx --json
```

Temizlemeden önce, MetaScout'un işaretlediği dosyalarda tam olarak ne olduğunu görmek için bunu çalıştırın.

### Clean (temizle)

```bash
# varsayılan: orijinaller dokunulmaz, temizlenmiş kopyalar ./metacls_cleaned/ altına
# girdi ağacını yansıtarak yazılır + report.json + report.html
metacls clean ./yayinlanan-belgeler

# bunun yerine orijinallerin üzerine yaz (önce sorar; -y ile atlanır)
metacls clean ./yayinlanan-belgeler --in-place

# yalnızca önizleme, hiçbir şey değiştirme
metacls clean ./yayinlanan-belgeler --dry-run

# belge başlıklarını koru, Türkçe rapor
metacls clean ./yayinlanan-belgeler --keep Title --report-lang tr

# sadece bazı dosyalar
metacls clean a.pdf b.docx c.jpg --out ./temiz
```

Faydalı bayraklar: `--filetypes`, `--no-recursive`, `--out DIR`, `--keep FIELD`, `--dry-run`,
`--no-verify`, `--no-keep-color-profile`, `--no-keep-orientation`, `--report-lang en|tr`,
`--password` (şifreli PDF'ler), `--strip-pdf-id`, `--backup` (`--in-place` ile `<ad>.orig` sakla),
`--strip-form-values`, `--strip-office-authors` (opt-in, yukarıya bakın),
`--jobs N` (N dosyayı paralel temizle), `--quarantine DIR` (orijinali üzerine yaz ama önce
`DIR/<tarih>/`'e taşı, kurtarılabilir, `--in-place`'ten güvenli),
`--policy publish|internal|minimal` (adlandırılmış presetler),
`--exclude GLOB` (tekrarlanabilir, gezerken dosya/dizin atla),
`--no-follow-symlinks` (sembolik bağlı dosyayı temizleme), `--progress` (ilerleme çubuğu), ve
grup düzeyinde `metacls --debug …` (ilk hatalı dosyada hatayı kaydetmek yerine yeniden fırlat).

`metacls inspect` da `--media` ve `--recurse` alır; bir arşive ya da videoya işaret edip
temizlemeden önce içindekileri görebilirsin.

**Proje yapılandırması:** çalışma dizininde ya da bir üstünde (git köküne kadar) bir
`.metacls.toml` komut başına varsayılanları belirler; CLI bayrakları ve env değişkenleri
yine kazanır.

```toml
[clean]
strip-office-authors = true
jobs = 4
keep = ["Title"]
```

**Çıkış kodları** (CI kapısı olarak): `0` temiz · `1` bir dosya hata verdi · `2` temizlenmiş
dosya doğrulamada hâlâ metadata taşıyordu · `3` (`--check`) metadata bulundu.

### Diff: bir dizini zaman içinde izle

```bash
metacls clean ./yayin --out ./tarama-ocak     # ayda bir, tarihli dizinlere
metacls clean ./yayin --out ./tarama-subat
metacls diff ./tarama-ocak ./tarama-subat     # ne değişti?
```

İki çalıştırma arasında eklenen/silinen dosyaları ve, asıl faydalı kısım, metadata'sı
**yeniden ortaya çıkan** dosyaları (birisi belgeyi editörde tekrar kaydetmiş) gösterir.
Bir şey metadata geri kazandıysa çıkış kodu `1`: bir cron işine koyun.

### Watch: bir bırakma klasörünü temiz tut

```bash
metacls watch /srv/ftp/incoming --move-processed /srv/ftp/scrubbed --interval 10 --settle 5
metacls watch ./inbox --once                       # tek geçiş, cron için
metacls watch ./inbox --pattern 'invoice-*.pdf' -j 4   # filtre + paralel birikim
```

Bir FTP/SFTP iniş bölgesi için poll döngüsü: bir dosyaya ancak `--settle` saniye boyunca
değişmeyi bıraktıktan sonra dokunulur (yarım kalmış yükleme asla temizlenmez), durum
`<dir>/.metacls-watch.json`'da tutulur (yeniden başlatma her şeyi yeniden işlemez), ve
daha yeni bir zaman damgasıyla tekrar bırakılan dosya yeniden işlenir. `.metacls-watch.lock`
dosyası aynı dizine ikinci bir watcher'ı sokmaz (ölü bir sürecin bıraktığı kilit çalınır).
`--pattern GLOB` (tekrarlanabilir) neyin alınacağını daraltır; `-j/--jobs N` birikmiş işi
paralel temizler; artık var olmayan dosyaların durum kayıtları her geçişte budanır. Varsayılan
yerinde temizler; `--to DIR` yerine temizlenmiş kopya yazar. systemd şablon unit'i
[`platform/linux/`](https://github.com/gorkemguler/MetaCLS/blob/main/platform/linux/metacls-watch@.service)'de.

## Web arayüzü

```bash
metacls web           # http://127.0.0.1:8770/ açılır
```

Dosyaları sayfaya sürükleyin, temizlenmiş halde geri alın, tek tek ya da zip olarak, dosya
bazında öncesi/sonrası görünümü ve tam raporla birlikte. Önceki çalıştırmalar **Geçmiş**
altında listelenir. Yerel, tek kullanıcılık, **kimlik doğrulama yok**. Ağa açmayın.

<p align="center">
  <img src="https://raw.githubusercontent.com/gorkemguler/MetaCLS/main/assets/screenshot-web.png" alt="MetaCLS yerel web arayüzü, sürükle-bırak dosya alanı" width="90%">
</p>

Sayfada ikinci bir form daha var: **Ya da FTP'den çek**. Bir sunucu adresi, uzak
dizin ve isteğe bağlı kullanıcı bilgisi verin; MetaCLS eşleşen tüm dosyaları FTP
ya da FTPS üzerinden çeker, temizler ve aynı öncesi/sonrası raporunu gösterir —
elle indirip yükleme derdi yok. Parola yalnızca o istek için kullanılır, hiçbir
yerde saklanmaz ya da loglanmaz. İsteğe bağlı bir onay kutusu, temizlenmiş
kopyaları doğrudan aynı uzak yollara geri yükleyip orijinallerin üzerine yazar.

## REST API

Linux sunucusu, FTP bırakma kutusu, ya da temizlenmesi için dosya devreden bir CI hattı için:

```bash
pip install 'metacls[api]'
metacls api           # http://127.0.0.1:8000/  ·  interaktif dokümanlar /docs
```

```bash
# bu sunucu neyi temizleyebilir, hangi opsiyonel araçlar yüklü?
curl -sS http://127.0.0.1:8000/v1/formats

# gönder  (recurse: .zip/.tar/.7z/.eml içine bak · media: ses/video de)
curl -sS -X POST http://127.0.0.1:8000/v1/clean \
  -F files=@sizinti.pdf -F files=@rapor.docx -F report_lang=tr -F recurse=true
# -> {"job_id": "...", "links": {...}}

# durum sorgula
curl -sS http://127.0.0.1:8000/v1/clean/<job_id>

# temizlenmiş dosyaları + raporu zip olarak çek
curl -sSL -o temiz.zip http://127.0.0.1:8000/v1/clean/<job_id>/download
```

İşler sınırlı bir arka plan thread havuzunda çalışır; `--max-workers` / `--max-pending` ile
boyutlandırılır. Yüklemeler `--max-upload-mb` / `--max-files` sınırlarıyla diske akıtılır.
`GET /v1/formats` ve `GET /v1/health`, API anahtarı ayarlı olsa bile açıktır.

**Kimlik doğrulama:** `metacls api --api-key ANAHTAR` (ya da `METACLS_API_KEY`) bu
anahtarı `/v1/health` ve `/v1/formats` dışında her `/v1` route'unda ister, `X-API-Key:
ANAHTAR` ya da `Authorization: Bearer ANAHTAR` olarak gönderin. Hem `api` hem `web`, kimlik
doğrulama yokken **loopback-dışı bir host'a bağlanmayı reddeder** (`0.0.0.0`, bir LAN IP'si);
desteklenen yol `127.0.0.1`'e bağlayıp önüne bir ters proxy koymaktır.
**[docs/reverse-proxy.md](https://github.com/gorkemguler/MetaCLS/blob/main/docs/reverse-proxy.md)** hazır nginx / Caddy yapılandırmaları içerir.

## Docker

Yayınlanmış imajı çekin (her sürümde amd64 + arm64 için derlenir):

```bash
docker pull ghcr.io/gorkemguler/metacls:latest
```

```bash
# web arayüzü
docker run --rm -p 127.0.0.1:8770:8770 -v "$(pwd)/metacls_cleaned:/data" \
  ghcr.io/gorkemguler/metacls:latest

# REST API
docker run --rm -p 127.0.0.1:8000:8000 -v "$(pwd)/metacls_cleaned:/data" \
  ghcr.io/gorkemguler/metacls:latest api --host 0.0.0.0 --port 8000 --output-dir /data

# tek seferlik: bağlanmış bir klasörü temizle
docker run --rm -v "$(pwd)/belgeler:/work" ghcr.io/gorkemguler/metacls:latest \
  clean /work --out /work/cleaned
```

Ya da yerelde derleyin: `docker build -t metacls .`. `docker compose up --build` web
arayüzünü, `docker compose --profile api up metacls-api` API'yi çalıştırır. Açmadan önce
önüne proxy koyun: bkz. [docs/reverse-proxy.md](https://github.com/gorkemguler/MetaCLS/blob/main/docs/reverse-proxy.md).

## Ne kadar kapsamlı?

- **PDF**: incremental update değil, tam bir QPDF yeniden yazımı; böylece silinen `/Info` ve
  XMP eski bir xref bölümünde geride kalmaz. Annotation yazar/tarihleri ve gömülü-dosya
  metadata'sı da gider; annotation'ın görünür metni ve ekli dosyanın kendisi kalır.
  **İmzalı PDF'ler bozulmadan atlanır**: temizlik imzayı geçersiz kılardı; temizlenmiş hali
  gerekiyorsa imzasız bir kopya yeniden dışa aktarın. **Şifreli PDF'ler** `--password`
  olmadan atlanır; onunla, temizlenmiş kopya şifresiz yazılır (sonuç bunu belirtir).
- **Office / ODF**: metadata parçaları pakette yalnızca boşaltılmaz, silinir (ODF'de
  boşaltılır) ve onlara giden referanslar temizlenir ki hiçbir şey boşa sarkmasın.
- **Görseller**: bu iş için referans araç olan `exiftool -all=`.
- **`--verify`** (varsayılan açık) her temizlenmiş dosyayı yeniden tarar ve hâlâ duran her şeyi
  rapora yazar; öyleyse CLI `2` ile çıkar.

### Sınırlamalar

- İçerik tasarım gereği kapsam dışı: belge gövdesindeki metin, görünür/taranmış imza, bir
  görselin içine gömülü metin: MetaCLS bunlara dokunmaz. (MetaScout'un `--scan-content`'i
  bunları bulur; kaldırılması manuel bir düzenlemedir.)
- Eski `.doc / .xls / .ppt` temizlenmez (önce dönüştürün).
- Sertifikalı bir sanitizasyon aracı değildir. Kritik işlerde çıktıyı kendiniz doğrulayın: `metacls inspect` ile ya da MetaScout ile ikinci bir geçiş tam da bunun içindir.

## Masaüstü entegrasyonu

Hepsi **[`platform/`](https://github.com/gorkemguler/MetaCLS/tree/main/platform)** altında, her biri için tek kurulum komutu; hepsi
yerinde temizler:

- **macOS**: penceresiz sürükle-bırak `MetaCLS.app` (`osacompile` ile, Xcode yok),
  sonuç listeli bir **bırakma penceresi** olan `MetaCLS Drop.app` (PyObjC), ve bir
  Finder **Quick Action**.
- **Windows**: bir WinForms **bırakma penceresi**, bir **Gönder** menüsü girdisi, bir
  Explorer **sağ tık** girdisi ve bir `winget` manifesti (şablon).
- **Linux**: bir `.desktop` başlatıcı / *Birlikte Aç* işleyici (`zenity` seçici ile), bir
  Nautilus/Nemo/Caja **betiği** ve bir `systemd` **watch** unit'i.

<p align="center">
  <img src="https://raw.githubusercontent.com/gorkemguler/MetaCLS/main/assets/desktop-apps.svg" alt="macOS, Windows ve Linux için MetaCLS masaüstü uygulamalarının illüstrasyonu" width="90%">
</p>

## CI / hook'lar

`metacls clean --check`, `--dry-run` demektir ve bir dosya hâlâ metadata taşıyorsa **3**
ile çıkar (temizse 0, hatada 1), pre-commit ve CI için bir kapı.

```yaml
# .pre-commit-config.yaml
- repo: https://github.com/gorkemguler/MetaCLS
  rev: main
  hooks: [{ id: metacls }]
```

```yaml
# .github/workflows/no-metadata.yml
- uses: gorkemguler/MetaCLS@main
  with:
    paths: docs/ public/
    mode: check        # ya da yerinde temizleyip commit'lemek için "fix"
```

## Yol haritası

Nelerin geldiği, bilinen sınırlamalar ve backlog için **[ROADMAP.tr.md](https://github.com/gorkemguler/MetaCLS/blob/main/ROADMAP.tr.md)**
(inotify watch, SFTP modu, `--jobs`, `--quarantine`, `.metacls.toml`, politika profilleri,
ses/video, PyPI, özyinelemeli konteyner temizliği).

## Lisans

MIT, bkz. [LICENSE](https://github.com/gorkemguler/MetaCLS/blob/main/LICENSE).
