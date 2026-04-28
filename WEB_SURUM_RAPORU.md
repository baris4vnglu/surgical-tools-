# Web Arayüzü Teknik Raporu — 3 Kısım

**Proje:** Smart Surgical Assistant v3.0  
**Dosya:** `index.html`  
**Üniversite:** Near East University — Bilgisayar Mühendisliği

---

## KISIM 1 — HTML: Sayfa Yapısı ve DOM

### 1.1 Genel Düzen

`index.html` tek dosyada HTML, CSS ve JavaScript'i bir arada barındıran bir **Single Page Application (SPA)** yapısıdır. Sayfa aşağıdaki bölümlerden oluşur:

| Bölüm | Etiket / ID | Açıklama |
|---|---|---|
| Navigasyon | `<nav id="mainNav">` | Sabit üst çubuk — okul logosu + bölüm linkleri |
| Hero | `<div class="hero">` | Tam ekran video arka planı, başlık, CTA butonları |
| İstatistikler | `<section>` `.stats-row` | 4 animasyonlu sayaç kartı |
| Özellikler | `<section id="features">` | 6 özellik kartı |
| Canlı Demo | `<section id="demo">` | Kamera akışı + kontrol paneli |
| Alet Galerisi | `<section id="tools">` | 16 alet chip'i |
| AI Bölümü | `<section id="ai">` | DeepSeek açıklaması + yazma efektli rapor kartı |
| Footer | `<footer>` | Üniversite bilgisi ve linkler |

### 1.2 Hero Bölümü

```html
<div class="hero">
  <video class="hero-video" src="ameliyat video.mp4" autoplay muted loop playsinline></video>
  <div class="hero-overlay"></div>   <!-- gradient karartma -->
  <div class="hero-content">        <!-- başlık + butonlar -->
```

- Arka plana gerçek ameliyat videosu (`ameliyat video.mp4`) yerleştirildi; `opacity: 0.22` ve `filter: saturate(.5)` ile soluk gösterildi.
- `hero-overlay` div'i `linear-gradient` ile altta tam opak bir geçiş sağlar, böylece alttaki içerik videoya karışmaz.
- `hero-badge` içindeki yeşil nokta CSS `@keyframes blink` ile yanıp söner.

### 1.3 Canlı Demo Bölümü (Kamera + Kontrol Paneli)

Demo bölümü `demo-body` içinde **2 sütunlu grid** olarak kuruldu:

```
┌─────────────────────────────┬──────────────────┐
│  Kamera akışı (.demo-video) │  Kontrol paneli  │
│  + HUD katmanı              │  (.demo-controls)│
└─────────────────────────────┴──────────────────┘
```

**Kamera alanı 3 katmandan oluşur:**

1. `<img id="liveStream">` — `/video_feed`'den MJPEG akışı.
2. `.cam-placeholder` — Sunucu bağlantısı yokken gösterilen spinner ve yönlendirme mesajı.
3. `.hud` (absolute, pointer-events: none) — FPS sayacı, "LIVE" etiketi, köşe çizgileri.

**Kontrol paneli 5 bloktan oluşur (yukarıdan aşağıya):**
1. Ameliyat kontrolü (Start / End butonları + süre saati)
2. Algılama hassasiyeti (slider + preset butonları)
3. Alet durum listesi (`#toolList`)
4. Olay logu (`#evtLog`)
5. Excel dışa aktarım butonu

### 1.4 Alet Galerisi ve Tool Status — Dinamik DOM

`#toolList` ve `#toolsGrid` içindeki tüm HTML, JavaScript tarafından çalışma zamanında oluşturulur; `index.html` içinde bu elemanlar için sabit HTML yoktur. Her alet satırı şu yapıya sahiptir:

```html
<div class="tool-row" id="row-scalpel">
  <div class="tool-dot"   id="dot-scalpel">   <!-- renk noktası -->
  <div class="tool-name">Scalpel</div>
  <div class="tool-bar-wrap">
    <div class="tool-bar-fill" id="bar-scalpel">  <!-- ilerleme çubuğu -->
  <div class="tool-badge"  id="badge-scalpel">    <!-- ON TABLE / IN HAND / MISSING -->
  <div class="tool-time"   id="time-scalpel">     <!-- kullanım süresi -->
  <div class="tool-score"  id="score-scalpel">    <!-- örtüşme skoru -->
</div>
```

### 1.5 Sunucu Uyarı Banner'ı

```html
<div id="serverWarning">
```

Sayfa `file://` protokolü ile açıldığında (sunucu çalışmıyorken) bu banner görünür hale gelir ve kullanıcıya `python server.py`'yi nasıl başlatacağını gösterir. Start / End / Excel butonları da otomatik olarak `disabled` yapılır.

---

## KISIM 2 — CSS: Tasarım Sistemi ve Animasyonlar

### 2.1 Renk Paleti — CSS Custom Properties

Tüm renkler `:root` bloğunda değişken olarak tanımlandı:

