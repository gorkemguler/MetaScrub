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
- **`metascrub diff <runA> <runB>`** — iki çalıştırma raporunu (ya da
  dizinini) karşılaştırır: eklenen/silinen dosyalar ve — asıl mesele —
  iki çalıştırma arasında metadata *yeniden ortaya çıkan* dosyalar
  (birisi belgeyi tekrar kaydetmiş). Herhangi bir dosya metadata
  geri kazandıysa çıkış kodu 1.
- **Altın külliyat** — `tests/test_corpus.py` her biçim için
  (pdf/docx/xlsx/pptx/odt/ods/svg/jpg/doc) kasıtlı kirli bir dosya üretir
  ve her birinin sıfır artık'a temizlendiğini doğrular. *(L8'i kapatır)*
  Daha şimdiden gerçek bir bug yakaladı — ODF `probe` `<meta>`'yı yanlış
  ad-alanında arıyordu, yani `inspect` / dry-run / verify `.odt/.ods`
  metadata'sına kördü.
- **Araçlar** — `ruff` + `mypy` (ikisi de temiz), GitHub Actions CI
  matrisi (py 3.10–3.13 × Linux/macOS/Windows), `slow` pytest işareti +
  session-kapsamlı eski-`.doc` fixture'ı (`pytest -q` ~60 sn → ~12 sn),
  `CHANGELOG.md` / `CONTRIBUTING.md` / `SECURITY.md`.
