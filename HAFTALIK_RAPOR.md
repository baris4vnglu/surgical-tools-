# Akıllı Cerrahi Alet Takip Sistemi — Haftalık Proje Raporu

**Proje Adı:** Smart Surgical Assistant  
**Üniversite:** Near East University — Bilgisayar Mühendisliği  
**Kullanılan Teknolojiler:** Python · YOLOv8 · MediaPipe · Tkinter · Flask · OpenRouter AI

---

## HAFTA 1 — Araştırma ve Planlama

### Yapılanlar

Bu haftanın amacı projenin temelini oluşturmak ve hangi teknolojilerin kullanılacağına karar vermekti.

**Problem Tanımı:**  
Ameliyathanelerde cerrahi aletlerin hasta vücudunda unutulması ciddi bir tıbbi hata kaynağıdır. Bu riski azaltmak için gerçek zamanlı kamera görüntüsü üzerinden aletleri tanıyan, takip eden ve eksik alet uyarısı veren bir yapay zeka sistemi tasarlanmasına karar verildi.

**Teknoloji Araştırması:**

| Teknoloji | Alternatifler | Seçim Nedeni |
|---|---|---|
| Nesne tespiti | YOLOv5, Faster R-CNN | YOLOv8 — hızlı, güncel, kolay eğitim |
| El tespiti | OpenCV contouring, MediaPipe | MediaPipe — 21 keypoint, yüksek doğruluk |
| Arayüz | PyQt5, wxPython, Tkinter | Tkinter — kurulum gerektirmez, hızlı prototip |
| Web framework | Django, FastAPI | Flask — hafif, kamera streaming için uygun |
| AI raporlama | OpenAI GPT | OpenRouter / DeepSeek-R1 — maliyet avantajı |

**Takip Edilecek 16 Cerrahi Alet Belirlendi:**  
army_navy, bulldog, castroviejo, forceps, frazier, hemostat, iris, mayo_metz, needle, potts, richardson, scalpel, towel_clip, weitlaner, yankauer, scissors

**Proje Mimarisi Taslağı:**
```
Kamera → YOLOv8 (alet tespiti) → MediaPipe (el tespiti)
       → Durum Motoru (on_table / in_hand / missing)
       → Arayüz (Tkinter veya Web)
       → AI Rapor (DeepSeek-R1)
```

---

## HAFTA 2 — Veri Seti Hazırlama ve Model Eğitimi

### Yapılanlar

**Veri Seti:**  
Cerrahi aletlere ait görseller toplandı ve etiketlendi. Veri seti `data.yaml` yapılandırma dosyasıyla organize edildi. Her alet sınıfı için yeterli örnek sağlandı.

**Model Eğitimi (`trsin.py`):**

```python
from ultralytics import YOLO

model = YOLO('yolov8n.pt')          # Hazır YOLOv8 nano mimarisi
model.train(
    data=r"...\data\data.yaml",
    epochs=25,                       # Veri setine uygun epoch sayısı
    imgsz=640,                       # Standart giriş boyutu
    device='cpu'
)
```

**Eğitim Parametreleri:**

| Parametre | Değer | Açıklama |
|---|---|---|
| Mimari | YOLOv8n | Nano — hız/doğruluk dengesi |
| Epoch | 25 | Küçük veri seti için yeterli |
| imgsz | 640 | Standart kare boyutu |
| Cihaz | CPU | GPU yokken CPU üzerinde |

**Çıktı:** `best.pt` — en iyi doğruluk değerini veren model ağırlıkları

**Hafta Sonu Durumu:** Model başarıyla eğitildi. Test görüntülerinde cerrahi aletler tanınmaya başlandı.

---

## HAFTA 3 — İlk Masaüstü Prototipi

### Yapılanlar (`1.py` — İlk Sürüm)

Model eğitimi tamamlandıktan sonra ilk çalışan prototip yazıldı. Hedef: kameradan görüntü alıp aletleri gerçek zamanlı tanımak.

**Temel Özellikler:**

- **Tkinter arayüzü:** Karanlık tema (`#0a0a0a`), kamera paneli ve sağda alet takip paneli.
- **YOLOv8 entegrasyonu:** Her kare modelden geçirildi; güven eşiği `conf=0.35` olarak belirlendi.
- **Bounding box çizimi:** Tespit edilen aletlerin üzerine yeşil kutu ve isim yazıldı.
- **Durum takibi:** `tool_states` sözlüğü ile her aletin durumu (`on_table` / `in_hand` / `missing`) takip edildi.
- **El–alet etkileşimi:** El ve alet kutularının geometrik çakışması (`is_touching`) hesaplandı.
- **AI Rapor:** OpenRouter API üzerinden her 20 saniyede bir yapay zeka raporu alındı.

