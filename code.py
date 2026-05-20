import os, sys, io, time, threading, collections
from datetime import datetime

# ── Tcl/Tk path fix for Windows venv ──────────────────────
def _fix_tcl():
    candidates = []
    exe  = sys.executable
    base = os.path.dirname(os.path.dirname(exe))
    cfg  = os.path.join(base, 'pyvenv.cfg')
    if os.path.exists(cfg):
        with open(cfg) as f:
            for line in f:
                if line.lower().startswith('home'):
                    home = line.split('=', 1)[1].strip()
                    candidates += [home, os.path.dirname(home)]
                    break
    candidates += [
        os.path.dirname(exe),
        os.path.dirname(os.path.dirname(exe)),
        # full installer path (has tcl even when base install doesn't)
        r"C:\Users\baris\AppData\Local\Programs\Python\Python313",
    ]
    for python_dir in candidates:
        tcl = os.path.join(python_dir, 'tcl', 'tcl8.6')
        tk_ = os.path.join(python_dir, 'tcl', 'tk8.6')
        if os.path.exists(tcl):
            os.environ['TCL_LIBRARY'] = tcl
            os.environ['TK_LIBRARY']  = tk_
            return
_fix_tcl()

import tkinter as tk
from tkinter import ttk, messagebox

import cv2
from PIL import Image, ImageTk

# ── YOLO ──────────────────────────────────────────────────
try:
    from ultralytics import YOLO
    MODEL_PATH = r"C:\Users\hüseyin koç\Desktop\tools\runs\detect\weights.pt"
    model = YOLO(MODEL_PATH)
    MODEL_OK = True
    print("[OK] YOLO model loaded")
except Exception as e:
    model = None
    MODEL_OK = False
    print(f"[WARN] YOLO failed: {e}")


# ── Excel ──────────────────────────────────────────────────
try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    EXCEL_OK = True
except ImportError:
    EXCEL_OK = False

# ── Detection enhancements ────────────────────────────────
_clahe             = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
_recent_detections = collections.deque(maxlen=8)   # temporal smoothing penceresi

CONF_THRESH = 0.25   # düşük eşik → daha fazla aday, temporal smoothing filtreler
NMS_IOU     = 0.45   # çakışan kutu filtresi
INFER_SIZE  = 800    # 640→800: küçük aletlerde belirgin iyileşme
SMOOTH_MIN  = 3      # 8 frame'den en az 3'ünde görülmeli → false positive azaltır


def _preprocess(frame):
    """CLAHE + unsharp masking: kontrast ve kenar netliği."""
    lab     = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l       = _clahe.apply(l)
    out     = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)
    blur    = cv2.GaussianBlur(out, (0, 0), 3)
    return cv2.addWeighted(out, 1.5, blur, -0.5, 0)

# ── Camera source ──────────────────────────────────────────
CAMERA_SOURCE = 0   # bilgisayar kamerası

# ── Tools ─────────────────────────────────────────────────
TOOLS = [
    "army_navy","bulldog","castroviejo","forceps","frazier",
    "hemostat","iris","mayo_metz","needle","potts","richardson",
    "scalpel","towel_clip","weitlaner","yankauer",
]

TOOL_LABELS = {t: t.replace("_", " ").title() for t in TOOLS}

# ── State ──────────────────────────────────────────────────
_lock = threading.Lock()
S = {
    'surgery_active':  False,
    'surgery_start':   None,
    'tool_timers':     {t: 0 for t in TOOLS},
    'tool_states':     {t: 'on_table' for t in TOOLS},
    'tool_pick_count': {t: 0 for t in TOOLS},
    'pre_tools':       {},
    'last_detected':   set(),
    'events':          [],
    'event_seq':       0,
    'fps':             0,
    '_fps_cnt':        0,
    '_fps_t':          time.time(),
}

# Ham kare (display thread okur — YOLO beklemeden)
_raw_frame  = None
_raw_lock   = threading.Lock()

# YOLO sonuçları (detect thread yazar, display thread çizer)
# Her eleman: (x1, y1, x2, y2, label, bgr_color, conf)
_det_boxes  = []
_det_lock   = threading.Lock()

# ── Helpers ────────────────────────────────────────────────
def _evt(msg, level="ok"):
    S['event_seq'] += 1
    ts = datetime.now().strftime("%H:%M:%S")
    S['events'].append({'id': S['event_seq'], 'ts': ts, 'level': level, 'msg': msg})
    if len(S['events']) > 120:
        del S['events'][:60]