```css
:root {
  --bg-dark:  #0d1117;   /* ana arka plan */
  --bg-panel: #161b22;   /* panel arka planı */
  --bg-card:  #1c2128;   /* kart arka planı */
  --accent:   #58a6ff;   /* mavi vurgu */
  --green:    #3fb950;   /* ON TABLE */
  --red:      #f85149;   /* IN HAND */
  --yellow:   #d29922;   /* MISSING */
  --cyan:     #39d0d8;   /* FPS / zaman */
  --text-dim: #8b949e;   /* soluk metin */
  --text:     #e6edf3;   /* ana metin */
  --border:   #30363d;   /* kenar çizgisi */
}
```

Bu yapı sayesinde ileride tema değişikliği tek bir blok düzenlenerek yapılabilir.

### 2.2 Animasyonlar

| Animasyon | Tetikleyici | Efekt |
|---|---|---|
| `slideDown` | Sayfa yüklenince | Nav çubuğu yukarıdan kayarak girer |
| `fadeUp` | Sayfa yüklenince | Hero içeriği aşağıdan yukarı açılır |
| `statIn` | Viewport'a girilince | İstatistik kartları ölçek ile belirir |
| `cardIn` | Viewport'a girilince | Özellik / alet kartları yukarı kayar |
| `blink` | Sürekli | "LIVE" ve durum noktaları yanıp söner |
| `bounce` | Sürekli | Hero'daki "Scroll down" oku sekme yapar |
| `spin` | Sunucu yokken | Kamera alanındaki spinner döner |
| `endPulse` | Ameliyat bitince | Kamera çerçevesi 3 kez kırmızı parlar |

**Örnek — `endPulse`:**
```css
@keyframes endPulse {
  0%,100% { box-shadow: inset 0 0 40px rgba(248,81,73,.12); }
  50%      { box-shadow: inset 0 0 80px rgba(248,81,73,.35); }
}
.surgery-ring.ending { animation: endPulse .55s ease 3; }
```

### 2.3 Kart ve Panel Stilleri

- **`.feat-card`:** `transform: translateY(-4px)` ve mavi `box-shadow` ile hover efekti.
- **`.tool-row`:** `background: rgba(88,166,255,.05)` hover rengi.
- **`.btn-start-surgery`:** Aktifken `box-shadow: 0 0 18px rgba(63,185,80,.5)` yeşil ışıma.
- **`.btn-end-surgery.armed`:** Kırmızıya dönüşerek `box-shadow` ile alarm görünümü alır.

### 2.4 HUD Köşe Çizgileri

```css
.hud-corner.tl { top:10px; left:10px;  border-width: 2px 0 0 2px; }
.hud-corner.tr { top:10px; right:10px; border-width: 2px 2px 0 0; }
.hud-corner.bl { bottom:10px; left:10px;  border-width: 0 0 2px 2px; }
.hud-corner.br { bottom:10px; right:10px; border-width: 0 2px 2px 0; }
```

Her köşeye sadece 2 kenarlık çizilerek klasik cerrahi izleme sistemlerindeki kamera HUD görünümü elde edildi.

### 2.5 Hassasiyet Slider'ı

```css
input[type="range"].sens-slider::-webkit-slider-thumb {
  width: 14px; height: 14px; border-radius: 50%;
  background: var(--accent); transition: transform .15s;
}
input[type="range"].sens-slider::-webkit-slider-thumb:hover {
  transform: scale(1.2);
}
```

Slider arka planında `linear-gradient(90deg, var(--green), var(--yellow), var(--red))` ile yeşilden kırmızıya geçen bir dolum çubuğu ve `var(--accent)` renkli bir marker çizgisi yer alır.

### 2.6 Responsive Tasarım

```css
@media (max-width: 800px) {
  .demo-body      { grid-template-columns: 1fr; }    /* kamera + kontrol alt alta */
  .ai-grid        { grid-template-columns: 1fr; }    /* AI bölümü tek sütun */
  .nav-links      { display: none; }                 /* menü linkleri gizlenir */
}
```

---

## KISIM 3 — JavaScript: Etkileşim ve Veri Senkronizasyonu

### 3.1 Başlangıç — Alet Listesi ve Galeri Oluşturma

```js
const TOOLS = [
  {id:"army_navy", icon:"🔧", label:"Army Navy"},
  {id:"scalpel",   icon:"🔪", label:"Scalpel"},
  // ... toplam 16 alet
];
```

Sayfa yüklendiğinde `TOOLS` dizisi döngüye alınarak hem `#toolList` hem de `#toolsGrid` DOM elemanları dinamik olarak oluşturulur. ID tabanlı (`dot-{id}`, `badge-{id}`, `time-{id}`) erişim sonradan hızlı güncelleme için kullanılır.

### 3.2 Sunucu Algılama ve Bağlantı Yönetimi

```js
const IS_SERVER = window.location.protocol.startsWith('http');
```

- `IS_SERVER = false` ise butonlar devre dışı, uyarı banner'ı görünür hale gelir.
- `IS_SERVER = true` ise sayfa açılışında `/api/config`'ten mevcut eşik çekilir; ardından `setInterval(pollState, 600)` ile döngü başlatılır.