**Karşılaşılan Sorunlar:**
- Güven eşiği 0.35'te bazı aletler kaçırıldı → 0.20'ye düşürülerek test edildi.
- El tespiti sadece bounding box çakışmasına dayandığından hatalı "in_hand" tespitleri oluştu.
- Bu sorunlar bir sonraki haftanın geliştirme gündemine alındı.

---

## HAFTA 4 — Gelişmiş Masaüstü Uygulaması

### Yapılanlar (`2.py`)

İlk prototipin eksiklikleri giderilerek çok daha kapsamlı bir masaüstü uygulaması yazıldı.

**MediaPipe Hand Landmarker Entegrasyonu:**

İlk sürümdeki basit bounding box çakışması yerine MediaPipe'ın 21 el keypoint modeli kullanıldı. Her el için daha hassas sınır kutusu hesaplandı (25 px padding ile).

**El–Alet Örtüşme Skoru:**

Basit çakışma yerine dört metriği birleştiren bir skor fonksiyonu yazıldı:

```
score = 0.40 × containment
      + 0.30 × center_in
      + 0.20 × IoU
      + 0.10 × proximity
```

**7 Karelik Kayan Pencere (Sliding Window):**  
Ani "false positive" hatalarını önlemek için `deque(maxlen=7)` kullanıldı. Bir alet, son 7 karenin yarısından fazlasında "elde" görünüyorsa gerçekten elde sayıldı.

**Yeni Özellikler:**

- **TTS (Text-to-Speech):** `pyttsx3` ile sesli uyarılar — alet alındığında, bırakıldığında veya kaybolduğunda sesli bildirim.
- **Ameliyat Oturumu Kontrolü:** "Start Surgery" / "End Surgery" butonları; ameliyat öncesi ve sonrası alet sayımı karşılaştırıldı.
- **Zaman Uyarısı:** 30 saniyeden fazla elde tutulan alet için görsel ve sesli alarm.
- **Raporlama:** CSV, PDF (`fpdf2`) ve Excel (`openpyxl`) formatlarında dışa aktarım.
- **Arayüz İyileştirmeleri:** FPS sayacı, canlı dijital saat, kaydırılabilir paneller, renk kodlu rozetler, ilerleme çubukları.
- **AI Modeli:** `deepseek/deepseek-r1`'e geçildi, rapor aralığı 20 → 15 saniyeye indirildi.

---

## HAFTA 5 — Web Tabanlı Sürüm

### Yapılanlar (`server.py` + `index.html`)

Tkinter arayüzü tamamen kaldırılarak uygulama bir **Flask web sunucusuna** dönüştürüldü. Böylece sistem tarayıcı üzerinden, ağdaki herhangi bir cihazdan erişilebilir hale geldi.

**Mimari Değişikliği:**

| Bileşen | Eski (Tkinter) | Yeni (Flask) |
|---|---|---|
| Kamera döngüsü | `window.after()` | Ayrı `daemon thread` |
| Video görüntüleme | `ImageTk.PhotoImage` | MJPEG stream (`/video_feed`) |
| Durum yönetimi | Sınıf değişkenleri | Thread-safe `S` sözlüğü + `Lock()` |
| Veri aktarımı | Widget'a doğrudan yazım | REST API → JSON → JS polling |
| Excel export | `filedialog` + disk | `BytesIO` → tarayıcıya indir |

**REST API Uç Noktaları:**

| Endpoint | Metod | İşlev |
|---|---|---|
| `/video_feed` | GET | MJPEG kamera akışı |
| `/api/state` | GET | Anlık tüm verileri JSON döndürür |
| `/api/start` | POST | Ameliyatı başlatır |
| `/api/end` | POST | Ameliyatı bitirir, eksik alet listesi döner |
| `/api/set_threshold` | POST | Hassasiyet eşiğini günceller |
| `/api/export_excel` | GET | Excel raporu indirir |

**Web Arayüzü (`index.html`):**
- Tek dosyada HTML + CSS + JavaScript
- Karanlık tema, CSS custom properties ile renk sistemi
- 8 CSS animasyonu (slideDown, fadeUp, cardIn, blink, endPulse vb.)
- Gerçek ameliyat videosu Hero arka planında
- 600 ms polling ile canlı durum güncellemesi
- 120 ms debounce ile hassasiyet slider API senkronizasyonu
- IntersectionObserver ile scroll animasyonları

---

## HAFTA 6 — IP Kamera ve FPS Optimizasyonu

### Yapılanlar

Sistem laboratuvar ortamında test edildi. Gerçek ameliyathane senaryosuna yaklaştırmak için IP kamera desteği ve performans iyileştirmeleri yapıldı.

**IP Kamera Desteği (`server.py` + `1.py`):**