STATUS_BGR = {
    'on_table': (80,  200,  80),
    'in_use':   (73,   81, 248),
}

# ── Thread 1: Sadece kamera okuma (mümkün olan en hızlı) ──
def _open_cap():
    cap = cv2.VideoCapture(CAMERA_SOURCE)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS,          30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE,   1)
    return cap

def _capture_loop():
    """Kamerayı sürekli okur; sadece en son kareyi _raw_frame'de tutar."""
    global _raw_frame
    cap        = _open_cap()
    fail_count = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            fail_count += 1
            if fail_count > 30:
                print("[WARN] Kamera okunamıyor, yeniden bağlanılıyor...")
                cap.release()
                time.sleep(1.0)
                cap = _open_cap()
                fail_count = 0
            else:
                time.sleep(0.03)
            continue
        fail_count = 0
        with _raw_lock:
            _raw_frame = frame
    cap.release()


# ── Thread 2: YOLO + MediaPipe (ağır iş, display'i bloklamaz) ─
def _detect_loop():
    """_raw_frame üzerinde YOLO+MP çalıştırır, sonuçları _det_boxes'a yazar."""
    global _det_boxes
    last_id = None
    while True:
        with _raw_lock:
            frame = _raw_frame
        if frame is None or id(frame) == last_id:
            time.sleep(0.01)
            continue
        last_id   = id(frame)
        work      = frame.copy()
        h_f, w_f  = work.shape[:2]

        # FPS sayacı
        with _lock:
            S['_fps_cnt'] += 1
            now = time.time()
            if now - S['_fps_t'] >= 1.0:
                S['fps']      = S['_fps_cnt']
                S['_fps_cnt'] = 0
                S['_fps_t']   = now

        # Kontrast + kenar netleştirme
        work = _preprocess(work)

        # YOLO algılama — ByteTrack + TTA
        detected_tools = {}
        detected_conf  = {}
        new_boxes      = []
        if MODEL_OK and model:
            try:
                res = model.track(work, conf=CONF_THRESH, iou=NMS_IOU,
                                  verbose=False, imgsz=INFER_SIZE,
                                  persist=True, tracker="bytetrack.yaml",
                                  augment=True)[0]
                for box in res.boxes:
                    c   = box.xyxy[0].tolist()
                    lbl = model.names[int(box.cls[0])].lower()
                    cf  = float(box.conf[0])
                    if lbl in TOOLS:
                        if lbl not in detected_conf or cf > detected_conf[lbl]:
                            detected_tools[lbl] = c
                            detected_conf[lbl]  = cf
                    with _lock:
                        bc = STATUS_BGR.get(S['tool_states'].get(lbl, 'on_table'), (88, 166, 255))
                    x1,y1,x2,y2 = int(c[0]),int(c[1]),int(c[2]),int(c[3])
                    new_boxes.append((x1, y1, x2, y2, lbl, bc, cf))
            except Exception:
                pass

        with _det_lock:
            _det_boxes = new_boxes

        # Temporal smoothing: son 8 frame'den en az 3'ünde görülen = "algılandı"
        _recent_detections.append(set(detected_tools.keys()))
        counts = collections.Counter(t for fs in _recent_detections for t in fs)
        smoothed_tools = {t for t, c in counts.items() if c >= SMOOTH_MIN}

        # Durum güncelleme (smoothed sonuç kullanılır)
        with _lock:
            S['last_detected'] = smoothed_tools
            s_active = S['surgery_active']

        if s_active:
            with _lock:
                for tool in TOOLS:
                    in_view    = tool in smoothed_tools
                    prev_state = S['tool_states'][tool]
                    if in_view:
                        S['tool_timers'][tool] += 1
                        S['tool_states'][tool]  = 'in_use'
                        if prev_state != 'in_use':
                            S['tool_pick_count'][tool] += 1
                            _evt(f"{TOOL_LABELS[tool]} kullanımda "
                                 f"(#{S['tool_pick_count'][tool]})", "ok")
                    else:
                        if prev_state == 'in_use':
                            S['tool_states'][tool] = 'on_table'


