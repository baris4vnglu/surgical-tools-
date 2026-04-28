# Web Tabanlı Akıllı Cerrahi Asistan — 3 Kısımlı Teknik Rapor

**Proje:** Smart Surgical Assistant v3.0  
**Dosyalar:** `server.py` · `index.html`  
**Üniversite:** Near East University — Bilgisayar Mühendisliği

---

## KISIM 1 — Flask Backend Sunucusu (`server.py`)

### 1.1 Genel Mimari

Tkinter masaüstü uygulaması tamamen kaldırılarak yerine bir **Flask web sunucusu** kuruldu. Uygulama iki katmana ayrıldı:

- **Backend (`server.py`):** Kamera okuma, yapay zeka tespiti ve durum yönetimi.
- **Frontend (`index.html`):** Tarayıcı üzerinden erişilen kullanıcı arayüzü.

Bu sayede birden fazla kullanıcı aynı anda farklı cihazlardan sisteme bağlanabilir hale geldi.

### 1.2 Kamera İşleme Döngüsü

Kamera işlemleri ana Flask thread'inden ayrı bir **daemon thread** üzerinde çalışır (`_process_loop`). Bu döngüde sırasıyla şu adımlar gerçekleştirilir:

1. `cv2.VideoCapture(0)` ile kameradan kare okunur.
2. **MediaPipe Hand Landmarker** ile ellerin 21 anahtar noktası tespit edilir; her el için dikdörtgen sınır kutusu (padding=25 px) hesaplanır.
3. **YOLOv8** modeli (`conf=0.35`) ile 16 cerrahi alet tanınır; en yüksek güven skorlu kutu seçilir.
4. Her alet için el–alet örtüşme skoru (`_score`) hesaplanır:

   ```
   score = 0.40×containment + 0.30×center_in + 0.20×IoU + 0.10×proximity
   ```

5. 7 karelik kayan pencere (`held_history`) ile ani "false positive" hatalar yumuşatılır.
6. Kare JPEG olarak sıkıştırılır (kalite=78) ve `_latest_jpeg` değişkenine yazılır.

### 1.3 Thread-Safe Durum Yönetimi

Tüm durum bilgisi `S` sözlüğünde tutulur ve `threading.Lock()` (`_lock`) ile korunur. JPEG tamponu ayrıca `_jpeg_lock` ile ayrı bir kilitle korunur; bu sayede kamera döngüsü ile HTTP istekleri birbirini bloke etmez.

### 1.4 REST API Uç Noktaları

| Endpoint | Metod | Açıklama |
|---|:---:|---|
| `/` | GET | `index.html` anasayfasını döndürür |
| `/video_feed` | GET | MJPEG stream — sonsuz multipart/jpeg akışı |
| `/api/state` | GET | Anlık tüm verileri JSON olarak döndürür |
| `/api/start` | POST | Ameliyatı başlatır; timerları ve sayaçları sıfırlar |
| `/api/end` | POST | Ameliyatı bitirir; eksik alet listesi ve geçen süreyi döndürür |
| `/api/set_threshold` | POST | El–alet eşiğini günceller (0.05–0.90 arası, debounce 120 ms) |
| `/api/config` | GET | Mevcut eşik değerini döndürür |
| `/api/export_excel` | GET | Oturum raporunu `.xlsx` olarak tarayıcıya indirir |

### 1.5 Graceful Fallback (Hata Toleransı)

- YOLO modeli yüklenemezse `MODEL_OK = False` ile devam edilir; kamera akışı çalışmaya devam eder.
- MediaPipe bulunamazsa veya `hand_landmarker.task` dosyası yoksa yalnızca YOLO ile çalışılır.
- Kamera açılamazsa siyah ekrana "Camera not found!" mesajı yazdırılır; sunucu çökmez.

### 1.6 Excel Raporlama (Sunucu Taraflı)

`/api/export_excel` endpoint'i `openpyxl` ile iki sayfalı bir Excel dosyası oluşturur:

- **Sayfa 1 (Tool Summary):** Her alet için kullanım süresi, kaç kez alındığı, mevcut durumu ve zaman aşımı uyarısı.
- **Sayfa 2 (Event Log):** Tüm oturum olayları; renk kodlu (yeşil / sarı / kırmızı / cyan) satırlar.

