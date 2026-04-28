# Akıllı Cerrahi Alet Takip Sistemi — Günlük Proje Raporu

**Proje Adı:** AI Destekli Akıllı Cerrahi Asistan  
**Kullanılan Teknolojiler:** Python, YOLOv8, MediaPipe, Tkinter, Flask, OpenRouter API

---

## GÜN 1 — Model Eğitimi ve İlk Prototip

### 1. YOLOv8 Modelinin Eğitilmesi (`trsin.py`)

- `ultralytics` kütüphanesi kullanılarak YOLOv8n mimarisi yüklendi.
- Cerrahi aletlere ait özel veri seti (`data.yaml`) ile 25 epoch boyunca model eğitildi.
- Görüntü boyutu 640×640 olarak belirlendi; eğitim CPU üzerinde gerçekleştirildi.
- Eğitim sonucunda `best.pt` adlı özel ağırlık dosyası elde edildi.

### 2. İlk Masaüstü Uygulamasının Yazılması (`1.py`)

- Tkinter ile karanlık temalı (`#0a0a0a`) bir arayüz oluşturuldu.
- Kameradan anlık görüntü alınarak YOLOv8 modeli ile cerrahi alet tespiti yapıldı.
- El ve alet kutucukları (bounding box) ekrana çizildi.
- Her aletin "elde mi / masada mı / kayıp mı" olduğu `tool_states` sözlüğüyle takip edilmeye başlandı.
- OpenRouter API üzerinden her 20 saniyede bir yapay zeka raporu alındı (`nousresearch/hermes-3-l3.1-405b` modeli).
- Güven eşiği 0.35 olarak ayarlandı; teşhis kolaylığı için 0.20'ye düşürme denemesi yapıldı ve her karedeki tespit sayısı konsola yazdırıldı.

---

## GÜN 2 — Gelişmiş Masaüstü Uygulaması (`2.py`)

### Yapay Zeka ve Tespit Katmanı İyileştirmeleri

- YOLO'nun yanına **MediaPipe Hand Landmarker** eklendi; elin 21 anahtar noktası tespit edilerek el konumu çok daha hassas belirlendi (önceki sürümde sadece bounding box çakışması kullanılıyordu).
- El–alet etkileşimi için özel bir skor fonksiyonu yazıldı: `containment`, `center-in`, `IoU` ve `proximity` metrikleri ağırlıklı formülle birleştirildi:

  ```
  score = 0.40×containment + 0.30×center_in + 0.20×iou + 0.10×proximity
  ```

- Ani "false positive" hatalarını önlemek için 7 karelik **sliding window** (`held_history`) ile yumuşatma eklendi.

### Yeni Özellikler

- **Text-to-Speech (TTS):** `pyttsx3` ile sesli uyarılar (örn. "scalpel picked up", "Warning! Tool missing!").
- **Cerrahi Oturum Kontrolü:** "Start Surgery" / "End Surgery" butonları; ameliyat öncesi ve sonrası alet sayımı karşılaştırılarak eksik alet popup uyarısı verildi.
- **Zaman Uyarısı:** Herhangi bir alet 30 saniyeden fazla elde tutulduğunda hem görsel hem sesli alarm tetiklendi.
- **Raporlama:** CSV, PDF (`fpdf2`) ve Excel (`openpyxl`) formatlarında ayrıntılı rapor dışa aktarımı eklendi.
- **Arayüz İyileştirmeleri:** FPS sayacı, canlı dijital saat, kaydırılabilir alet panelleri, renk kodlu durum rozetleri (yeşil / kırmızı / sarı) ve ilerleme çubukları (progress bar) eklendi.
- AI modeli `deepseek/deepseek-r1` ile güncellendi, her 15 saniyede bir rapor alınmaya başlandı.

### Takip Edilen 16 Cerrahi Alet

`army_navy`, `bulldog`, `castroviejo`, `clamp`, `forceps`, `frazier`,
`hemostat`, `iris`, `mayo_metz`, `needle`, `potts`, `richardson`,
`scalpel`, `towel_clip`, `weitlaner`, `yankauer`

---

## GÜN 3 — Web Tabanlı Sürüm (`server.py` + `index.html`)

### Mimarinin Tarayıcıya Taşınması

- Tkinter arayüzü tamamen kaldırıldı; uygulamanın arkasına **Flask** web sunucusu yerleştirildi.
- Kamera görüntüsü MJPEG stream olarak `/video_feed` endpoint'i üzerinden tarayıcıya iletildi.
- Tüm durum bilgisi (timerlar, alet durumları, olay logu) `/api/state` endpoint'iyle JSON olarak sunuldu.

### REST API Tasarımı

| Endpoint | Metod | İşlev |
|---|---|---|
| `/api/state` | GET | Anlık tüm verileri döndürür |
| `/api/start` | POST | Ameliyatı başlatır, alet sayımını sıfırlar |
| `/api/end` | POST | Ameliyatı bitirir, eksik alet listesi döner |
| `/api/set_threshold` | POST | El–alet eşiğini dinamik ayarlar (0.05–0.90) |
| `/api/config` | GET | Mevcut eşik değerini döndürür |
| `/api/export_excel` | GET | Excel raporu tarayıcıya indirir |

### Teknik İyileştirmeler

- **Thread-safety:** `threading.Lock()` ile global durum koruması sağlandı; kamera döngüsü ayrı bir `daemon thread` üzerinde çalıştırıldı.
- **Graceful fallback:** YOLO veya MediaPipe yüklenemezse uygulama çökmeden devam eder; kamera açılamazsa ekranda hata görüntüsü gösterilir, sunucu ayakta kalır.
- **Dinamik eşik:** Kullanıcı, el–alet skorunu arayüzden anlık olarak ayarlayabilir (0.05–0.90 arası).
- **HUD overlay:** Köşe çizgileri, FPS değeri ve ameliyat durumu etiketi kamera görüntüsüne gömüldü.
- **Bellek yönetimi:** Olay logu son 120 kaydı tutar, taşınca otomatik budanır.

---

## Proje Gelişim Özeti

| Özellik | Gün 1 | Gün 2 | Gün 3 |
|---|:---:|:---:|:---:|
| Tespit Yöntemi | YOLO + BBox çakışması | YOLO + MediaPipe LM | YOLO + MediaPipe LM |
| Arayüz | Tkinter (basit) | Tkinter (gelişmiş) | Web (Flask + HTML) |
| Raporlama | Yok | CSV / PDF / Excel | Excel (API ile indir) |
| Sesli Uyarı | Yok | Var (TTS) | — |
| Çoklu Kullanıcı Desteği | Hayır | Hayır | Evet (tarayıcı üzerinden) |
| Thread Safety | Hayır | Kısmen | Tam (Lock) |
| Dinamik Ayar | Yok | Yok | Eşik slider (API) |
| AI Rapor Aralığı | 20 saniye | 15 saniye | 15 saniye |