# ── Colours ────────────────────────────────────────────────
BG       = '#0d1117'
BG_PANEL = '#161b22'
BG_CARD  = '#1c2128'
ACCENT   = '#58a6ff'
GREEN    = '#3fb950'
RED      = '#f85149'
YELLOW   = '#d29922'
CYAN     = '#39d0d8'
TEXT     = '#e6edf3'
TEXT_DIM = '#8b949e'
BORDER   = '#30363d'

# ── GUI ────────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Smart Surgical Assistant — Near East University")
        self.configure(bg=BG)
        self.minsize(1300, 720)
        self.resizable(True, True)

        self._imgtk      = None
        self._last_evt   = 0

        self._build()
        self._tick_video()
        self._tick_state()

    # ── Layout ────────────────────────────────────────────
    def _build(self):
        # Video pane
        self.canvas = tk.Canvas(self, bg='#000000', highlightthickness=0)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Right panel (fixed width)
        panel = tk.Frame(self, bg=BG_PANEL, width=580)
        panel.pack(side=tk.RIGHT, fill=tk.Y)
        panel.pack_propagate(False)

        # Logo
        try:
            _lpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "image.png")
            _limg  = Image.open(_lpath).convert("RGBA")
            _limg  = _limg.resize((90, 90), Image.LANCZOS)
            _bg    = Image.new("RGBA", _limg.size, (22, 27, 34, 255))  # BG_PANEL
            _bg.paste(_limg, mask=_limg.split()[3])
            self._logo_imgtk = ImageTk.PhotoImage(_bg.convert("RGB"))
            tk.Label(panel, image=self._logo_imgtk, bg=BG_PANEL).pack(pady=(18, 4))
        except Exception:
            self._logo_imgtk = None

        # Title
        tk.Label(panel, text="Smart Surgical Assistant",
                 bg=BG_PANEL, fg=ACCENT, font=('Segoe UI', 17, 'bold')
                 ).pack(pady=(6, 2))
        tk.Label(panel, text="Near East University",
                 bg=BG_PANEL, fg=TEXT_DIM, font=('Segoe UI', 11)
                 ).pack(pady=(0, 18))
        self._sep(panel)

        # Surgery control
        self._section(panel, "SURGERY CONTROL")
        btn_row = tk.Frame(panel, bg=BG_PANEL)
        btn_row.pack(fill=tk.X, padx=16, pady=(0, 6))
        self.btn_start = tk.Button(
            btn_row, text="▶  Start", bg=GREEN, fg='#0d1117',
            font=('Segoe UI', 12, 'bold'), relief=tk.FLAT,
            padx=14, pady=12, cursor='hand2', command=self._start)
        self.btn_start.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.btn_end = tk.Button(
            btn_row, text="■  End", bg=BG_CARD, fg=TEXT_DIM,
            font=('Segoe UI', 12, 'bold'), relief=tk.FLAT,
            padx=14, pady=12, cursor='hand2', command=self._end,
            state=tk.DISABLED)
        self.btn_end.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._timer_var = tk.StringVar(value="--:--:--")
        tk.Label(panel, textvariable=self._timer_var,
                 bg=BG_PANEL, fg=CYAN, font=('Consolas', 32, 'bold')
                 ).pack(pady=10)
        self._sep(panel)

        # Tool status
        self._section(panel, "TOOL STATUS")
        tool_frame = tk.Frame(panel, bg=BG_PANEL)
        tool_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 4))
        vsb = tk.Scrollbar(tool_frame, bg=BG_PANEL, troughcolor=BG_CARD, width=10)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tool_txt = tk.Text(
            tool_frame, bg=BG_CARD, fg=TEXT, font=('Consolas', 11),
            relief=tk.FLAT, state=tk.DISABLED, yscrollcommand=vsb.set,
            cursor='arrow', wrap=tk.NONE)
        self.tool_txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.config(command=self.tool_txt.yview)
        for tag, col in (('g', GREEN),('r', RED),('y', YELLOW),('d', TEXT_DIM)):
            self.tool_txt.tag_config(tag, foreground=col)
        self._sep(panel)

        # Event log
        self._section(panel, "EVENT LOG")
        log_frame = tk.Frame(panel, bg=BG_PANEL)
        log_frame.pack(fill=tk.BOTH, padx=12, pady=(0, 4))
        lsb = tk.Scrollbar(log_frame, bg=BG_PANEL, troughcolor=BG_CARD, width=10)
        lsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.evt_txt = tk.Text(
            log_frame, bg=BG_CARD, fg=TEXT_DIM, font=('Consolas', 10),
            relief=tk.FLAT, state=tk.DISABLED, yscrollcommand=lsb.set,
            height=8, cursor='arrow', wrap=tk.WORD)
        self.evt_txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        lsb.config(command=self.evt_txt.yview)
        for tag, col in (('ok', GREEN),('warn', YELLOW),('err', RED),('ai', CYAN),('ts', TEXT_DIM)):
            self.evt_txt.tag_config(tag, foreground=col)

        # Export
        tk.Button(
            panel, text="⬇  Export Excel Report (.xlsx)",
            bg=BG_CARD, fg=ACCENT, font=('Segoe UI', 11, 'bold'),
            relief=tk.FLAT, pady=12, cursor='hand2', command=self._export
        ).pack(fill=tk.X, padx=16, pady=(6, 16))

    def _sep(self, p):
        tk.Frame(p, bg=BORDER, height=1).pack(fill=tk.X, padx=12, pady=5)

    def _section(self, p, text):
        tk.Label(p, text=text, bg=BG_PANEL, fg=TEXT_DIM,
                 font=('Segoe UI', 10, 'bold')).pack(anchor='w', padx=16, pady=(8, 4))

    # ── Video tick (fast — YOLO'yu beklemiyor) ────────────
    def _tick_video(self):
        with _raw_lock:
            frame = _raw_frame
        if frame is not None:
            display = frame.copy()
            fh, fw  = display.shape[:2]

            # YOLO kutularını çiz (en son sonuç, arka planda güncelleniyor)
            with _det_lock:
                boxes = list(_det_boxes)
            for (x1, y1, x2, y2, lbl, bc, cf) in boxes:
                cv2.rectangle(display, (x1,y1),(x2,y2), bc, 2)
                cv2.putText(display, f"{lbl} {cf:.2f}", (x1, max(y1-6,12)),
                            0, 0.42, (230,237,243), 1)

            # HUD
            with _lock:
                fps_v = S['fps']
                s_act = S['surgery_active']
            cv2.putText(display, f"FPS:{fps_v}", (fw-80, 22), 0, 0.55, (57,208,216), 2)
            s_txt = "SURGERY ACTIVE" if s_act else "STANDBY"
            s_col = (80,200,80) if s_act else (120,120,120)
            cv2.putText(display, s_txt, (10, fh-12), 0, 0.48, s_col, 1)
            SZ=22; T=2
            for px,py,dx,dy in [(0,0,1,1),(fw,0,-1,1),(0,fh,1,-1),(fw,fh,-1,-1)]:
                cv2.line(display,(px,py),(px+dx*SZ,py),(88,166,255),T)
                cv2.line(display,(px,py),(px,py+dy*SZ),(88,166,255),T)

            cw = self.canvas.winfo_width()
            ch = self.canvas.winfo_height()
            if cw > 10 and ch > 10:
                scale  = min(cw/fw, ch/fh)
                nw, nh = int(fw*scale), int(fh*scale)
                resized = cv2.resize(display, (nw, nh), interpolation=cv2.INTER_LINEAR)
                rgb     = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
                pil     = Image.fromarray(rgb)
                self._imgtk = ImageTk.PhotoImage(pil)
                self.canvas.delete('all')
                x = (cw - nw) // 2
                y = (ch - nh) // 2
                self.canvas.create_image(x, y, anchor=tk.NW, image=self._imgtk)
        self.after(16, self._tick_video)   # ~60 FPS hedef

    # ── State tick (slow) ─────────────────────────────────
    def _tick_state(self):
        with _lock:
            s_active = S['surgery_active']
            elapsed  = int(time.time() - S['surgery_start']) \
                       if s_active and S['surgery_start'] else 0
            states   = dict(S['tool_states'])
            timers   = dict(S['tool_timers'])
            picks    = dict(S['tool_pick_count'])
            events   = list(S['events'])

        # Timer label
        if s_active:
            h = elapsed//3600; m = (elapsed%3600)//60; s = elapsed%60
            self._timer_var.set(f"{h:02d}:{m:02d}:{s:02d}")

        # Buttons
        if s_active:
            self.btn_start.config(state=tk.DISABLED, bg=BG_CARD, fg=TEXT_DIM)
            self.btn_end.config(state=tk.NORMAL, bg=RED, fg='white')
        else:
            self.btn_start.config(state=tk.NORMAL, bg=GREEN, fg='#0d1117')
            self.btn_end.config(state=tk.DISABLED, bg=BG_CARD, fg=TEXT_DIM)

        # Tool list
        self.tool_txt.config(state=tk.NORMAL)
        self.tool_txt.delete('1.0', tk.END)
        for tool in TOOLS:
            st  = states.get(tool, 'on_table')
            sec = timers.get(tool, 0) // 10
            pk  = picks.get(tool, 0)
            tag   = 'g' if st == 'on_table' else 'r'
            badge = {'on_table': 'TABLE  ', 'in_use': 'USING  '}.get(st, 'TABLE  ')
            line = f"  {TOOL_LABELS[tool]:<17} [{badge}] {sec:>4}s  ×{pk}\n"
            self.tool_txt.insert(tk.END, line, tag)
        self.tool_txt.config(state=tk.DISABLED)

        # Event log
        new_evts = [e for e in events if e['id'] > self._last_evt]
        if new_evts:
            self.evt_txt.config(state=tk.NORMAL)
            for e in new_evts:
                self._last_evt = max(self._last_evt, e['id'])
                lvl = e['level'] if e['level'] in ('ok','warn','err','ai') else 'ts'
                self.evt_txt.insert(tk.END, f"[{e['ts']}] ", 'ts')
                self.evt_txt.insert(tk.END, e['msg'] + "\n", lvl)
            self.evt_txt.see(tk.END)
            self.evt_txt.config(state=tk.DISABLED)

        self.after(400, self._tick_state)

    # ── Surgery control ───────────────────────────────────
    def _start(self):
        with _lock:
            if S['surgery_active']:
                return
            S['surgery_active'] = True
            S['surgery_start']  = time.time()
            for t in TOOLS:
                S['tool_timers'][t]     = 0
                S['tool_states'][t]     = 'on_table'
                S['tool_pick_count'][t] = 0
            S['pre_tools'] = {t: (t in S['last_detected']) for t in TOOLS}
            present = [t for t in TOOLS if S['pre_tools'].get(t)]
            _evt("=== SURGERY STARTED ===", "ok")
            _evt(f"Initial tools: {len(present)} detected", "ok")

    def _end(self):
        with _lock:
            if not S['surgery_active']:
                return
            S['surgery_active'] = False
            post    = {t: (t in S['last_detected']) for t in TOOLS}
            missing = [t for t in TOOLS if S['pre_tools'].get(t) and not post[t]]
            elapsed = int(time.time() - S['surgery_start']) if S['surgery_start'] else 0
            _evt("=== SURGERY ENDED ===", "ok")
            if missing:
                _evt(f"MISSING TOOLS: {', '.join(missing)}", "err")
            else:
                _evt("All tools verified. None missing.", "ok")
            top3 = sorted(TOOLS, key=lambda t: S['tool_timers'][t], reverse=True)[:3]
            top3 = [f"{t}:{S['tool_timers'][t]//10}s" for t in top3 if S['tool_timers'][t] > 0]
            if top3:
                _evt("Most used: " + ", ".join(top3), "ai")
        self._timer_var.set("--:--:--")
        if missing:
            messagebox.showwarning("Missing Tools",
                                   "Missing tools detected:\n" + "\n".join(
                                       TOOL_LABELS.get(t, t) for t in missing))

    # ── Excel export ──────────────────────────────────────
    def _export(self):
        if not EXCEL_OK:
            messagebox.showerror("Error", "openpyxl not installed.\npip install openpyxl")
            return
        with _lock:
            timers   = dict(S['tool_timers'])
            states   = dict(S['tool_states'])
            picks    = dict(S['tool_pick_count'])
            events   = list(S['events'])
            s_active = S['surgery_active']
            s_start  = S['surgery_start']
            elapsed  = int(time.time() - s_start) if s_active and s_start else 0

        wb      = openpyxl.Workbook()
        ts_str  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        hdr_fill   = PatternFill("solid", fgColor="1C2128")
        title_fill = PatternFill("solid", fgColor="161B22")
        dark_fill  = PatternFill("solid", fgColor="0D1117")
        mid_fill   = PatternFill("solid", fgColor="161B22")

        title_font  = Font(name="Calibri", bold=True, color="E6EDF3", size=13)
        hdr_font    = Font(name="Calibri", bold=True, color="58A6FF", size=10)
        normal_font = Font(name="Calibri", color="E6EDF3", size=10)
        dim_font    = Font(name="Calibri", color="8B949E", size=9)
        green_font  = Font(name="Calibri", bold=True, color="3FB950", size=10)
        red_font    = Font(name="Calibri", bold=True, color="F85149", size=10)
        yellow_font = Font(name="Calibri", bold=True, color="D29922", size=10)

        green_fill  = PatternFill("solid", fgColor="0D3320")
        red_fill    = PatternFill("solid", fgColor="3D1210")
        yellow_fill = PatternFill("solid", fgColor="3D2C00")

        thin = Border(
            left=Side(style="thin", color="30363D"),
            right=Side(style="thin", color="30363D"),
            top=Side(style="thin", color="30363D"),
            bottom=Side(style="thin", color="30363D"),
        )
        center = Alignment(horizontal="center", vertical="center")
        left   = Alignment(horizontal="left",   vertical="center")

        ws1 = wb.active
        ws1.title = "Tool Summary"
        ws1.merge_cells("A1:F1")
        ws1["A1"] = "Smart Surgical Assistant — Session Report"
        ws1["A1"].font = title_font; ws1["A1"].fill = title_fill; ws1["A1"].alignment = center
        ws1.row_dimensions[1].height = 28
        ws1.merge_cells("A2:F2")
        ws1["A2"] = f"Generated: {ts_str}   |   Surgery active: {'Yes' if s_active else 'No'}"
        ws1["A2"].font = dim_font; ws1["A2"].fill = title_fill; ws1["A2"].alignment = left

        for col, h in enumerate(["Tool Name","Use Time (s)","Pick Count","Status","Notes"], 1):
            cell = ws1.cell(row=4, column=col, value=h)
            cell.font = hdr_font; cell.fill = hdr_fill; cell.border = thin; cell.alignment = center
        ws1.row_dimensions[4].height = 20

        status_map = {
            'on_table': ("ON TABLE", green_font, green_fill),
            'in_use':   ("USING",    red_font,   red_fill),
        }
        for i, tool in enumerate(TOOLS):
            r   = i + 5
            sec = timers[tool] // 10
            bg  = dark_fill if i % 2 == 0 else mid_fill
            stxt, sfont, sfill = status_map.get(states[tool], status_map['on_table'])
            for col, val in enumerate([TOOL_LABELS[tool], sec, picks[tool], stxt, ""], 1):
                cell = ws1.cell(row=r, column=col, value=val)
                cell.border = thin
                cell.alignment = left if col == 1 else center
                if col == 4:
                    cell.font = sfont; cell.fill = sfill
                else:
                    cell.font = normal_font; cell.fill = bg
        for col, w in enumerate([22,14,12,14,20], 1):
            ws1.column_dimensions[get_column_letter(col)].width = w

        ws2 = wb.create_sheet("Event Log")
        ws2.merge_cells("A1:C1")
        ws2["A1"] = "Event Log"
        ws2["A1"].font = title_font; ws2["A1"].fill = title_fill; ws2["A1"].alignment = center
        ws2.row_dimensions[1].height = 26
        for col, h in enumerate(["Timestamp","Level","Message"], 1):
            cell = ws2.cell(row=2, column=col, value=h)
            cell.font = hdr_font; cell.fill = hdr_fill; cell.border = thin; cell.alignment = center

        lvl_colors = {
            "ok":  ("3FB950","0D3320"), "warn": ("D29922","3D2C00"),
            "err": ("F85149","3D1210"), "ai":   ("39D0D8","0D2A2C"),
            "":    ("8B949E","161B22"),
        }
        for i, ev in enumerate(events):
            r = i + 3
            fg, bg_hex = lvl_colors.get(ev['level'], ("8B949E","161B22"))
            ef = Font(name="Calibri", color=fg, size=9)
            efill = PatternFill("solid", fgColor=bg_hex)
            for col, val in enumerate([ev['ts'], ev['level'].upper(), ev['msg']], 1):
                cell = ws2.cell(row=r, column=col, value=val)
                cell.font = ef; cell.fill = efill; cell.border = thin
                cell.alignment = Alignment(horizontal="left", vertical="center",
                                           wrap_text=(col == 3))
        ws2.column_dimensions["A"].width = 14
        ws2.column_dimensions["B"].width = 10
        ws2.column_dimensions["C"].width = 70

        # ── AI Analysis sheet ────────────────────────────────
        ws3 = wb.create_sheet("AI Analysis")

        section_font = Font(name="Calibri", bold=True, color="D29922", size=11)
        section_fill = PatternFill("solid", fgColor="1C2128")
        metric_font  = Font(name="Calibri", color="E6EDF3", size=10)
        value_font   = Font(name="Calibri", bold=True, color="58A6FF", size=10)

        ws3.merge_cells("A1:D1")
        ws3["A1"] = "AI Analysis Report — Smart Surgical Assistant"
        ws3["A1"].font = Font(name="Calibri", bold=True, color="E6EDF3", size=14)
        ws3["A1"].fill = title_fill; ws3["A1"].alignment = center
        ws3.row_dimensions[1].height = 30
        ws3.merge_cells("A2:D2")
        ws3["A2"] = f"Generated: {ts_str}"
        ws3["A2"].font = dim_font; ws3["A2"].fill = title_fill; ws3["A2"].alignment = left

        total_tool_secs = sum(timers[t] // 10 for t in TOOLS)
        used_tools      = [t for t in TOOLS if timers[t] > 0]
        unused_tools    = [t for t in TOOLS if timers[t] == 0]
        sorted_by_time  = sorted(TOOLS, key=lambda t: timers[t], reverse=True)
        high_freq_tools = [t for t in TOOLS if picks[t] >= 3]
        brief_use_tools = [t for t in TOOLS if 0 < timers[t] // 10 < 5]
        total_picks     = sum(picks[t] for t in TOOLS)
        avg_use_sec     = (total_tool_secs // len(used_tools)) if used_tools else 0
        start_str       = datetime.fromtimestamp(s_start).strftime("%H:%M:%S") if s_start else "N/A"

        def _ws3_section(r, label):
            ws3.merge_cells(f"A{r}:D{r}")
            ws3[f"A{r}"] = label
            ws3[f"A{r}"].font = section_font
            ws3[f"A{r}"].fill = section_fill
            ws3[f"A{r}"].alignment = Alignment(horizontal="left", vertical="center")
            ws3.row_dimensions[r].height = 22
            return r + 1

        # SESSION OVERVIEW
        row = 4
        row = _ws3_section(row, "SESSION OVERVIEW")
        overview = [
            ("Surgery Start Time",   start_str),
            ("Total Tools Defined",  str(len(TOOLS))),
            ("Tools Used",           str(len(used_tools))),
            ("Tools Unused",         str(len(unused_tools))),
            ("Total Pick Events",    str(total_picks)),
            ("Total Tool-Seconds",   f"{total_tool_secs} s"),
            ("Avg Use Time / Tool",  f"{avg_use_sec} s"),
        ]
        for i, (lbl, val) in enumerate(overview):
            bg = dark_fill if i % 2 == 0 else mid_fill
            c1 = ws3.cell(row=row, column=1, value=lbl)
            c1.font = metric_font; c1.fill = bg; c1.border = thin; c1.alignment = left
            c2 = ws3.cell(row=row, column=2, value=val)
            c2.font = value_font; c2.fill = bg; c2.border = thin; c2.alignment = center
            for col in [3, 4]:
                cx = ws3.cell(row=row, column=col, value="")
                cx.fill = bg; cx.border = thin
            row += 1

        row += 1

        # TOOL PERFORMANCE RANKING
        row = _ws3_section(row, "TOOL PERFORMANCE RANKING")
        for col, h in enumerate(["Rank", "Tool", "Use Time (s)", "Picks", "Assessment"], 1):
            cell = ws3.cell(row=row, column=col, value=h)
            cell.font = hdr_font; cell.fill = hdr_fill; cell.border = thin; cell.alignment = center
        ws3.row_dimensions[row].height = 18
        row += 1

        for rank, tool in enumerate(sorted_by_time, 1):
            sec = timers[tool] // 10
            pk  = picks[tool]
            bg  = dark_fill if rank % 2 == 0 else mid_fill
            if sec == 0:
                assessment, af, afill = "Not used", dim_font, bg
            elif sec >= 60:
                assessment, af, afill = "Primary instrument", green_font, green_fill
            elif pk >= 3:
                assessment, af, afill = "Frequently swapped", yellow_font, yellow_fill
            elif sec < 5:
                assessment, af, afill = "Brief use", dim_font, bg
            else:
                assessment, af, afill = "Standard use", normal_font, bg
            vals = [rank, TOOL_LABELS[tool], sec, pk, assessment]
            for col, val in enumerate(vals, 1):
                cell = ws3.cell(row=row, column=col, value=val)
                cell.border = thin
                cell.alignment = left if col == 2 else center
                if col == 5:
                    cell.font = af; cell.fill = afill
                else:
                    cell.font = dim_font if sec == 0 else (value_font if col in [3, 4] else normal_font)
                    cell.fill = bg
            row += 1

        row += 1

        # AI INSIGHTS
        row = _ws3_section(row, "AI INSIGHTS & OBSERVATIONS")
        insights = []
        if not used_tools:
            insights.append(("INFO", "No tools were used during this session.", "8B949E", "161B22"))
        else:
            top_tool = sorted_by_time[0]
            if timers[top_tool] > 0:
                insights.append(("TOP TOOL",
                    f"{TOOL_LABELS[top_tool]} was the most used instrument "
                    f"({timers[top_tool]//10}s, {picks[top_tool]} picks).",
                    "3FB950", "0D3320"))
            if unused_tools:
                names = ", ".join(TOOL_LABELS[t] for t in unused_tools[:5])
                extra = f" (+{len(unused_tools)-5} more)" if len(unused_tools) > 5 else ""
                insights.append(("UNUSED", f"Not used: {names}{extra}", "D29922", "3D2C00"))
            if high_freq_tools:
                names = ", ".join(TOOL_LABELS[t] for t in high_freq_tools)
                insights.append(("HIGH FREQ", f"Frequently swapped (3+ picks): {names}", "39D0D8", "0D2A2C"))
            if brief_use_tools:
                names = ", ".join(TOOL_LABELS[t] for t in brief_use_tools)
                insights.append(("BRIEF USE", f"Used very briefly (<5s): {names}", "D29922", "3D2C00"))
            eff = int(len(used_tools) / len(TOOLS) * 100)
            col_eff = ("3FB950","0D3320") if eff >= 70 else (("D29922","3D2C00") if eff >= 40 else ("8B949E","161B22"))
            insights.append(("EFFICIENCY",
                f"Instrument utilization: {eff}% ({len(used_tools)}/{len(TOOLS)} tools used).",
                col_eff[0], col_eff[1]))
            err_evts = [e for e in events if e['level'] == 'err']
            if err_evts:
                insights.append(("WARNING",
                    f"{len(err_evts)} error event(s) recorded. Review Event Log sheet.",
                    "F85149", "3D1210"))

        for lbl, text, fg, bg_hex in insights:
            ef    = Font(name="Calibri", bold=True, color=fg, size=10)
            efill = PatternFill("solid", fgColor=bg_hex)
            tf    = Font(name="Calibri", color="E6EDF3", size=10)
            c1 = ws3.cell(row=row, column=1, value=lbl)
            c1.font = ef; c1.fill = efill; c1.border = thin; c1.alignment = center
            ws3.merge_cells(f"B{row}:D{row}")
            c2 = ws3.cell(row=row, column=2, value=text)
            c2.font = tf; c2.fill = efill; c2.border = thin
            c2.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
            for col in [3, 4]:
                ws3.cell(row=row, column=col).border = thin
            ws3.row_dimensions[row].height = 20
            row += 1

        ws3.column_dimensions["A"].width = 18
        ws3.column_dimensions["B"].width = 55
        ws3.column_dimensions["C"].width = 14
        ws3.column_dimensions["D"].width = 14

        fname = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             f"surgical_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
        wb.save(fname)
        messagebox.showinfo("Export Complete", f"Saved:\n{fname}")
        os.startfile(fname)


# ── Entry point ────────────────────────────────────────────
if __name__ == '__main__':
    threading.Thread(target=_capture_loop, daemon=True).start()   # kamera okuma
    threading.Thread(target=_detect_loop,  daemon=True).start()   # YOLO işleme
    print("\n" + "="*52)
    print("  Smart Surgical Assistant — Tkinter GUI")
    print("="*52 + "\n")
    App().mainloop()