Dosya diske kaydedilmez; `io.BytesIO` tamponu üzerinden doğrudan tarayıcıya akıtılır.

---

## KISIM 2 — Web Arayüzü: HTML ve CSS (`index.html`)

### 2.1 Sayfa Yapısı

`index.html` tek bir dosyada hem HTML hem de CSS ve JavaScript barındırır. Sayfa şu bölümlerden oluşur:

| Bölüm | ID / Klass | İçerik |
|---|---|---|
| Navigasyon | `#mainNav` | Sabit üst bar, okul logosu, bölüm linkleri |
| Hero | `.hero` | Tam ekran video arka plan, başlık, CTA butonları |
| İstatistikler | `.stats-row` | 4 animasyonlu sayaç kartı |
| Özellikler | `#features` | 6 özellik kartı grid |
| Canlı Demo | `#demo` | Kamera + kontrol paneli |
| Alet Galerisi | `#tools` | 16 alet chip |
| AI Bölümü | `#ai` | DeepSeek açıklaması + animasyonlu AI rapor kartı |
| Footer | `footer` | Üniversite bilgisi |

### 2.2 Tasarım Sistemi (CSS Custom Properties)

Tüm renkler CSS değişkeni olarak tanımlandı; bu sayede tema değişikliği tek noktadan yapılabilir:

```css
:root {
  --bg-dark: #0d1117;   --bg-panel: #161b22;  --bg-card: #1c2128;
  --accent:  #58a6ff;   --green:    #3fb950;  --red:     #f85149;
  --yellow:  #d29922;   --cyan:     #39d0d8;
}
```

### 2.3 Animasyonlar

| Animasyon | Tetikleyici | Efekt |
|---|---|---|
| `slideDown` | Sayfa yüklenince | Nav çubuğu yukarıdan kayar |
| `fadeUp` | Sayfa yüklenince | Hero içeriği aşağıdan yukarı açılır |
| `statIn` | Viewport'a girilince | İstatistik kartları scale-in ile belirir |
| `cardIn` | Viewport'a girilince | Özellik ve alet kartları aşağıdan kayar |
| `blink` | Sürekli | "LIVE" noktası ve yeşil durum noktası yanıp söner |
| `bounce` | Sürekli | Hero'daki "Scroll down" aşağı sekme yapar |
| `spin` | Sunucu bağlantısı yokken | Kamera alanındaki yükleniyor spinneri döner |
| `endPulse` | Ameliyat bitince | Kamera çerçevesi 3 kez kırmızı parlar |

### 2.4 Responsive Tasarım

`max-width: 800px` medya sorgusunda:
- `demo-body` tek sütuna düşer (kamera + kontrol alt alta).
- AI grid tek sütuna düşer.
- Nav linkleri gizlenir (sadece logo ve başlık kalır).

### 2.5 Kamera Görüntüsü ve HUD Katmanı

Kamera alanı üç katman halinde yapılandırıldı:

1. **`<img id="liveStream">`** — `/video_feed`'den gelen MJPEG akışını gösterir.
2. **`.cam-placeholder`** — Sunucu bağlantısı yokken spinner ve yönlendirme mesajı gösterir.
3. **`.hud`** (absolute konumlu) — FPS sayacı, "LIVE" etiketi, köşe çizgileri ve ameliyat durumu etiketi; pointer-events: none ile etkileşimi engellenmez.

`surgery-ring` CSS sınıfı, ameliyat aktifken yeşil, bitişinde kırmızı çerçeve animasyonu yapar.

### 2.6 Demo Kontrol Paneli

Sağ panel aşağıdaki blokları içerir (yukarıdan aşağı):

1. **Surgery Control** — Start/End butonları + `monospace` oturum saati.
2. **Detection Sensitivity** — Slider (5–80 pct → 0.05–0.80) + gradyan dolum çubuğu + 4 ön ayar butonu (High 0.08 / Med-Lo 0.15 / Normal 0.20 / Strict 0.40).
3. **Tool Status** — 16 alet satırı; her birinde durum noktası, rozet, süre ve örtüşme skoru.
4. **Event Log** — Kaydırılabilir monospace log alanı.
5. **Export Excel** — `.xlsx` raporu indirme butonu.

---

## KISIM 3 — Web Arayüzü: JavaScript (`index.html`)