```python
# Ortam değişkeniyle esnek kamera seçimi
_raw = os.getenv("CAMERA_SOURCE", "0")
CAMERA_SOURCE = int(_raw) if _raw.isdigit() else _raw
```

| Kamera Türü | CAMERA_SOURCE Değeri |
|---|---|
| USB Webcam | `0` |
| DroidCam (Android/iOS) | `http://192.168.x.x:4747/video` |
| IP Webcam (Android) | `http://192.168.x.x:8080/video` |
| RTSP | `rtsp://user:pass@ip:554/stream` |

IP kamera seçildiğinde `CAP_PROP_*` ayarları atlandı; çözünürlük ve FPS uzak uygulama tarafından belirleniyor.

**FPS Optimizasyonları (`server.py`):**

| Değişiklik | Eski Değer | Yeni Değer | Kazanım |
|---|---|---|---|
| Kamera buffer | — | `BUFFERSIZE=1` | Bayat kare birikimini önler |
| Kamera FPS | — | `CAP_PROP_FPS=60` | Sürücüden max FPS ister |
| YOLO imgsz | 640 | 416 | Inference ~2× hızlanır |
| JPEG kalitesi | 78 | 65 | Daha küçük paket, hızlı transfer |
| Stream sleep | 0.033 s | 0.013 s | ~30 FPS → ~75 FPS üst sınır |

**Denenen Ama Geri Alınan Yaklaşım:**  
Her 2 karede bir YOLO inference çalıştırma fikri test edildi. Ancak `detected_tools={}` boş kaldığı karelerde durum motoru tüm aletleri `missing` olarak işaretliyordu. Bu yüzden bu yaklaşım kullanılmadı.

---

## HAFTA 7 — Son Düzenlemeler ve Alet Listesi Güncellemesi

### Yapılanlar

**Alet Listesi Güncellemeleri:**

- `clamp` modelin iyi tanımaması nedeniyle listeden çıkarıldı.
- `makas` (Türkçe tanım) eklendi.
- `scissors` (İngilizce tanım) ayrı sınıf olarak eklendi.
- Toplam alet sayısı: **17**

Her üç dosyada (`server.py`, `1.py`, `index.html`) aynı anda güncellendi:
```python
TOOLS = [
    "army_navy", "bulldog",    "castroviejo",
    "forceps",   "frazier",    "hemostat",   "iris",
    "mayo_metz", "needle",     "potts",      "richardson",
    "scalpel",   "towel_clip", "weitlaner",  "yankauer",
    "makas",     "scissors",
]
```

**`1.py` Tam Yeniden Yazımı:**

İlk prototip olan `1.py`, `server.py`'nin tüm backend mantığıyla yeniden yazıldı — arayüz Tkinter olarak korundu. Bu sayede web sunucusu olmadan da tam özellikli sistem çalışabiliyor.

`1.py`'ye eklenen özellikler:
- MediaPipe Hand Landmarker (21 keypoint)
- `_score()` örtüşme fonksiyonu (server.py ile birebir aynı)
- 7 karelik sliding window
- CAMERA_SOURCE (IP kamera desteği)
- YOLO imgsz=416
- Hassasiyet slider + preset butonlar
- Ameliyat start/end kontrolü
- TTS, zaman uyarısı
- CSV + PDF + Excel export
- FPS sayacı, canlı saat, olay logu

**Web Sitesi Son Düzenlemeleri (`index.html`):**
- Tüm metin İngilizce'ye çevrildi.
- Alet galerisi ve istatistik sayaçları güncel alet sayısına göre düzeltildi.

---

## Proje Genel Özeti

| Hafta | Ana Konu | Temel Çıktı |
|---|---|---|
| 1 | Araştırma & Planlama | Teknoloji kararları, sistem mimarisi |
| 2 | Veri Seti & Model Eğitimi | `best.pt` model dosyası |
| 3 | İlk Prototip | Çalışan Tkinter uygulaması (temel) |
| 4 | Gelişmiş Masaüstü App | MediaPipe, TTS, export, ameliyat kontrolü |
| 5 | Web Sürümü | Flask API + HTML/CSS/JS arayüzü |
| 6 | IP Kamera & FPS | Telefon kamerası, ~2× hız artışı |
| 7 | Son Düzenlemeler | Alet listesi, 1.py yeniden yazımı |

### Kullanılan Kütüphaneler

```
ultralytics     → YOLOv8 model eğitimi ve inference
mediapipe       → El keypoint tespiti
opencv-python   → Kamera ve görüntü işleme
flask           → Web sunucusu ve REST API
tkinter         → Masaüstü arayüz
pillow          → Görüntü dönüşümü (Tkinter render)
pyttsx3         → Text-to-speech sesli uyarı
fpdf2           → PDF rapor oluşturma
openpyxl        → Excel rapor oluşturma
requests        → OpenRouter AI API çağrısı
```