- **API kimlik doğrulama + sınırlar** — `metascrub api --api-key` (env
  `METASCRUB_API_KEY`) `/v1/health` dışında her `/v1` route'unda gerekli
  (`X-API-Key` ya da `Authorization: Bearer`). Yüklemeler doğrudan geçici
  bir dosyaya akıtılır (tüm grup asla bellekte değil), `--max-upload-mb` /
  `--max-files` sınırlarıyla → 413. Hem `web` hem `api`, kimlik doğrulama
  yokken **loopback-dışı bir host'a bağlanmayı reddeder** (`--insecure`
  hariç). *(L9'u kapatır)*
- **Kalıcı API işleri** — iş kaydı artık bir SQLite dosyası
  (`<output_dir>/jobs.db`); iş durumu + özeti yeniden başlatmada korunur,
  süreç öldüğünde `running` olan bir iş `error: interrupted by a service
  restart` olarak döner, `--run-ttl-days N` başlangıçta eski bitmiş
  işleri + çalıştırma dizinlerini siler. *(L10'un bir kısmı)*
- **Konteyner** — imaj root olmayan bir kullanıcı (uid 1000) olarak
  çalışır, `HEALTHCHECK`'i var, ve `metascrub api --log-json` istek
  başına bir JSON erişim-log satırı basar. `docker-compose` API servisi
  artık `METASCRUB_API_KEY` ve 30-günlük TTL alıyor.

---

## Bilinen sınırlamalar

Bunlar mevcut sürümdeki gerçek eksikler, hata değil:

| # | Eksik | Not |
|---|-------|-----|
| L2 | **Belge *gövde* içeriğine dokunulmuyor** | Gövdeye yazılmış metin, bir yorumun/değişikliğin metni, görselin içine gömülü metin — tasarım gereği kapsam dışı (`--strip-form-values` / `--strip-office-authors` kimlik kısımları için opt-in istisnalar). |
| L5 | **Office: bazı parçalar hâlâ kapsanmıyor** | `--strip-office-authors` değişiklik-takibi/yorum yazarlarını hallediyor; makro içeren / şablon dosyalar temizlenip `vbaProject.bin` işaretleniyor. Hâlâ dokunulmayan: `vbaProject.bin` *içeriği* (bilerek korunuyor), dış-bağlantı hedef yolları ve sıra dışı düzenlerde `docProps/thumbnail`. |
| L6 | **Görseller: Pillow yedeği zayıf** | exiftool jpg/png/gif/webp/heic/tiff'i tam işler. Pillow yedeği (exiftool yokken) yalnız jpg/png/webp/heic (heic `pillow-heif` ile) ve animasyonlu biçimleri bozabilir. |
| L7 | **Video temizliği best-effort** | Ses (`mutagen`) kapsamlı; video için yalnız metadata atom'ları temizlenir — exiftool'un yazamadığı bir konteyner (`.mkv`/`.avi`/`.webm`) tam kapsanmayabilir, oynatma kontrol edilmeli. |
| L11 | **Eski Office: biçim-içi kullanıcı adları** | OLE2 yamalayıcısı property akışlarını temizler (`inspect` / Explorer'ın gösterdiği); `.xls` `WRITEACCESS` ya da `.ppt` `CurrentUserAtom`'a ulaşmaz. LibreOffice yedeği ulaşır (tam yeniden render). |
| L8 | **exiftool yok-say listesi elle tutuluyor** | `engines/exiftool.py`'nin "yapısal etiket" izin listesi hâlâ elle tutuluyor; altın külliyat sık durumları koruyor ama egzotik bir kamera etiketi sızabilir. |
| L10 | **Her şey tek süreç, bellek içi çalışıyor** | Büyük ağaçlar için paralellik yok; API iş kaydı yeniden başlatmada kaybolur. |

---

## Şimdi — v0.3 planı (eksik kapatma taraması)

Sıralı batch'ler, her biri kendi commit'i:

1. ~~**Biçim kapsamı** — GIF (comment/XMP blokları); `.docm/.xlsm/.pptm` +
   `.dotx/.xltx/.potx`; ODF `Thumbnails/`. `DEFAULT_FILETYPES`
   genişletilir.~~ **Bitti.** GIF artık temizleniyor (EXIF/XMP + comment
   uzantısı) ve `GIF` exiftool grubu yapısal sayıldığı için temizlenmiş
   bir GIF artık çıkış-kodu kapısını tetiklemiyor; JPEG/GIF `Comment`
   bloğu gerçek bir kaçak olarak izleniyor. Makro içeren ve şablon OOXML
   dosyaları office motorundan geçiyor — `vbaProject.bin` korunuyor ama
   rapor dosyanın kısmen temizlendiğini bildiriyor. ODF `Thumbnails/`
   önizlemesi + manifest girdisi düşürülüyor. `DEFAULT_FILETYPES` 29
   uzantı. *(L5, L6 daralır)*
2. ~~**XFA form verisi** — `--strip-form-values` ile `/AcroForm/XFA`
   `datasets` paketini (`<xfa:data>` içeriği) boşalt.~~ **Bitti.** Her XFA
   paketinin (dizi biçimi ya da tek `xdp:xdp` akışı) `<xfa:data>` gövdesi
   boşaltılıyor; şablon, datasets sarmalayıcısı ve `<dd:dataDescription>`
   şeması korunuyor.
3. ~~**`watch` sağlamlaştırma** — lockfile (dizin başına tek watcher),
   `--pattern` glob filtresi, kaybolan dosyalar için state budama,
   `--jobs` geçişi.~~ **Bitti.** `.metascrub-watch.lock` (PID damgalı, ölü
   sahibin kilidini çalar); tekrarlanabilir `--pattern GLOB`; `-j/--jobs N`
   (birikmiş iş tek `clean_paths` çağrısında); kaybolan dosya kayıtları
   her taramada budanır.
4. **Tutarlılık + paketleme** — `inspect --recurse/--media`; `py.typed`;
   `--exclude GLOB`; `--no-follow-symlinks`; `--progress`; tam
   `tool_versions()`; `--debug` re-raise; `.editorconfig` / `CODEOWNERS` /
   issue+PR şablonları; CI'da `ruff format`.
5. **Video EBML/RIFF** — minimal `.mkv/.webm` EBML `Tags` ve `.avi` RIFF
   `LIST/INFO` + `IDIT` temizleyici (exiftool bunlara yazamıyor). *(L7'yi kapatır)*
6. **Daha fazla konteyner** — `.tar`/`.tar.gz` (stdlib), `.msg` (opsiyonel
   `extract-msg`), `.7z` (opsiyonel `py7zr`).
7. **Yerel drop uygulamaları** —
   - macOS: `osacompile` droplet `MetaScrub.app` (Xcode yok) + Quick Action.
   - Windows: WinForms sürükle-bırak `.ps1` GUI + `SendTo` kısayolu +
     `winget` manifesti; sağ-tık girdisi zaten var.
   - Linux: `.desktop` MIME handler + `zenity` drop diyaloğu + Nautilus betiği.
8. **Web/API eşitliği** — web formunda ve API'de `--recurse` / `--media`;
   `GET /v1/formats` endpoint'i; yenilenmiş ekran görüntüleri.
9. **Yayın hattı** — `.github/workflows/docker.yml` tag'de
   `ghcr.io/gorkemguler/metascrub` build+push; `--api-key` yanında
   nginx/Caddy reverse-proxy tarifi.

### `metascrub watch` — FTP/SFTP bırakma-kutusu daemon'u — **tamam**
- `metascrub watch <dir> [--to DIR] [--move-processed DIR] [--interval] [--settle] [--once]`
- Settle penceresiyle poll döngüsü (yarım yüklenmiş dosya yok), yeniden
  başlatmanın yeniden işlememesi için JSON durum dosyası, yeniden-bırakma
  tespiti, ve `platform/linux/`'te systemd şablon unit'i.
- *Hâlâ yapılacak:* Linux'ta inotify hızlı-yolu, ve uzak bırakma
  dizininden çekip temizlenmiş dosyayı geri iten bir SFTP modu.

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

Geldi: `--jobs N` (thread-pool paralel temizlik), `--quarantine DIR`,
`.metascrub.toml` proje yapılandırması, `--policy publish|internal|minimal`,
açılır/filtrelenebilir/yazdırılabilir HTML rapor, ve bir `release.yml`
(tag → build → PyPI Trusted Publishing + GitHub Release).

Hâlâ açık:
- Büyük ağaçlar için `rich` ilerleme çubuğu.
- Çalıştırmaları birleştiren HTML rapor; CSV-kopyala.
- Daha derin video — `.mkv/.webm` için EBML `Tags`, `.avi` için RIFF `LIST`.
- Windows `IExplorerCommand` shell eklentisi; `winget` / Homebrew /
  `.deb` paketleri; GitHub Action'ı Marketplace'e yayınla.

## Bir gün — daha büyük bahisler

- **Özyinelemeli konteynerler** — *ilk sürüm tamam*: `metascrub clean
  --recurse` `.zip` arşivlerine ve `.eml` e-postalarına iner
  (`engines/container.py`), her üyeyi temizler, yeniden paketler, derinlik
  sınırlı. Hâlâ açık: `.msg` (Outlook), ve bir PDF'nin *kendi*
  `/EmbeddedFiles`'ının temizlenmiş kopyalarını yeniden gömme.
- **İçerik tarafı işaretleme** — çıktıda MetaScout'un `--scan-content`'ini
  çalıştıran bir `--flag-content`; gövde metninde hâlâ PII varsa uyarır.
  Şimdilik README ikinci geçiş olarak `metascout local-scan
  --scan-content` çalıştırmayı öneriyor.
- **Deterministik yeniden inşa** — *tamam ve korumalı*:
  `tests/test_deterministic.py` aynı dosyanın aynı seçeneklerle ikinci
  temizliğinin byte-birebir aynı olduğunu doğrular (`--strip-pdf-id`
  hariç — o tasarım gereği rastgele).