### 3.1 Başlangıç — Alet Listesi ve Galeri Oluşturma

Sayfa yüklendiğinde JavaScript, `TOOLS` dizisini dönerek hem kontrol panelindeki `#toolList` hem de `#tools` galerisi için HTML elemanlarını dinamik olarak oluşturur. Her alet için ID tabanlı erişim sağlanır (`dot-{id}`, `badge-{id}`, `time-{id}`, `bar-{id}`, `score-{id}`).

### 3.2 Intersection Observer (Scroll Animasyonu)

`IntersectionObserver` ile `.feat-card`, `.stat-card` ve `.tool-chip` elemanları viewport'a girince `visible` sınıfı alır ve CSS animasyonu tetiklenir. İstatistik kartlarındaki sayılar 1200 ms'lik ease-in-quadratic eğrisiyle animasyonlu olarak hedef değere ulaşır.

### 3.3 Sunucu Bağlantı Yönetimi

`IS_SERVER` bayrağı (`window.location.protocol.startsWith('http')`) ile dosya:// üzerinden açılıp açılmadığı tespit edilir:

- **Sunucu yoksa:** Start/End/Excel butonları devre dışı bırakılır; sarı uyarı banner gösterilir.
- **Sunucu varsa:** Sayfa açılışında `/api/config`'ten mevcut eşik değeri çekilir; ardından her 600 ms'de bir `/api/state` çağrılır.

### 3.4 Durum Sorgulama Döngüsü (`pollState`)

`setInterval(pollState, 600)` ile saniyede ~1.67 kez sunucu durumu sorgulanır:

1. `/api/state` yanıtından FPS, ameliyat süresi ve alet verileri okunur.
2. Her alet için `updateToolRow()` çağrılarak durum noktası, rozet, süre çubuğu ve örtüşme skoru güncellenir.
3. Örtüşme skoru eşiğin üzerindeyse **yeşil (`.hot`)**, altındaysa **sarı (`.warm`)** renk uygulanır.
4. Yalnızca son görülen ID'den büyük olaylar log'a eklenir (`lastSeenEventId` takibi); bu sayede aynı satır iki kez eklenmez.

### 3.5 Eşik (Sensitivity) Kontrolü

- **Slider** hareketiyle `onSliderMove()` çağrılır; `_syncThreshUI()` hem slider hem dolum çubuğunu hem de marker çizgisini günceller.
- **Preset butonları** `applyPreset(pct)` ile aynı akışı tetikler ve aktif butonu işaretler.
- Sunucuya gönderim **120 ms debounce** (`_threshTimer`) ile gerçekleşir; slider sürüklenirken gereksiz API çağrısı yapılmaz.

### 3.6 Excel Export

`exportExcel()`:
1. `/api/export_excel`'e GET isteği atar.
2. Yanıt `Blob` olarak alınır.
3. Geçici `<a>` elemanı oluşturularak `URL.createObjectURL` ile tarayıcının indirme mekanizması tetiklenir.
4. İşlem bittikten sonra `URL.revokeObjectURL` ile bellek temizlenir.

### 3.7 AI Yazma Efekti

`typeAI()` fonksiyonu, `#aiTypedText` alanında 4 örnek AI raporunu sırayla karakter karakter yazar (her karakter 26 ms aralıkla). Bir mesaj tamamlandıktan 4.2 saniye sonra bir sonrakine geçer. Canlı AI yanıtları `/api/state` event log üzerinden gelir; bu animasyon sistemin ne yapabileceğini göstermek için gösterge amaçlıdır.

---

## Özet Tablo

| | Kısım 1 (Backend) | Kısım 2 (HTML/CSS) | Kısım 3 (JavaScript) |
|---|---|---|---|
| **Ana Dosya** | `server.py` | `index.html` | `index.html` |
| **Sorumluluk** | Kamera, AI, API | Yapı ve görsel tasarım | Etkileşim ve veri senkronizasyonu |
| **Temel Teknoloji** | Flask, OpenCV, YOLO, MediaPipe | CSS Variables, Flexbox/Grid, Keyframes | Fetch API, IntersectionObserver, Blob |
| **Kritik Özellik** | Thread-safe `_lock` | Animasyonlu HUD katmanı | 600 ms polling + debounce |
