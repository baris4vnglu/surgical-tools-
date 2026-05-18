import os
import sys
import csv
import queue

os.environ['TCL_LIBRARY'] = r'C:\Users\baris\AppData\Local\Programs\Python\Python313\tcl\tcl8.6'
os.environ['TK_LIBRARY']  = r'C:\Users\baris\AppData\Local\Programs\Python\Python313\tcl\tk8.6'

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
import urllib.request
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk
from ultralytics import YOLO
import requests
import time
import threading
from datetime import datetime
from collections import deque

try:
    import pyttsx3
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False

try:
    from fpdf import FPDF
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False

# ── MediaPipe model ────────────────────────────────────────
HAND_MODEL_PATH = os.path.join(os.path.dirname(__file__), "hand_landmarker.task")
HAND_MODEL_URL  = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
if not os.path.exists(HAND_MODEL_PATH):
    print("Downloading MediaPipe hand model (~8 MB)...")
    urllib.request.urlretrieve(HAND_MODEL_URL, HAND_MODEL_PATH)
    print("Downloaded:", HAND_MODEL_PATH)

# ── Settings ───────────────────────────────────────────────
MODEL_PATH = r"C:\Users\baris\Downloads\best.pt"
API_KEY    = os.getenv("OPENROUTER_API_KEY",
             "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")

# Camera source — same logic as server.py
# USB webcam  → CAMERA_SOURCE=0
# DroidCam    → CAMERA_SOURCE=http://192.168.x.x:4747/video
# IP Webcam   → CAMERA_SOURCE=http://192.168.x.x:8080/video
# RTSP        → CAMERA_SOURCE=rtsp://user:pass@192.168.x.x:554/stream
_raw = os.getenv("CAMERA_SOURCE", "0")
CAMERA_SOURCE = int(_raw) if _raw.isdigit() else _raw

TOOLS = [
    "army_navy", "bulldog",   "castroviejo",
    "forceps",   "frazier",   "hemostat",   "iris",
    "mayo_metz", "needle",    "potts",      "richardson",
    "scalpel",   "towel_clip","weitlaner",  "yankauer",
    "makas",     "scissors",
]

ALERT_THRESHOLDS = {tool: 30 for tool in TOOLS}

# ── Color palette ──────────────────────────────────────────
BG_DARK     = "#0d1117"
BG_PANEL    = "#161b22"
BG_CARD     = "#1c2128"
ACCENT      = "#58a6ff"
GREEN       = "#3fb950"
RED         = "#f85149"
YELLOW      = "#d29922"
CYAN        = "#39d0d8"
TEXT_DIM    = "#8b949e"
TEXT_BRIGHT = "#e6edf3"
BORDER      = "#30363d"

STATUS_COLORS = {
    "on_table": (GREEN,  "ON TABLE"),
    "in_hand":  (RED,    "IN HAND"),
    "missing":  (YELLOW, "MISSING"),
}