### 3.3 Durum Sorgulama Döngüsü (`pollState`)

Her 600 ms'de `/api/state` sorgulanır. Gelen yanıt işlenerek:

1. **FPS** — `#hudFps` güncellenir.
2. **Ameliyat süresi** — `#surgeryTimer` `HH:MM:SS` formatında gösterilir.
3. **Alet satırları** — `updateToolRow()` ile durum noktası, rozet, süre çubuğu ve örtüşme skoru güncellenir.
4. **Event log** — `lastSeenEventId` takibi sayesinde yalnızca yeni olaylar eklenir; aynı satır iki kez görünmez.

```js
const newEvts = (data.events || []).filter(e => e.id > lastSeenEventId);
newEvts.forEach(e => {
  if (e.id > lastSeenEventId) lastSeenEventId = e.id;
  // log satırı oluştur ve ekle
});
```

### 3.4 Alet Satırı Güncelleme (`updateToolRow`)

```js
function updateToolRow(id, state, timerFrames, picks, score, threshold) {
  const s   = STATUS[state] || STATUS.on_table;
  const sec = Math.floor(timerFrames / 10);
  // renk noktası, rozet, süre çubuğu, skor güncelleme
}
```

Örtüşme skoru görselleştirmesi:
- `score >= threshold` → `.tool-score.hot` → **yeşil**
- `score > 0 && score < threshold` → `.tool-score.warm` → **sarı**
- `score == 0` → `"—"` (alet görünmüyor)

### 3.5 Hassasiyet Slider Kontrolü

```js
function onSliderMove(val) {
  _syncThreshUI(parseInt(val));
  _pushThreshold(_currentThreshold);
}
```

Sunucuya gönderim **120 ms debounce** ile gerçekleşir; slider sürüklenirken her harekette API çağrısı yapılmaz:

```js
let _threshTimer = null;
function _pushThreshold(val) {
  clearTimeout(_threshTimer);
  _threshTimer = setTimeout(async () => {
    await fetch('/api/set_threshold', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({threshold: val})
    });
  }, 120);
}
```

4 preset butonu (`applyPreset`) aynı akışı tetikler ve aktif butonu `.active-pre` sınıfıyla işaretler.

### 3.6 Excel Dışa Aktarım

```js
async function exportExcel() {
  const res  = await fetch('/api/export_excel');
  const blob = await res.blob();
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href     = url;
  a.download = `surgical_report_${...}.xlsx`;
  a.click();
  URL.revokeObjectURL(url);   // bellek temizlenir
}
```

Dosya diske kaydedilmeden doğrudan tarayıcının indirme mekanizması tetiklenir.

### 3.7 Animasyonlu Sayaçlar (IntersectionObserver)

```js
const io = new IntersectionObserver(entries => {
  entries.forEach(e => {
    if (!e.isIntersecting) return;
    e.target.classList.add("visible");
    const num    = e.target.querySelector("[data-count]");
    const target = +num.dataset.count;
    const start  = performance.now();
    const tick = now => {
      const p = Math.min((now - start) / 1200, 1);
      num.textContent = Math.round(p * p * target);     // ease-in-quadratic
      if (p < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}, { threshold: 0.15 });
```

Elemanlar viewport'a %15 girince sayaç başlar; 1200 ms'lik ease-in-quadratic eğrisiyle hedefe ulaşır.

### 3.8 AI Yazma Efekti

```js
const AI_MSGS = [
  "Scalpel held for 47 seconds — 1.3× the average surgical duration...",
  // ... 4 örnek mesaj
];
function typeAI() {
  const el  = document.getElementById("aiTypedText");
  const msg = AI_MSGS[aiIdx++ % AI_MSGS.length];
  el.textContent = "";
  let i = 0;
  const iv = setInterval(() => {
    el.textContent += msg[i++];
    if (i >= msg.length) { clearInterval(iv); setTimeout(typeAI, 4200); }
  }, 26);
}
```

Her karakter 26 ms aralıkla yazılır; mesaj tamamlanınca 4.2 saniye beklenerek bir sonrakine geçilir.

---

## Özet Tablo

| | Kısım 1 — HTML | Kısım 2 — CSS | Kısım 3 — JavaScript |
|---|---|---|---|
| **Konu** | Sayfa yapısı ve DOM | Görsel tasarım ve animasyonlar | Etkileşim ve veri senkronizasyonu |
| **Kritik Özellik** | 3 katmanlı kamera alanı | `--css-custom-properties` tema sistemi | 600 ms polling + 120 ms debounce |
| **Dinamik İçerik** | `#toolList`, `#toolsGrid` JS ile doldurulur | 8 `@keyframes` animasyonu | `updateToolRow`, `pollState`, `exportExcel` |
| **Responsive** | `grid-template-columns` değişimleri | `@media (max-width: 800px)` | `IS_SERVER` bayrağı ile protokol tespiti |
