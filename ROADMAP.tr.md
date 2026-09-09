<p align="center"><sub><a href="ROADMAP.md">🇬🇧 English</a> · 🇹🇷 Türkçe</sub></p>

# MetaScrub yol haritası

v0.1 nerede duruyor ve sırada ne var. Temaya göre gruplandı; her grup
içinde kabaca öncelik sırasında. Buradaki hiçbir şey söz değil — çalışan
bir yapılacaklar listesi.

---

## v0.1'deki bilinen sınırlamalar

Bunlar mevcut sürümdeki gerçek eksikler, hata değil:

| # | Eksik | Not |
|---|-------|-----|
| L1 | **Eski `.doc / .xls / .ppt` temizlenmiyor** | `unsupported` olarak raporlanıyor. OLE2 Compound File Binary için güvenli, yalnız-stdlib bir temizlik yok. |
| L2 | **Belge içeriğine hiç dokunulmuyor** | Değişiklik takibi / yorumlardaki yazar adları, gövdeye yazılmış metin, görselin içine gömülü metin — tasarım gereği kapsam dışı. |
| L3 | **PDF: yalnız `/Info` + XMP + `/PieceInfo` + sayfa metadata'sı** | Henüz yok: gömülü dosya ekleri, annotation yazar/tarihleri, AcroForm verisi, `xmpMM` düzenleme geçmişi, trailer `/ID`. |
| L4 | **Şifreli / parolalı PDF'ler `error` düşüyor** | pikepdf parolasız açamıyor; henüz `--password` bayrağı yok. |
| L5 | **Office: yalnız `docProps/*` + `w:rsids`** | Henüz yok: değişiklik-takibi/yorum yazarları, bazı düzenlerde `docProps/thumbnail`, dış-bağlantı yolları, `.docm/.xlsm` `vbaProject.bin`. |
| L6 | **Görseller `exiftool` binary'si gerektiriyor** | Pillow yedeği yalnız jpg/png/webp yapar, korunmadıkça ICC profilini düşürür, animasyonlu biçimleri bozabilir. |
| L7 | **SVG / ses / video motoru yok** | `.svg` (editör yorumları, `<metadata>`), `.mp4/.mov/.mp3/.m4a` (exiftool yapabilir, bağlamadık). |
| L8 | **Doğrulama geçişi sezgisel** | `engines/exiftool.py`'daki "yapısal etiketleri yok say" listesi elle tutuluyor; henüz `residual == []`'i geniş çapta doğrulayan bir altın külliyat yok. |
| L9 | **API/web'de kimlik doğrulama yok** | Belgelendi ama yerleşik token/anahtar yok — önüne proxy koymanız gerekir. |
| L10 | **Her şey tek süreç, bellek içi çalışıyor** | Büyük ağaçlar için paralellik yok; API iş kaydı yeniden başlatmada kaybolur. |

---

## Şimdi — v0.2 (kapsam + güven)

- **PDF derinliği** — gömülü dosya ekleri (`/Names /EmbeddedFiles`, `/AF`),
  annotation `/T` `/M` `/CreationDate`, `xmpMM:History` / `xmpMM:DerivedFrom`,
  trailer `/ID` için `--strip-id` bayrağı. (L3'ü kapatır)
- **Şifreli PDF'ler** — ham hata yerine net rapor; `metascrub clean
  --password …` eklenir. (L4'ü kapatır)
- **Eski Office** — `olefile` ile `\x05SummaryInformation` /
  `\x05DocumentSummaryInformation` akışlarını sıfırlama; `soffice` varsa
  opsiyonel LibreOffice-headless dönüştür-geri-al yolu. (L1'i kapatır)
- **Office yazarları** — opt-in `--strip-office-authors`: `w:ins`/`w:del`
  yazarları, `comments.xml` / `people.xml`, PowerPoint notları. (L5'in bir kısmı)
- **SVG motoru** — `<metadata>`, editör yorumları, `sodipodi:`/`inkscape:`
  öznitelikleri. (L7'nin bir kısmı)
- **Altın külliyat** — `tests/corpus/` içine eklenen, lisansı temiz gerçek
  PDF / Office / görsel seti; her temizlenmiş dosyanın sıfır kimlik
  metadata'sına indiğini doğrulayan test. (L8'i kapatır)
- **`--backup`** — `--in-place` temizlikte `<ad>.orig` bırak.
- **`metascrub diff <runA> <runB>`** — iki çalıştırma raporunu karşılaştır
  (MetaScout'un `diff`'i gibi), bir dizini zaman içinde izle.
- CI: GitHub Actions matrisi (Python 3.10–3.13 × macOS/Linux/Windows,
  exiftool'lu ve exiftool'suz), `ruff`, `mypy`.

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
