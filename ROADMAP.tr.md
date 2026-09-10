<p align="center"><sub><a href="ROADMAP.md">🇬🇧 English</a> · 🇹🇷 Türkçe</sub></p>

# MetaScrub yol haritası

Proje nerede duruyor ve sırada ne var. Temaya göre gruplandı; her grup
içinde kabaca öncelik sırasında. Buradaki hiçbir şey söz değil — çalışan
bir yapılacaklar listesi.

---

## v0.1'den bu yana eklenenler

- **Şifreli PDF'ler** — `metascrub clean --password …` / `inspect --password`.
  Parola yoksa şifreli PDF temiz bir `skipped` (ham hata değil); yanlış
  parola net bir `error`; temizlenmiş kopya şifresiz yazılır ve sonuç
  bunu belirtir. *(L4'ü kapatır)*
- **PDF annotation'ları** — her markup annotation'ından (ve `/Popup`'ından)
  yorumcu adı (`/T`), `/M` ve `/CreationDate` silinir; form-alanı
  widget'ları ve annotation'ın görünür `/Contents`'i korunur.
  *(L3'ün bir kısmı)*
- **PDF gömülü dosyaları** — her ekin dosya spec'indeki açıklama ve
  orijinal zaman damgaları kaldırılır; ekli dosyanın kendisi korunur.
  *(L3'ün bir kısmı)*
- **`--strip-pdf-id`** — her çalıştırmada taze rastgele bir trailer `/ID`;
  böylece bir dosyanın iki temizlenmiş kopyası bununla ilişkilendirilemez.
  *(L3'ün bir kısmı)*
- **Eski `.doc / .xls / .ppt`** — saf-Python, yerinde bir temizleyici
  (`engines/ole2.py`) `\x05SummaryInformation` /
  `\x05DocumentSummaryInformation` property akışlarını — yazar, son
  kaydeden, şirket, yönetici, şablon, başlık, zaman damgaları ve özel
  özellikler — dosyanın boyutunu ya da yapısını değiştirmeden yamalar;
  böylece orijinal biçim korunur ve `--in-place` çalışır. LibreOffice
  (`soffice`) artık yalnızca yamalayıcının ayrıştıramadığı bir konteyner
  için *yedek* (ve OOXML'e yeniden render eder). *(L1 ve L11'i kapatır)*
- **SVG motoru** — `<metadata>` (RDF/Dublin-Core yazar/başlık),
  `sodipodi:` / `inkscape:` / Adobe-Illustrator element ve öznitelikleri,
  ve editör yorumları silinir; çizime dokunulmaz. *(L7'nin bir kısmı)*
- **`--backup`** — `--in-place` ile, dokunulmamış orijinali `<ad>.orig`
  olarak saklar (mevcut olanı asla ezmez).
- **`--strip-form-values`** *(opt-in)* — PDF AcroForm alan değerlerini
  (`/V`, `/DV`) boşaltır ve eski değerin hâlâ görünmemesi için önbellekli
  `/AP` görünümünü düşürür; `NeedAppearances` işaretlenir. Birinin bir
  forma yazdığı ad/adres teknik olarak içerik olsa da bir sızıntıdır.
  *(L3'ü kapatır)*
- **`--strip-office-authors`** *(opt-in)* — `document.xml`, `comments.xml`,
  header/footer'lar ve `people.xml` / `authors.xml` / `persons`
  kayıtlarında (Word / PowerPoint / Excel) değişiklik-takibi ve yorum
  **yazar adları + tarihlerini** boşaltır; değişiklik ve yorum *metni*
  korunur ki kabul/ret hâlâ çalışsın. *(L5'in bir kısmı)*

---

## Bilinen sınırlamalar

Bunlar mevcut sürümdeki gerçek eksikler, hata değil:

| # | Eksik | Not |
|---|-------|-----|
| L2 | **Belge *gövde* içeriğine dokunulmuyor** | Gövdeye yazılmış metin, bir yorumun/değişikliğin metni, görselin içine gömülü metin — tasarım gereği kapsam dışı (`--strip-form-values` / `--strip-office-authors` kimlik kısımları için opt-in istisnalar). |
| L5 | **Office: bazı parçalar hâlâ kapsanmıyor** | `--strip-office-authors` artık değişiklik-takibi/yorum yazarlarını hallediyor; hâlâ dokunulmayan: sıra dışı düzenlerde `docProps/thumbnail`, dış-bağlantı hedef yolları, `.docm/.xlsm` `vbaProject.bin`. |
| L6 | **Görseller `exiftool` binary'si gerektiriyor** | Pillow yedeği yalnız jpg/png/webp yapar, korunmadıkça ICC profilini düşürür, animasyonlu biçimleri bozabilir. |
| L7 | **Ses / video motoru yok** | SVG artık hallediliyor; `.mp4/.mov/.mp3/.m4a` hâlâ değil (exiftool yapabilir — bağlanmadı). |
| L11 | **Eski Office: biçim-içi kullanıcı adları** | OLE2 yamalayıcısı property akışlarını temizler (`inspect` / Explorer'ın gösterdiği); `.xls` `WRITEACCESS` ya da `.ppt` `CurrentUserAtom`'a ulaşmaz. LibreOffice yedeği ulaşır (tam yeniden render). |
| L8 | **Doğrulama geçişi sezgisel** | `engines/exiftool.py`'daki "yapısal etiketleri yok say" listesi elle tutuluyor; henüz `residual == []`'i geniş çapta doğrulayan bir altın külliyat yok. |
| L9 | **API/web'de kimlik doğrulama yok** | Belgelendi ama yerleşik token/anahtar yok — önüne proxy koymanız gerekir. |
| L10 | **Her şey tek süreç, bellek içi çalışıyor** | Büyük ağaçlar için paralellik yok; API iş kaydı yeniden başlatmada kaybolur. |

---

## Şimdi — v0.2 (kapsam + güven)

- **Altın külliyat** — `tests/corpus/` içine eklenen, lisansı temiz gerçek
  PDF / Office / görsel seti; her temizlenmiş dosyanın sıfır kimlik
  metadata'sına indiğini doğrulayan test. (L8'i kapatır)
- **`metascrub diff <runA> <runB>`** — iki çalıştırma raporunu karşılaştır
  (MetaScout'un `diff`'i gibi), bir dizini zaman içinde izle.
- CI: GitHub Actions matrisi (Python 3.10–3.13 × macOS/Linux/Windows,
  exiftool'lu/exiftool'suz ve LibreOffice'li/siz), `ruff`, `mypy`.

## Sırada — v0.3–v0.5 (servisleştir, ortama otur)

### Servis sağlamlaştırma ("Linux sunucu / FTP kutusu" senaryosu)
- **API için kimlik doğrulama** — statik API-anahtarı header'ı + belgelenmiş
  nginx/Caddy reverse-proxy tarifi; `--i-know` verilmedikçe loopback-dışı
  bağlanmayı reddet. (L9'u kapatır)
- **Akışlı yükleme** — istek gövdelerini belleğe `await f.read()` yerine
  doğrudan diske yaz; istek başına dosya-sayısı ve boyut sınırları.
- **Kalıcı işler** — SQLite tabanlı iş kaydı; eski çalıştırma dizinleri için
  TTL temizliği. (L10'un bir kısmı)
- **Konteyner** — root olmayan kullanıcı, `HEALTHCHECK`, GHCR'a sürümlü
  imajlar.
- Yapılandırılmış JSON log; opsiyonel `/metrics`.

### `metascrub watch` — FTP/SFTP bırakma-kutusu daemon'u
- `metascrub watch <dir> [--pattern] [--in-place | --to <dir>] [--move-back]`
- inotify (Linux) / polling yedeği, debounce, lockfile, systemd unit.
- Opsiyonel SFTP modu: uzak bırakma dizininden çek, temizle, geri gönder.

### Platform sarmalayıcıları ("sağ tık / eklenti" senaryosu)
- **macOS** — bir Quick Action (`.workflow`); *Finder → sağ tık → Clean
  metadata* ve Servisler menüsü CLI'yi çağırsın; küçük bir SwiftUI
  sürükle-bırak `.app`'i; Homebrew formülü.
- **Windows** — Explorer sağ-tık girdisi (`IExplorerCommand` shell
  eklentisi), `winget` paketi, PowerShell modülü.
- **Linux** — Nautilus / Dolphin / Thunar özel-eylem betikleri; `.deb` /
  `.rpm` / AUR.

### CI / DevSecOps entegrasyonu
- `metascrub clean --dry-run` çalıştırıp kirli belgelerde commit'i düşüren
  bir `pre-commit` hook'u.
- Yayınlanmış bir **GitHub Action** (`gorkemguler/metascrub-action`) — PR'da
  çalışır, raporu yorum olarak yazar, isteğe bağlı temiz dosyaları
  otomatik commit eder.
- Bir GitLab CI şablonu.

## Sonra — v1.0 (cila + ölçek)

- **Paralellik** — büyük ağaçlar için `--jobs N` (ProcessPoolExecutor); bir
  `rich` ilerleme çubuğu. (L10'u kapatır)
- **`--quarantine`** — orijinalleri silmek yerine tarihli bir klasöre taşı;
  `--in-place`'ten daha güvenli bir varsayılan.
- **Proje yapılandırması** — repo başına keep-list ve varsayılanlar için
  `.metascrub.toml`.
- **Politika profilleri** — `--policy publish` / `--policy internal` vb.; her
  biri belgelenmiş, adlandırılmış bir alan seti.
- **HTML rapor** — açılır/kapanır kartlar, duruma göre filtre, CSV-kopyala,
  yazdırma stili; birden çok çalıştırmayı birleştiren rapor.
- `--media` arkasında ses / video motoru. (L7'yi kapatır)
- exiftool'suz HEIC (`pillow-heif` ile). (L6'nın bir kısmı)
- PyPI sürümü, `v0.1.0` etiketi + GitHub release + `CHANGELOG.md`,
  `SECURITY.md`, `CONTRIBUTING.md`.

## Bir gün — daha büyük bahisler

- **Özyinelemeli konteynerler** — ekli `.docx` olan bir PDF, belge dolu bir
  `.zip`, ekli bir `.eml` / `.msg`: her parçaya in, temizle, yeniden paketle.
- **İçerik tarafı işaretleme** — çıktıda MetaScout'un `--scan-content`'ini
  çalıştır ve gövde metninde hâlâ PII varsa uyar. MetaScrub yine içeriği
  düzenlemez ama orada olduğunu söyleyebilir.
- **Deterministik yeniden inşa** — aynı girdi + seçenekler için byte-birebir
  aynı çıktı; böylece bir temizlik tekrarlanabilir/denetlenebilir olur.