class SurgicalAssistantApp:
    def __init__(self, window):
        self.window = window
        self.window.title("Smart Surgical Assistant  |  v3.0  |  Tkinter")
        self.window.configure(bg=BG_DARK)
        self.window.resizable(True, True)
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

        # YOLO
        self.model = YOLO(MODEL_PATH)

        # MediaPipe Hand Landmarker
        _base = mp_python.BaseOptions(model_asset_path=HAND_MODEL_PATH)
        _opts = mp_vision.HandLandmarkerOptions(
            base_options=_base,
            num_hands=4,
            min_hand_detection_confidence=0.4,
            min_hand_presence_confidence=0.4,
            min_tracking_confidence=0.4,
            running_mode=mp_vision.RunningMode.IMAGE,
        )
        self.hand_landmarker = mp_vision.HandLandmarker.create_from_options(_opts)

        # Tool tracking
        self.tool_timers      = {t: 0 for t in TOOLS}
        self.tool_states      = {t: "on_table" for t in TOOLS}
        self.held_history     = {t: deque(maxlen=7) for t in TOOLS}
        self.tool_alerted     = {t: False for t in TOOLS}
        self.tool_pick_count  = {t: 0 for t in TOOLS}
        self._prev_in_hand    = {t: False for t in TOOLS}

        # Surgery session
        self.surgery_active      = False
        self.surgery_start_time  = None
        self.pre_surgery_tools   = {}
        self.session_events      = []
        self.last_detected_tools = set()

        # Sensitivity threshold (same as server.py)
        self.hold_threshold = 0.20

        # AI
        self.last_api_call = time.time()

        # FPS
        self.frame_count = 0
        self.fps         = 0
        self._fps_t      = time.time()

        # TTS
        self._tts_queue = queue.Queue()
        if TTS_AVAILABLE:
            threading.Thread(target=self._tts_worker, daemon=True).start()

        self._apply_style()
        self._build_ui()
        self.setup_camera()

    # ── Styles ─────────────────────────────────────────────
    def _apply_style(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("Card.TFrame",  background=BG_CARD,  relief="flat")
        s.configure("Panel.TFrame", background=BG_PANEL, relief="flat")
        s.configure("Dark.TFrame",  background=BG_DARK,  relief="flat")
        s.configure("Timer.Horizontal.TProgressbar",
                    troughcolor=BG_DARK, background=ACCENT, thickness=6, bordercolor=BG_DARK)

    # ── Layout ─────────────────────────────────────────────
    def _build_ui(self):
        self.window.columnconfigure(0, weight=3)
        self.window.columnconfigure(1, weight=1)
        self.window.rowconfigure(1, weight=1)
        self._build_header()
        self._build_camera_panel()
        self._build_right_panel()
        self._build_statusbar()

    def _build_header(self):
        hdr = tk.Frame(self.window, bg=BG_DARK, pady=8)
        hdr.grid(row=0, column=0, columnspan=2, sticky="ew", padx=16)

        tk.Label(hdr, text="Smart Surgical Assistant",
                 bg=BG_DARK, fg=TEXT_BRIGHT, font=("Segoe UI", 17, "bold")).pack(side="left")
        tk.Label(hdr, text="v3.0",
                 bg=BG_DARK, fg=ACCENT, font=("Segoe UI", 10)).pack(side="left", padx=(8,0), pady=4)

        self.clock_var = tk.StringVar()
        tk.Label(hdr, textvariable=self.clock_var,
                 bg=BG_DARK, fg=TEXT_DIM, font=("Consolas", 10)).pack(side="right")
        self._tick_clock()

        tk.Frame(self.window, bg=BORDER, height=1).grid(row=0, column=0, columnspan=2, sticky="sew")

    def _tick_clock(self):
        self.clock_var.set(datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))
        self.window.after(1000, self._tick_clock)

    def _build_camera_panel(self):
        outer = tk.Frame(self.window, bg=BG_DARK)
        outer.grid(row=1, column=0, sticky="nsew", padx=(16,8), pady=12)
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)

        cam_card = tk.Frame(outer, bg=BG_CARD, bd=0,
                            highlightbackground=BORDER, highlightthickness=1)
        cam_card.grid(row=0, column=0, sticky="nsew")
        cam_card.rowconfigure(1, weight=1)
        cam_card.columnconfigure(0, weight=1)

        title_bar = tk.Frame(cam_card, bg=BG_PANEL, pady=5, padx=10)
        title_bar.grid(row=0, column=0, sticky="ew")
        tk.Label(title_bar, text="  Live Camera Feed",
                 bg=BG_PANEL, fg=TEXT_BRIGHT, font=("Segoe UI", 10, "bold")).pack(side="left")
        self.fps_label = tk.Label(title_bar, text="FPS: --",
                                  bg=BG_PANEL, fg=CYAN, font=("Consolas", 9))
        self.fps_label.pack(side="right")
        tk.Label(title_bar, text=f"Source: {CAMERA_SOURCE}",
                 bg=BG_PANEL, fg=TEXT_DIM, font=("Consolas", 8)).pack(side="right", padx=(0,12))

        self.cam_label = tk.Label(cam_card, bg="black")
        self.cam_label.grid(row=1, column=0, padx=2, pady=2, sticky="nsew")

        # Log area
        log_card = tk.Frame(outer, bg=BG_CARD,
                            highlightbackground=BORDER, highlightthickness=1)
        log_card.grid(row=2, column=0, sticky="ew", pady=(8,0))
        log_card.columnconfigure(0, weight=1)

        log_title = tk.Frame(log_card, bg=BG_PANEL, pady=5, padx=10)
        log_title.grid(row=0, column=0, columnspan=2, sticky="ew")
        tk.Label(log_title, text="  Event Log",
                 bg=BG_PANEL, fg=TEXT_BRIGHT, font=("Segoe UI", 10, "bold")).pack(side="left")
        tk.Button(log_title, text="Clear", bg=BG_PANEL, fg=TEXT_DIM, relief="flat", cursor="hand2",
                  font=("Segoe UI", 8),
                  command=lambda: self.log_text.delete("1.0", tk.END)).pack(side="right")

        self.log_text = tk.Text(log_card, height=7, bg=BG_DARK, fg=GREEN,
                                font=("Consolas", 9), bd=0, padx=8, pady=4,
                                insertbackground=GREEN, selectbackground=ACCENT)
        self.log_text.grid(row=1, column=0, sticky="ew", padx=2, pady=2)
        for tag, fg in [("warn", YELLOW), ("ai", CYAN), ("error", RED), ("ts", TEXT_DIM), ("ok", GREEN)]:
            self.log_text.tag_config(tag, foreground=fg)

        scr = ttk.Scrollbar(log_card, command=self.log_text.yview)
        scr.grid(row=1, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scr.set)

        self._log("System started. Waiting for camera...", "ok")

    def _log(self, msg, tag=""):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{ts}] ", "ts")
        self.log_text.insert(tk.END, msg + "\n", tag if tag else None)
        self.log_text.see(tk.END)
        self.session_events.append((datetime.now(), tag or "info", msg))

    # ── Right panel ────────────────────────────────────────
    def _build_right_panel(self):
        right = tk.Frame(self.window, bg=BG_DARK)
        right.grid(row=1, column=1, sticky="nsew", padx=(0,16), pady=12)
        right.columnconfigure(0, weight=1)

        self._build_timer_card(right,     row=0)
        self._build_status_card(right,    row=1)
        self._build_threshold_card(right, row=2)
        self._build_surgery_card(right,   row=3)
        self._build_ai_card(right,        row=4)

    def _scrollable_card(self, parent, row, title, height, pady_top=0):
        card = tk.Frame(parent, bg=BG_CARD,
                        highlightbackground=BORDER, highlightthickness=1)
        card.grid(row=row, column=0, sticky="ew", pady=(pady_top, 0))
        card.columnconfigure(0, weight=1)

        t_title = tk.Frame(card, bg=BG_PANEL, pady=5, padx=10)
        t_title.grid(row=0, column=0, columnspan=2, sticky="ew")
        tk.Label(t_title, text=f"  {title}",
                 bg=BG_PANEL, fg=TEXT_BRIGHT, font=("Segoe UI", 10, "bold")).pack(side="left")

        canvas = tk.Canvas(card, bg=BG_CARD, highlightthickness=0, height=height)
        canvas.grid(row=1, column=0, sticky="ew")
        scr = ttk.Scrollbar(card, orient="vertical", command=canvas.yview)
        scr.grid(row=1, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scr.set)

        inner = tk.Frame(canvas, bg=BG_CARD)
        win_id = canvas.create_window((0,0), window=inner, anchor="nw")

        canvas.bind("<Configure>",   lambda e: canvas.itemconfig(win_id, width=e.width))
        inner.bind("<Configure>",    lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<MouseWheel>",  lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))
        inner.bind("<MouseWheel>",   lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        return card, inner

    def _build_timer_card(self, parent, row):
        _, inner = self._scrollable_card(parent, row, "Usage Time", height=180)
        inner.columnconfigure(0, weight=1)
        self.timer_labels = {}
        self.timer_bars   = {}
        self.timer_max    = {t: 1 for t in TOOLS}
        self.pick_labels  = {}

        for i, tool in enumerate(TOOLS):
            rf = tk.Frame(inner, bg=BG_CARD, padx=10, pady=3)
            rf.grid(row=i, column=0, sticky="ew")
            rf.columnconfigure(1, weight=1)

            tk.Label(rf, text="●", bg=BG_CARD, fg=ACCENT,
                     font=("Segoe UI", 7)).grid(row=0, column=0, padx=(0,5))
            tk.Label(rf, text=tool.replace("_"," ").title(),
                     bg=BG_CARD, fg=TEXT_BRIGHT,
                     font=("Segoe UI", 9, "bold"), anchor="w").grid(row=0, column=1, sticky="w")

            tl = tk.Label(rf, text="0s", bg=BG_CARD, fg=CYAN, font=("Consolas", 8), anchor="e")
            tl.grid(row=0, column=2, sticky="e")
            self.timer_labels[tool] = tl

            pl = tk.Label(rf, text="x0", bg=BG_CARD, fg=TEXT_DIM, font=("Consolas", 8), anchor="e")
            pl.grid(row=0, column=3, sticky="e", padx=(4,0))
            self.pick_labels[tool] = pl

            bar = ttk.Progressbar(rf, style="Timer.Horizontal.TProgressbar",
                                  orient="horizontal", length=100, maximum=100)
            bar.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(1,0))
            self.timer_bars[tool] = bar

    def _build_status_card(self, parent, row):
        _, inner = self._scrollable_card(parent, row, "Tool Status", height=160, pady_top=10)
        inner.columnconfigure(0, weight=1)
        self.status_canvases = {}
        self.status_labels   = {}

        for i, tool in enumerate(TOOLS):
            rf = tk.Frame(inner, bg=BG_CARD, padx=10, pady=4)
            rf.grid(row=i, column=0, sticky="ew")
            rf.columnconfigure(1, weight=1)

            cvs = tk.Canvas(rf, width=12, height=12, bg=BG_CARD, highlightthickness=0)
            cvs.grid(row=0, column=0, padx=(0,7))
            circle = cvs.create_oval(1, 1, 11, 11, fill=GREEN, outline="")
            self.status_canvases[tool] = (cvs, circle)

            tk.Label(rf, text=tool.replace("_"," ").title(),
                     bg=BG_CARD, fg=TEXT_BRIGHT,
                     font=("Segoe UI", 9), anchor="w").grid(row=0, column=1, sticky="w")

            badge = tk.Label(rf, text="ON TABLE", bg=BG_DARK, fg=GREEN,
                             font=("Segoe UI", 7, "bold"), padx=5, pady=1)
            badge.grid(row=0, column=2)
            self.status_labels[tool] = badge

    def _build_threshold_card(self, parent, row):
        card = tk.Frame(parent, bg=BG_CARD,
                        highlightbackground=BORDER, highlightthickness=1)
        card.grid(row=row, column=0, sticky="ew", pady=(10,0))
        card.columnconfigure(0, weight=1)

        title = tk.Frame(card, bg=BG_PANEL, pady=5, padx=10)
        title.grid(row=0, column=0, sticky="ew")
        tk.Label(title, text="  Detection Sensitivity",
                 bg=BG_PANEL, fg=TEXT_BRIGHT, font=("Segoe UI", 10, "bold")).pack(side="left")
        self.thresh_var = tk.StringVar(value="0.20")
        tk.Label(title, textvariable=self.thresh_var,
                 bg=BG_PANEL, fg=CYAN, font=("Consolas", 9)).pack(side="right")

        inner = tk.Frame(card, bg=BG_CARD, padx=10, pady=8)
        inner.grid(row=1, column=0, sticky="ew")
        inner.columnconfigure(0, weight=1)

        row_lbl = tk.Frame(inner, bg=BG_CARD)
        row_lbl.grid(row=0, column=0, sticky="ew")
        tk.Label(row_lbl, text="Loose", bg=BG_CARD, fg=TEXT_DIM, font=("Segoe UI", 7)).pack(side="left")
        tk.Label(row_lbl, text="Strict", bg=BG_CARD, fg=TEXT_DIM, font=("Segoe UI", 7)).pack(side="right")

        self.thresh_scale = ttk.Scale(inner, from_=5, to=80, orient="horizontal",
                                      command=self._on_threshold_change)
        self.thresh_scale.set(20)
        self.thresh_scale.grid(row=1, column=0, sticky="ew", pady=(2,6))

        preset_frame = tk.Frame(inner, bg=BG_CARD)
        preset_frame.grid(row=2, column=0, sticky="ew")
        for label, val in [("High\n0.08", 8), ("Normal\n0.20", 20), ("Strict\n0.40", 40)]:
            tk.Button(preset_frame, text=label, bg=BG_DARK, fg=TEXT_DIM, relief="flat",
                      font=("Segoe UI", 7), cursor="hand2",
                      command=lambda v=val: self._apply_preset(v)
                      ).pack(side="left", expand=True, fill="x", padx=2)

    def _on_threshold_change(self, val):
        self.hold_threshold = round(float(val) / 100, 2)
        self.thresh_var.set(f"{self.hold_threshold:.2f}")

    def _apply_preset(self, val):
        self.thresh_scale.set(val)
        self._on_threshold_change(val)

    def _build_surgery_card(self, parent, row):
        card = tk.Frame(parent, bg=BG_CARD,
                        highlightbackground=BORDER, highlightthickness=1)
        card.grid(row=row, column=0, sticky="ew", pady=(10,0))
        card.columnconfigure(0, weight=1)

        title = tk.Frame(card, bg=BG_PANEL, pady=5, padx=10)
        title.grid(row=0, column=0, sticky="ew")
        tk.Label(title, text="  Surgery Control",
                 bg=BG_PANEL, fg=TEXT_BRIGHT, font=("Segoe UI", 10, "bold")).pack(side="left")
        self.surgery_time_var = tk.StringVar(value="--:--:--")
        tk.Label(title, textvariable=self.surgery_time_var,
                 bg=BG_PANEL, fg=CYAN, font=("Consolas", 9)).pack(side="right")

        btn_row = tk.Frame(card, bg=BG_CARD, padx=10, pady=8)
        btn_row.grid(row=1, column=0, sticky="ew")
        btn_row.columnconfigure(0, weight=1)
        btn_row.columnconfigure(1, weight=1)

        self.btn_start = tk.Button(btn_row, text="Start Surgery",
                                   bg=GREEN, fg="black",
                                   font=("Segoe UI", 9, "bold"),
                                   relief="flat", cursor="hand2",
                                   command=self.start_surgery)
        self.btn_start.grid(row=0, column=0, sticky="ew", padx=(0,4))

        self.btn_end = tk.Button(btn_row, text="End Surgery",
                                 bg=BG_DARK, fg=TEXT_DIM,
                                 font=("Segoe UI", 9, "bold"),
                                 relief="flat", cursor="hand2",
                                 state="disabled",
                                 command=self.end_surgery)
        self.btn_end.grid(row=0, column=1, sticky="ew", padx=(4,0))

        self.count_labels = {}
        cf = tk.Frame(card, bg=BG_CARD, padx=10, pady=4)
        cf.grid(row=2, column=0, sticky="ew")
        cf.columnconfigure(0, weight=1)
        for i, tool in enumerate(TOOLS):
            rf = tk.Frame(cf, bg=BG_CARD)
            rf.grid(row=i, column=0, sticky="ew")
            rf.columnconfigure(0, weight=1)
            tk.Label(rf, text=tool.replace("_"," ").title(),
                     bg=BG_CARD, fg=TEXT_DIM,
                     font=("Segoe UI", 8), anchor="w").grid(row=0, column=0, sticky="w")
            lbl = tk.Label(rf, text="—", bg=BG_CARD, fg=TEXT_DIM,
                           font=("Consolas", 8), anchor="e")
            lbl.grid(row=0, column=1, sticky="e")
            self.count_labels[tool] = lbl

        tk.Button(card, text="  Export Report (CSV + PDF + Excel)",
                  bg=BG_PANEL, fg=ACCENT,
                  font=("Segoe UI", 9), relief="flat", cursor="hand2",
                  command=self.export_report
                  ).grid(row=3, column=0, sticky="ew", padx=10, pady=(4,8))

    def _build_ai_card(self, parent, row):
        card = tk.Frame(parent, bg=BG_CARD,
                        highlightbackground=BORDER, highlightthickness=1)
        card.grid(row=row, column=0, sticky="ew", pady=(10,0))
        card.columnconfigure(0, weight=1)

        ai_title = tk.Frame(card, bg=BG_PANEL, pady=5, padx=10)
        ai_title.grid(row=0, column=0, sticky="ew")
        tk.Label(ai_title, text="  AI Report",
                 bg=BG_PANEL, fg=TEXT_BRIGHT, font=("Segoe UI", 10, "bold")).pack(side="left")
        self.ai_dot = tk.Label(ai_title, text="●", bg=BG_PANEL, fg=TEXT_DIM, font=("Segoe UI", 9))
        self.ai_dot.pack(side="right")

        self.ai_next_label = tk.Label(card, text="Next report in 15s",
                                      bg=BG_CARD, fg=TEXT_DIM, font=("Segoe UI", 9), pady=6)
        self.ai_next_label.grid(row=1, column=0, sticky="ew", padx=10)

        self.ai_bar = ttk.Progressbar(card, style="Timer.Horizontal.TProgressbar",
                                      orient="horizontal", length=160, maximum=15)
        self.ai_bar.grid(row=2, column=0, sticky="ew", padx=10, pady=(0,8))

    def _build_statusbar(self):
        bar = tk.Frame(self.window, bg=BG_PANEL, pady=3)
        bar.grid(row=2, column=0, columnspan=2, sticky="ew")
        tk.Frame(self.window, bg=BORDER, height=1).grid(row=2, column=0, columnspan=2, sticky="new")
        self.sb_var = tk.StringVar(value="Ready")
        tk.Label(bar, textvariable=self.sb_var,
                 bg=BG_PANEL, fg=TEXT_DIM, font=("Segoe UI", 8), padx=16).pack(side="left")
        tk.Label(bar, text="Smart Surgical Assistant  •  YOLO + MediaPipe + DeepSeek",
                 bg=BG_PANEL, fg=TEXT_DIM, font=("Segoe UI", 8)).pack(side="right", padx=16)

    # ── Camera ─────────────────────────────────────────────
    def setup_camera(self):
        is_ipcam = isinstance(CAMERA_SOURCE, str)
        self.cap  = cv2.VideoCapture(CAMERA_SOURCE)
        if not is_ipcam:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.cap.set(cv2.CAP_PROP_FPS, 60)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.update_loop()

    # ── TTS ────────────────────────────────────────────────
    def _tts_worker(self):
        engine = pyttsx3.init()
        engine.setProperty("rate", 160)
        while True:
            text = self._tts_queue.get()
            if text is None: break
            try:
                engine.say(text)
                engine.runAndWait()
            except Exception:
                pass

    def _speak(self, text):
        if TTS_AVAILABLE:
            self._tts_queue.put(text)

    # ── Surgery control ────────────────────────────────────
    def start_surgery(self):
        self.surgery_active     = True
        self.surgery_start_time = datetime.now()
        self.pre_surgery_tools  = {t: (t in self.last_detected_tools) for t in TOOLS}
        self.tool_alerted       = {t: False for t in TOOLS}

        self.btn_start.config(state="disabled", bg=BG_DARK, fg=TEXT_DIM)
        self.btn_end.config(state="normal", bg=RED, fg="white")

        for tool, present in self.pre_surgery_tools.items():
            self.count_labels[tool].config(
                text="PRESENT" if present else "MISSING",
                fg=GREEN if present else YELLOW)

        self._log("=== SURGERY STARTED ===", "ok")
        self._speak("Surgery started. Tool tracking is now active.")
        self._tick_surgery_clock()

    def _tick_surgery_clock(self):
        if not self.surgery_active: return
        elapsed = datetime.now() - self.surgery_start_time
        h, rem  = divmod(int(elapsed.total_seconds()), 3600)
        m, s    = divmod(rem, 60)
        self.surgery_time_var.set(f"{h:02d}:{m:02d}:{s:02d}")
        self.window.after(1000, self._tick_surgery_clock)

    def end_surgery(self):
        self.surgery_active = False
        self.btn_start.config(state="normal", bg=GREEN, fg="black")
        self.btn_end.config(state="disabled", bg=BG_DARK, fg=TEXT_DIM)

        post = {t: (t in self.last_detected_tools) for t in TOOLS}
        missing = [t for t in TOOLS if self.pre_surgery_tools.get(t) and not post[t]]

        self._log("=== SURGERY ENDED ===", "ok")
        if missing:
            msg = f"WARNING! Missing tools: {', '.join(missing)}"
            self._log(msg, "error")
            self._speak(f"Warning! Missing tools detected: {', '.join(missing)}")
            messagebox.showwarning("Missing Tools!", msg)
        else:
            self._log("All tools verified. None missing.", "ok")
            self._speak("All tools verified. None missing.")

        for tool in TOOLS:
            self.count_labels[tool].config(
                text="PRESENT" if post[tool] else "MISSING",
                fg=GREEN if post[tool] else RED)

    # ── Export ─────────────────────────────────────────────
    def export_report(self):
        save_dir = filedialog.askdirectory(title="Select folder to save report:")
        if not save_dir: return

        ts_str    = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path  = os.path.join(save_dir, f"surgical_report_{ts_str}.csv")
        pdf_path  = os.path.join(save_dir, f"surgical_report_{ts_str}.pdf")
        xlsx_path = os.path.join(save_dir, f"surgical_report_{ts_str}.xlsx")

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Time", "Level", "Event"])
            for ts, level, msg in self.session_events:
                writer.writerow([ts.strftime("%H:%M:%S"), level, msg])
        self._log(f"CSV saved: {csv_path}", "ok")

        if PDF_AVAILABLE:
            self._export_pdf(pdf_path, ts_str)
            self._log(f"PDF saved: {pdf_path}", "ok")
        else:
            self._log("fpdf2 not installed — PDF skipped.", "warn")

        if EXCEL_AVAILABLE:
            self._export_excel(xlsx_path, ts_str)
            self._log(f"Excel saved: {xlsx_path}", "ok")
        else:
            self._log("openpyxl not installed — Excel skipped.", "warn")

    def _export_pdf(self, path, ts_str):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 10, "Smart Surgical Assistant - Session Report", ln=True)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, f"Generated: {ts_str}", ln=True)
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Tool Usage Summary", ln=True)
        pdf.set_font("Helvetica", "", 10)
        for tool in TOOLS:
            sec   = self.tool_timers[tool] // 10
            picks = self.tool_pick_count[tool]
            pdf.cell(0, 6, f"  {tool.replace('_',' ').title()}: {sec}s in use, picked up {picks}x", ln=True)
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Event Log", ln=True)
        pdf.set_font("Helvetica", "", 9)
        for ts, level, msg in self.session_events:
            safe = msg.encode("ascii", "replace").decode("ascii")
            pdf.multi_cell(0, 5, f"[{ts.strftime('%H:%M:%S')}] [{level.upper():5s}] {safe}")
        pdf.output(path)

    def _export_excel(self, path, ts_str):
        wb  = openpyxl.Workbook()
        ws1 = wb.active
        ws1.title = "Tool Summary"

        hdr_fill    = PatternFill("solid", fgColor="1C2128")
        title_font  = Font(name="Calibri", bold=True, color="E6EDF3", size=14)
        hdr_font    = Font(name="Calibri", bold=True, color="58A6FF", size=11)
        normal_font = Font(name="Calibri", color="E6EDF3", size=10)
        dim_font    = Font(name="Calibri", color="8B949E", size=9)
        green_font  = Font(name="Calibri", bold=True, color="3FB950", size=10)
        red_font    = Font(name="Calibri", bold=True, color="F85149", size=10)
        yellow_font = Font(name="Calibri", bold=True, color="D29922", size=10)
        thin = Border(
            left=Side(style="thin", color="30363D"), right=Side(style="thin", color="30363D"),
            top=Side(style="thin", color="30363D"),  bottom=Side(style="thin", color="30363D"))

        ws1.merge_cells("A1:F1")
        ws1["A1"] = "Smart Surgical Assistant — Session Report"
        ws1["A1"].font = title_font
        ws1["A1"].fill = PatternFill("solid", fgColor="161B22")
        ws1["A1"].alignment = Alignment(horizontal="center", vertical="center")
        ws1.row_dimensions[1].height = 28

        ws1.merge_cells("A2:F2")
        ws1["A2"] = f"Generated: {ts_str}"
        ws1["A2"].font = dim_font
        ws1["A2"].fill = PatternFill("solid", fgColor="161B22")

        for col, h in enumerate(["Tool Name", "Use Time (s)", "Pick Count", "Status", "Notes"], 1):
            cell = ws1.cell(row=4, column=col, value=h)
            cell.font = hdr_font; cell.fill = hdr_fill; cell.border = thin
            cell.alignment = Alignment(horizontal="center", vertical="center")

        smap = {
            "on_table": ("ON TABLE", green_font,  PatternFill("solid", fgColor="0D3320")),
            "in_hand":  ("IN HAND",  red_font,    PatternFill("solid", fgColor="3D1210")),
            "missing":  ("MISSING",  yellow_font, PatternFill("solid", fgColor="3D2C00")),
        }
        for i, tool in enumerate(TOOLS):
            r   = i + 5
            sec = self.tool_timers[tool] // 10
            bg  = PatternFill("solid", fgColor="0D1117" if i%2==0 else "161B22")
            stxt, sfont, sfill = smap.get(self.tool_states[tool], smap["on_table"])
            for col, val in enumerate(
                    [tool.replace("_"," ").title(), sec, self.tool_pick_count[tool], stxt, ""], 1):
                cell = ws1.cell(row=r, column=col, value=val)
                cell.border = thin
                cell.alignment = Alignment(horizontal="left" if col==1 else "center", vertical="center")
                if col == 4: cell.font = sfont; cell.fill = sfill
                else:        cell.font = normal_font; cell.fill = bg

        for col, w in enumerate([22, 14, 12, 14, 20], 1):
            ws1.column_dimensions[get_column_letter(col)].width = w

        ws2 = wb.create_sheet("Event Log")
        ws2.merge_cells("A1:C1")
        ws2["A1"] = "Event Log"
        ws2["A1"].font = title_font
        ws2["A1"].fill = PatternFill("solid", fgColor="161B22")
        ws2["A1"].alignment = Alignment(horizontal="center", vertical="center")
        for col, h in enumerate(["Timestamp", "Level", "Message"], 1):
            cell = ws2.cell(row=2, column=col, value=h)
            cell.font = hdr_font; cell.fill = hdr_fill; cell.border = thin

        lvl_colors = {
            "ok":    ("3FB950","0D3320"), "warn":  ("D29922","3D2C00"),
            "error": ("F85149","3D1210"), "ai":    ("39D0D8","0D2A2C"),
            "info":  ("8B949E","161B22"), "":      ("8B949E","161B22"),
        }
        for i, (ts, level, msg) in enumerate(self.session_events):
            r = i + 3
            fg, bg = lvl_colors.get(level, ("8B949E","161B22"))
            efont = Font(name="Calibri", color=fg, size=9)
            efill = PatternFill("solid", fgColor=bg)
            for col, val in enumerate([ts.strftime("%H:%M:%S"), level.upper(), msg], 1):
                cell = ws2.cell(row=r, column=col, value=val)
                cell.font = efont; cell.fill = efill; cell.border = thin
                cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=(col==3))
        ws2.column_dimensions["A"].width = 14
        ws2.column_dimensions["B"].width = 10
        ws2.column_dimensions["C"].width = 70
        wb.save(path)

    # ── Hand-tool overlap score (identical to server.py) ───
    def _score(self, bh, bt):
        hx1,hy1,hx2,hy2 = bh;  tx1,ty1,tx2,ty2 = bt
        ix1=max(hx1,tx1); iy1=max(hy1,ty1); ix2=min(hx2,tx2); iy2=min(hy2,ty2)
        inter = max(0,ix2-ix1)*max(0,iy2-iy1)
        ta    = max((tx2-tx1)*(ty2-ty1), 1)
        ha    = max((hx2-hx1)*(hy2-hy1), 1)
        union = ta + ha - inter
        cont  = inter / ta
        tc_x  = (tx1+tx2)/2;  tc_y = (ty1+ty2)/2
        cin   = float(hx1<=tc_x<=hx2 and hy1<=tc_y<=hy2)
        iou   = inter/union if union else 0
        hc_x  = (hx1+hx2)/2;  hc_y = (hy1+hy2)/2
        hd    = max(((hx2-hx1)**2+(hy2-hy1)**2)**.5, 1)
        prox  = max(0, 1-((tc_x-hc_x)**2+(tc_y-hc_y)**2)**.5/(hd*1.5))
        return 0.40*cont + 0.30*cin + 0.20*iou + 0.10*prox

    # ── LLM (DeepSeek via OpenRouter) ─────────────────────
    def call_llm(self, report_data):
        self.ai_dot.config(fg=YELLOW)
        try:
            headers = {
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://surgical-assistant.local",
                "X-Title": "Smart Surgical Assistant",
            }
            payload = {
                "model": "deepseek/deepseek-r1",
                "messages": [
                    {"role": "system", "content":
                        "You are an expert surgical assistant. Interpret the data professionally and concisely."},
                    {"role": "user", "content": report_data}
                ],
                "max_tokens": 300,
            }
            res = requests.post("https://openrouter.ai/api/v1/chat/completions",
                                json=payload, headers=headers, timeout=120)
            if res.status_code != 200:
                self._log(f"[API ERROR] HTTP {res.status_code}", "error")
                self.ai_dot.config(fg=RED); return
            data = res.json()
            if 'error' in data:
                self._log(f"[API ERROR] {data['error'].get('message','')}", "error")
                self.ai_dot.config(fg=RED); return
            choice  = data['choices'][0]['message']
            content = choice.get('content') or choice.get('reasoning_content','')
            if not content:
                self._log("[API ERROR] Empty response", "error")
                self.ai_dot.config(fg=RED); return
            self._log(f"[AI] {content.strip()}", "ai")
            self.ai_dot.config(fg=GREEN)
        except requests.exceptions.Timeout:
            self._log("[API ERROR] Timeout", "error"); self.ai_dot.config(fg=RED)
        except Exception as e:
            self._log(f"[API ERROR] {type(e).__name__}: {e}", "error"); self.ai_dot.config(fg=RED)

    # ── Main loop ──────────────────────────────────────────
    def update_loop(self):
        ret, frame = self.cap.read()
        if not ret:
            self.window.after(10, self.update_loop)
            return

        # FPS
        self.frame_count += 1
        now = time.time()
        if now - self._fps_t >= 1.0:
            self.fps         = self.frame_count
            self.frame_count = 0
            self._fps_t      = now
            self.fps_label.config(text=f"FPS: {self.fps}")

        h_frame, w_frame = frame.shape[:2]

        # 1. MediaPipe hand detection
        rgb      = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        hand_res = self.hand_landmarker.detect(mp_image)
        detected_hands = []

        if hand_res.hand_landmarks:
            for hand_lms in hand_res.hand_landmarks:
                xs  = [lm.x * w_frame for lm in hand_lms]
                ys  = [lm.y * h_frame  for lm in hand_lms]
                pad = 25
                hx1 = max(0,       int(min(xs)) - pad)
                hy1 = max(0,       int(min(ys)) - pad)
                hx2 = min(w_frame, int(max(xs)) + pad)
                hy2 = min(h_frame, int(max(ys)) + pad)
                detected_hands.append([hx1, hy1, hx2, hy2])
                cv2.rectangle(frame, (hx1,hy1),(hx2,hy2),(255,200,50), 2)
                cv2.putText(frame, "hand", (hx1,hy1-6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,200,50), 1)
        else:
            cv2.putText(frame, "No hand detected", (10,30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,80,255), 2)

        # 2. YOLO tool detection (imgsz=416 for speed)
        yolo_res            = self.model(frame, conf=0.35, verbose=False, imgsz=416)[0]
        detected_tools      = {}
        detected_tools_conf = {}

        for box in yolo_res.boxes:
            c     = box.xyxy[0].tolist()
            label = self.model.names[int(box.cls[0])].lower()
            conf  = float(box.conf[0])

            if label in TOOLS:
                if label not in detected_tools_conf or conf > detected_tools_conf[label]:
                    detected_tools[label]      = c
                    detected_tools_conf[label] = conf
                color = (88, 166, 255)
            else:
                color = (120, 120, 120)

            x1,y1,x2,y2 = int(c[0]),int(c[1]),int(c[2]),int(c[3])
            cv2.rectangle(frame, (x1,y1),(x2,y2), color, 2)
            cv2.putText(frame, f"{label} {conf:.2f}", (x1,y1-6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.50, (230,237,243), 1)

        self.last_detected_tools = set(detected_tools.keys())

        # 3. State & UI update
        for tool in TOOLS:
            in_view  = tool in detected_tools
            raw_held = False

            if in_view and detected_hands:
                best_score = max(self._score(h, detected_tools[tool]) for h in detected_hands)
                raw_held   = best_score >= self.hold_threshold
                tx1,ty1,tx2,ty2 = [int(v) for v in detected_tools[tool]]
                cv2.putText(frame, f"hold:{best_score:.2f}", (tx1, ty2+16),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                            (50,255,120) if raw_held else (180,180,180), 1)

            self.held_history[tool].append(raw_held)
            is_held      = sum(self.held_history[tool]) > len(self.held_history[tool]) / 2
            prev_in_hand = self._prev_in_hand[tool]

            if in_view:
                if is_held:
                    self.tool_timers[tool] += 1
                    self.tool_states[tool]  = "in_hand"
                    if not prev_in_hand:
                        self.tool_pick_count[tool] += 1
                        self._log(f"{tool.replace('_',' ').title()} picked up "
                                  f"(#{self.tool_pick_count[tool]})", "ok")
                        self._speak(f"{tool.replace('_',' ')} picked up")
                else:
                    if prev_in_hand:
                        self._log(f"{tool.replace('_',' ').title()} released.", "")
                    self.tool_states[tool] = "on_table"
            else:
                if self.tool_states[tool] == "in_hand":
                    self.tool_states[tool] = "missing"
                    self._log(f"[WARNING] {tool} left the hand and is not visible!", "warn")
                    self._speak(f"Warning! {tool.replace('_',' ')} is missing!")

            self._prev_in_hand[tool] = is_held

            # Duration alert
            if self.surgery_active and is_held:
                sec = self.tool_timers[tool] // 10
                if sec >= ALERT_THRESHOLDS[tool] and not self.tool_alerted[tool]:
                    self.tool_alerted[tool] = True
                    msg = f"{tool.replace('_',' ').title()} held for {ALERT_THRESHOLDS[tool]}s!"
                    self._log(f"[TIME ALERT] {msg}", "warn")
                    self._speak(f"Warning! {tool.replace('_',' ')} has been held for {ALERT_THRESHOLDS[tool]} seconds.")

            color_hex, badge_text = STATUS_COLORS[self.tool_states[tool]]
            cvs, circle = self.status_canvases[tool]
            cvs.itemconfig(circle, fill=color_hex)
            self.status_labels[tool].config(text=badge_text, fg=color_hex)

            sec = self.tool_timers[tool] // 10
            self.timer_labels[tool].config(text=f"{sec}s")
            self.pick_labels[tool].config(text=f"x{self.tool_pick_count[tool]}")
            if sec > self.timer_max[tool]: self.timer_max[tool] = sec
            self.timer_bars[tool]["value"] = min(100, int(sec * 100 / max(self.timer_max[tool], 1)))

        # AI countdown
        elapsed   = time.time() - self.last_api_call
        remaining = max(0, 15 - elapsed)
        self.ai_bar["value"] = elapsed
        self.ai_next_label.config(text=f"Next report in {int(remaining)}s")

        if elapsed > 15:
            summary = (f"Surgery active: {self.surgery_active}. "
                       f"Timers(frames): {self.tool_timers}. "
                       f"States: {self.tool_states}. "
                       f"Pick counts: {self.tool_pick_count}.")
            threading.Thread(target=self.call_llm, args=(summary,), daemon=True).start()
            self.last_api_call = time.time()

        # Render to Tkinter
        img   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img   = Image.fromarray(img).resize((640, 480), Image.LANCZOS)
        imgtk = ImageTk.PhotoImage(img)
        self.cam_label.configure(image=imgtk)
        self.cam_label.image = imgtk

        self.window.after(10, self.update_loop)

    # ── Cleanup ────────────────────────────────────────────
    def _on_close(self):
        self._tts_queue.put(None)
        self.cap.release()
        self.window.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    root.minsize(1050, 680)
    app = SurgicalAssistantApp(root)
    root.mainloop()
