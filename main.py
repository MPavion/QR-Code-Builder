#!/usr/bin/env python3
"""QR Code Builder – GUI app that saves QR codes as PNG and SVG."""
import io
import json
import os
import re
import ssl
import subprocess
import threading
import tkinter as tk
import urllib.error
import urllib.request
from datetime import datetime
from tkinter import colorchooser, filedialog, messagebox
from urllib.parse import urlparse

import customtkinter as ctk
import segno
from PIL import Image, ImageDraw, ImageTk

# ── Constants ──────────────────────────────────────────────────────────────────

APP_NAME      = "QR Code Builder"
APP_VERSION   = "1.0"
APP_AUTHOR    = "Martin Pavion"
SETTINGS_DIR  = os.path.join(os.path.expanduser("~"), ".qrbuilder")
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")
DOWNLOADS     = os.path.join(os.path.expanduser("~"), "Downloads")
ASSETS_DIR    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

EC_DESCRIPTIONS = {
    "L": "Low — 7% of data recoverable. Smallest code, minimal damage tolerance.",
    "M": "Medium — 15% recoverable. Default; good for most uses.",
    "Q": "Quartile — 25% recoverable. Good for printed or worn surfaces.",
    "H": "High — 30% recoverable. Use this when embedding a logo.",
}

TIPS = {
    "url":         "Enter any URL to encode.\nhttps:// is added automatically if omitted.",
    "size":        "Width and height of the exported PNG in pixels.\nThe SVG is always infinitely scalable — no size limit.",
    "folder":      "Where PNG and SVG files are saved.\nDefault: your Downloads folder.",
    "filename":    "Template for the output filename.\n{domain} → website domain (e.g. github-com)\n{date} → YYYYMMDD_HHMMSS timestamp",
    "fg_color":    "Colour of the dark QR modules.\nMust contrast strongly with the background for reliable scanning.",
    "bg_color":    "Background colour of the QR code.\nKeep contrast with foreground high (4:1 ratio or better).",
    "transparent": "Makes the background transparent.\nSaved as PNG with alpha channel and SVG with no background fill.\nUseful for placing the code on a coloured background in design tools.",
    "shape":       "Shape of each dark module.\n• Square — standard; maximum scanner compatibility.\n• Rounded — softer look; still reliable.\n• Circle — decorative; use with Q or H error correction.\nNote: SVG always uses square modules.",
    "ec":          "How much of the code can be damaged and still scan.\nHigher levels add redundancy — the code is slightly larger.\nL=7%  M=15%  Q=25%  H=30%",
    "quiet_zone":  "The blank border around the QR code.\nScanners need clear space to find where the code begins.\nThe QR standard requires 4 modules; below 2 risks scan failures.",
    "logo":        "Embed a logo or icon in the centre of the QR code.\nAlways use H (High) error correction with a logo so the\ncode can still be decoded despite the obstruction.",
    "logo_size":   "How large the logo is relative to the QR code width.\n20% is a safe default. Above 30% may cause scan failures\neven with H correction.",
    "clipboard":   "Copies the PNG to your clipboard immediately after saving,\nso you can paste it into Word, Slack, email, etc.",
    "gen":         "Saves both a PNG image and a scalable SVG file to your chosen folder.",
    "shortcut":    "Create a desktop shortcut that launches this app directly.",
}

DEFAULTS: dict = {
    "error_correction":  "M",
    "fg_color":          "#000000",
    "bg_color":          "#ffffff",
    "transparent_bg":    False,
    "module_shape":      "Square",
    "quiet_zone":        "4",
    "png_size":          "512",
    "output_folder":     DOWNLOADS,
    "filename_template": "{domain}_{date}",
    "logo_path":         "",
    "logo_size_pct":     20,
    "copy_to_clipboard": False,
    "recent_urls":       [],
    "theme":             "dark",
    "window_geometry":   "",
    "window_state":      "zoomed",
}

# ── Settings persistence ───────────────────────────────────────────────────────

def load_settings() -> dict:
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE) as fh:
                return {**DEFAULTS, **json.load(fh)}
        except Exception:
            pass
    return dict(DEFAULTS)


def save_settings(data: dict) -> None:
    os.makedirs(SETTINGS_DIR, exist_ok=True)
    with open(SETTINGS_FILE, "w") as fh:
        json.dump(data, fh, indent=2)


# ── URL reachability check ─────────────────────────────────────────────────────

def check_url(url: str) -> tuple[str, str]:
    """HEAD request to url. Returns (state, message) where state: ok | warn | error."""
    ctx = ssl.create_default_context()
    try:
        req = urllib.request.Request(
            url, method="HEAD",
            headers={"User-Agent": "QR-Code-Builder/1.0"})
        with urllib.request.urlopen(req, timeout=6, context=ctx) as r:
            return "ok", f"Reachable (HTTP {r.status})"
    except urllib.error.HTTPError as e:
        if e.code == 405:
            return "warn", "Server OK (does not allow HEAD requests)"
        if 200 <= e.code < 400:
            return "ok", f"Reachable (HTTP {e.code})"
        return "error", f"HTTP {e.code} — {e.reason}"
    except ssl.SSLError:
        return "warn", "SSL certificate issue — URL may still work in a browser"
    except urllib.error.URLError as e:
        r = str(e.reason).lower()
        if any(k in r for k in ("getaddrinfo", "nodename", "name or service")):
            return "error", "Domain not found — check the URL"
        return "error", str(e.reason)[:60]
    except Exception as e:
        return "error", str(e)[:60]


# ── QR rendering ───────────────────────────────────────────────────────────────

def _rgba(hex_color: str, alpha: int = 255) -> tuple:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


def render_png(
    qr, size: int, fg: str, bg: str, transparent: bool,
    shape: str, quiet_zone: int, logo_path: str, logo_pct: int,
) -> Image.Image:
    matrix = qr.matrix
    n      = len(matrix)
    total  = n + 2 * quiet_zone
    mod    = max(1, size // total)
    canvas = mod * total

    bg_fill = (0, 0, 0, 0) if transparent else _rgba(bg)
    fg_fill = _rgba(fg)

    img  = Image.new("RGBA", (canvas, canvas), bg_fill)
    draw = ImageDraw.Draw(img)

    for y, row in enumerate(matrix):
        for x, dark in enumerate(row):
            if dark & 0x1:
                px = (x + quiet_zone) * mod
                py = (y + quiet_zone) * mod
                x2, y2 = px + mod - 1, py + mod - 1
                if shape == "Circle":
                    draw.ellipse([px + 1, py + 1, x2 - 1, y2 - 1], fill=fg_fill)
                elif shape == "Rounded":
                    draw.rounded_rectangle([px, py, x2, y2],
                                           radius=max(1, mod // 3), fill=fg_fill)
                else:
                    draw.rectangle([px, py, x2, y2], fill=fg_fill)

    if logo_path and os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGBA")
            ls   = int(canvas * logo_pct / 100)
            logo = logo.resize((ls, ls), Image.LANCZOS)
            cx   = (canvas - ls) // 2
            img.paste(logo, (cx, cx), logo)
        except Exception:
            pass

    if canvas != size:
        img = img.resize((size, size), Image.LANCZOS)
    return img


def render_svg(qr, fg: str, bg: str, transparent: bool, quiet_zone: int) -> bytes:
    buf   = io.BytesIO()
    light = None if transparent else bg
    qr.save(buf, kind="svg", dark=fg, light=light, border=quiet_zone, scale=10)
    return buf.getvalue()


def build_filename(template: str, url: str) -> str:
    try:
        domain = urlparse(url).netloc.lstrip("www.").replace(".", "-") or "qr"
    except Exception:
        domain = "qr"
    date = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = template.replace("{domain}", domain).replace("{date}", date)
    return re.sub(r'[<>:"/\\|?*\s]', "-", name)


def normalise_url(raw: str) -> str | None:
    raw = raw.strip()
    if not raw:
        return None
    if not re.match(r"^[a-zA-Z][\w+\-.]*://", raw):
        raw = "https://" + raw
    return raw


# ── Tooltip ────────────────────────────────────────────────────────────────────

class Tooltip:
    """Hover tooltip for any Tk/CTk widget. Appears after a short delay."""
    _DELAY = 650

    def __init__(self, widget, text: str) -> None:
        self._w    = widget
        self._text = text
        self._job  = None
        self._win  = None
        try:
            widget.bind("<Enter>",       self._enter, add="+")
            widget.bind("<Leave>",       self._leave, add="+")
            widget.bind("<ButtonPress>", self._leave, add="+")
        except (NotImplementedError, tk.TclError):
            pass  # some CTk widgets (e.g. CTkSegmentedButton) don't support bind

    def _enter(self, _=None) -> None:
        self._cancel()
        self._job = self._w.after(self._DELAY, self._show)

    def _leave(self, _=None) -> None:
        self._cancel()
        if self._win:
            self._win.destroy()
            self._win = None

    def _cancel(self) -> None:
        if self._job:
            self._w.after_cancel(self._job)
            self._job = None

    def _show(self) -> None:
        if self._win:
            return
        x = self._w.winfo_rootx() + 14
        y = self._w.winfo_rooty() + self._w.winfo_height() + 5
        self._win = tw = tk.Toplevel(self._w)
        tw.wm_overrideredirect(True)
        tw.wm_attributes("-topmost", True)
        tw.wm_geometry(f"+{x}+{y}")
        dark = ctk.get_appearance_mode().lower() == "dark"
        bg   = "#2a2a2a" if dark else "#fafafa"
        fg   = "#e0e0e0" if dark else "#1a1a1a"
        bd   = "#505050" if dark else "#c0c0c0"
        outer = tk.Frame(tw, bg=bd, bd=1)
        outer.pack(fill="both", expand=True)
        tk.Label(outer, text=self._text, bg=bg, fg=fg,
                 justify="left", font=("Segoe UI", 9),
                 wraplength=300, padx=9, pady=7).pack()


# ── Help dialog ────────────────────────────────────────────────────────────────

class HelpDialog(ctk.CTkToplevel):
    """Tabbed reference window explaining every setting."""

    # Each entry: (text, is_heading)
    _TABS: dict[str, list[tuple[str, bool]]] = {
        "Error Correction": [
            ("Error Correction controls how much of the QR code can be physically "
             "damaged, dirty, or obscured and still scan correctly. Higher levels "
             "add redundancy — the code becomes slightly larger but far more durable.", False),
            ("L — Low  (7% recovery)", True),
            ("Up to 7% of the data can be lost and recovered. Produces the smallest "
             "possible code. Use when print quality is perfect and there is no logo.", False),
            ("M — Medium  (15% recovery)", True),
            ("The default setting. A balanced choice between code size and resilience. "
             "Suitable for most digital and print uses.", False),
            ("Q — Quartile  (25% recovery)", True),
            ("Recommended for printed materials that may get scratched, dirty, or worn "
             "— e.g. stickers, packaging, or outdoor signage.", False),
            ("H — High  (30% recovery)", True),
            ("Maximum resilience. Always use H when embedding a logo — the logo covers "
             "the centre of the code, and H correction compensates for that data loss.", False),
        ],
        "Quiet Zone": [
            ("The quiet zone is the plain, unprinted border surrounding the QR code "
             "pattern. It is always the background colour (or transparent).", False),
            ("Why does it exist?", True),
            ("Scanners need clear space to locate where the code starts and ends. "
             "Without a quiet zone, the code blends into surrounding content and many "
             "scanners will fail to read it entirely.", False),
            ("How many modules?", True),
            ("One 'module' equals the width of one data dot. The QR standard specifies "
             "a minimum of 4 modules on all four sides. Setting it below 2 can cause "
             "scan failures on many devices, especially on busy or coloured backgrounds.", False),
            ("Recommendation", True),
            ("Leave this at 4 for maximum compatibility. You can reduce it if the code "
             "will always be scanned in controlled conditions and space is critical "
             "(e.g. a small label).", False),
        ],
        "Module Shape": [
            ("Each dark element in a QR code is called a module. The three large squares "
             "in the corners are finder patterns — they are always square regardless of "
             "the shape setting.", False),
            ("Square", True),
            ("The standard look. All scanners handle it perfectly. Use this for "
             "maximum compatibility.", False),
            ("Rounded", True),
            ("Modules have rounded corners. Gives a softer, modern look and is still "
             "highly reliable. Recommended for branded codes.", False),
            ("Circle", True),
            ("Modules are dots. Decorative and distinctive, but can reduce scan "
             "reliability. Use Q or H error correction and test before printing at scale.", False),
            ("Note: SVG output", True),
            ("The SVG file always uses standard square modules regardless of this "
             "setting. Shape customisation applies to the PNG only.", False),
        ],
        "Filename Template": [
            ("You can control how saved files are named using the template field.", False),
            ("{domain}", True),
            ("Replaced with the domain of the URL, with dots converted to dashes.\n"
             "Example:  https://www.github.com  →  github-com", False),
            ("{date}", True),
            ("Replaced with the current date and time in YYYYMMDD_HHMMSS format.\n"
             "Example:  20261016_143022", False),
            ("Full example", True),
            ("Template:  {domain}_{date}\n"
             "URL:       https://github.com\n"
             "Result:    github-com_20261016_143022.png\n"
             "           github-com_20261016_143022.svg", False),
        ],
    }

    def __init__(self, parent: ctk.CTk, initial_tab: str = "") -> None:
        super().__init__(parent)
        self.title(f"{APP_NAME} — Help")
        self.geometry("530x560")
        self.minsize(440, 380)
        self.grab_set()
        _apply_window_icon(self)

        self.tabs = ctk.CTkTabview(self, anchor="nw")
        self.tabs.pack(fill="both", expand=True, padx=12, pady=(12, 4))

        for title, items in self._TABS.items():
            tab = self.tabs.add(title)
            tab.grid_rowconfigure(0, weight=1)
            tab.grid_columnconfigure(0, weight=1)
            sf = ctk.CTkScrollableFrame(tab, fg_color="transparent")
            sf.grid(row=0, column=0, sticky="nsew")
            sf.grid_columnconfigure(0, weight=1)
            for i, (text, bold) in enumerate(items):
                pady = (10, 1) if bold else (1, 4)
                ctk.CTkLabel(
                    sf, text=text,
                    font=ctk.CTkFont(size=12, weight="bold" if bold else "normal"),
                    wraplength=460, justify="left", anchor="w",
                ).grid(row=i, column=0, padx=12, pady=pady, sticky="w")

        ctk.CTkButton(self, text="Close", width=100,
                      command=self.destroy).pack(pady=(4, 12))

        if initial_tab and initial_tab in self._TABS:
            self.after(60, lambda: self.tabs.set(initial_tab))


# ── About dialog ──────────────────────────────────────────────────────────────

class AboutDialog(ctk.CTkToplevel):
    """Credits and desktop-shortcut helper."""

    _CREDITS = [
        ("segno",
         "QR code generation — PNG and native SVG output",
         "github.com/heuer/segno"),
        ("CustomTkinter",
         "Modern GUI framework built on top of Tkinter",
         "github.com/TomSchimansky/CustomTkinter"),
        ("Pillow (PIL)",
         "Image rendering, module-shape drawing, logo embedding",
         "github.com/python-pillow/Pillow"),
    ]

    def __init__(self, parent: ctk.CTk, shortcut_fn) -> None:
        super().__init__(parent)
        self.title(f"About {APP_NAME}")
        self.geometry("420x480")
        self.resizable(False, False)
        self.grab_set()
        _apply_window_icon(self)

        ctk.CTkLabel(self, text=APP_NAME,
                     font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(28, 4))
        ctk.CTkLabel(self, text=f"Version {APP_VERSION}",
                     text_color="gray60").pack()

        self._sep()

        ctk.CTkLabel(self, text=f"Created by  {APP_AUTHOR}",
                     font=ctk.CTkFont(size=13)).pack(pady=(0, 14))

        ctk.CTkLabel(self, text="Built with open-source libraries",
                     font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=28)

        for name, desc, url in self._CREDITS:
            row = ctk.CTkFrame(self, fg_color="transparent")
            row.pack(fill="x", padx=28, pady=(6, 0))
            ctk.CTkLabel(row, text=f"•  {name}",
                         font=ctk.CTkFont(weight="bold"),
                         anchor="w").pack(anchor="w")
            ctk.CTkLabel(row, text=f"    {desc}",
                         text_color="gray60", anchor="w").pack(anchor="w")
            ctk.CTkLabel(row, text=f"    {url}",
                         text_color="gray60", font=ctk.CTkFont(size=11),
                         anchor="w").pack(anchor="w")

        self._sep()

        ctk.CTkButton(
            self, text="Create Desktop Shortcut",
            fg_color="transparent", border_width=1,
            command=shortcut_fn,
        ).pack(fill="x", padx=28, pady=(0, 8))

        ctk.CTkButton(self, text="Close", width=100,
                      command=self.destroy).pack(pady=(0, 20))

    def _sep(self) -> None:
        ctk.CTkFrame(self, height=1, fg_color="gray40").pack(
            fill="x", padx=24, pady=12)


# ── App ────────────────────────────────────────────────────────────────────────

class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.cfg = load_settings()
        ctk.set_appearance_mode(self.cfg.get("theme", "dark"))
        ctk.set_default_color_theme("blue")
        self.title(APP_NAME)
        _apply_window_icon(self)

        # Always set a sensible restored size first (used when un-maximising)
        saved_geom  = self.cfg.get("window_geometry", "")
        saved_state = self.cfg.get("window_state", "zoomed")
        self.geometry("960x900")
        if saved_geom:
            try:
                self.geometry(saved_geom)
            except Exception:
                pass
        self.minsize(820, 700)
        # Start maximised by default; restore previous state on subsequent runs
        self.after(10, lambda: self.state(
            saved_state if saved_state in ("zoomed", "normal") else "zoomed"))

        self._debounce_id:  str | None = None
        self._check_url_id: str | None = None
        self._photo_ref:    ImageTk.PhotoImage | None = None
        self._help_win:     HelpDialog | None = None
        self._about_win:    AboutDialog | None = None

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_ui()
        self.after(120, self._refresh_preview)

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._left_frame = ctk.CTkScrollableFrame(self, width=312, corner_radius=0)
        self._left_frame.grid(row=0, column=0, sticky="nsew")
        self._left_frame.grid_columnconfigure(0, weight=1)
        self._build_left(self._left_frame)
        # Forward scroll-wheel events from any child widget to the left panel
        self.bind_all("<MouseWheel>", self._on_mousewheel)

        right = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=16, pady=16)
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)
        self._build_right(right)

    def _build_left(self, p: ctk.CTkScrollableFrame) -> None:  # noqa: C901
        r    = 0
        SMAL = ctk.CTkFont(size=11)

        # ── Header: title + help button ───────────────────────────────────
        hdr = ctk.CTkFrame(p, fg_color="transparent")
        hdr.grid(row=r, column=0, pady=(16, 8), padx=16, sticky="ew"); r += 1
        hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hdr, text=APP_NAME,
                     font=ctk.CTkFont(size=17, weight="bold")).grid(
            row=0, column=0, sticky="w")
        help_btn = ctk.CTkButton(
            hdr, text="?", width=28, height=28, corner_radius=14,
            fg_color="transparent", border_width=1,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._open_help,
        )
        help_btn.grid(row=0, column=1)
        Tooltip(help_btn, "Open Help — explains every setting in detail")

        about_btn = ctk.CTkButton(
            hdr, text="i", width=28, height=28, corner_radius=14,
            fg_color="transparent", border_width=1,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._open_about,
        )
        about_btn.grid(row=0, column=2, padx=(4, 0))
        Tooltip(about_btn, "About this app — credits and desktop shortcut")

        # ── URL ──────────────────────────────────────────────────────────
        self._section_label(p, r, "URL"); r += 1
        self.url_var   = tk.StringVar(value="")
        recent         = self.cfg.get("recent_urls", [])
        self.url_combo = ctk.CTkComboBox(
            p, variable=self.url_var,
            values=recent[:10] if recent else [],
            command=lambda _: self._on_url_change(),
            width=280,
        )
        self.url_combo.set("")
        self.url_combo.grid(row=r, column=0, padx=16, pady=(0, 2), sticky="ew"); r += 1
        Tooltip(self.url_combo, TIPS["url"])
        self.url_var.trace_add("write", lambda *_: self._on_url_change())

        # URL reachability status line
        self.url_status_var = tk.StringVar(value="")
        self.url_status_lbl = ctk.CTkLabel(
            p, textvariable=self.url_status_var,
            font=SMAL, anchor="w",
        )
        self.url_status_lbl.grid(row=r, column=0, padx=20, pady=(0, 8), sticky="ew"); r += 1

        # ── Output ───────────────────────────────────────────────────────
        self._separator(p, r); r += 1
        self._section_label(p, r, "Output"); r += 1

        ctk.CTkLabel(p, text="PNG Size").grid(row=r, column=0, padx=16, sticky="w"); r += 1
        self.size_var  = tk.StringVar(value=str(self.cfg["png_size"]))
        size_menu = ctk.CTkOptionMenu(
            p, variable=self.size_var,
            values=["256", "512", "1024", "2048"],
            command=lambda _: self._schedule_preview(),
        )
        size_menu.grid(row=r, column=0, padx=16, pady=(0, 8), sticky="ew"); r += 1
        Tooltip(size_menu, TIPS["size"])

        ctk.CTkLabel(p, text="Output Folder").grid(row=r, column=0, padx=16, sticky="w"); r += 1
        frow = ctk.CTkFrame(p, fg_color="transparent")
        frow.grid(row=r, column=0, padx=16, pady=(0, 8), sticky="ew"); r += 1
        frow.grid_columnconfigure(0, weight=1)
        self.folder_var = tk.StringVar(value=self.cfg["output_folder"])
        fe = ctk.CTkEntry(frow, textvariable=self.folder_var)
        fe.grid(row=0, column=0, sticky="ew")
        Tooltip(fe, TIPS["folder"])
        bb = ctk.CTkButton(frow, text="...", width=34, command=self._browse_folder)
        bb.grid(row=0, column=1, padx=(4, 0))
        Tooltip(bb, "Browse for an output folder")

        ctk.CTkLabel(p, text="Filename Template").grid(
            row=r, column=0, padx=16, sticky="w"); r += 1
        ctk.CTkLabel(p, text="{domain}  {date}  available",
                     text_color="gray60", font=SMAL).grid(
            row=r, column=0, padx=16, sticky="w"); r += 1
        self.fname_var = tk.StringVar(value=self.cfg["filename_template"])
        fn_entry = ctk.CTkEntry(p, textvariable=self.fname_var)
        fn_entry.grid(row=r, column=0, padx=16, pady=(2, 8), sticky="ew"); r += 1
        Tooltip(fn_entry, TIPS["filename"])

        # ── Appearance ───────────────────────────────────────────────────
        self._separator(p, r); r += 1
        self._section_label(p, r, "Appearance"); r += 1

        cf = ctk.CTkFrame(p, fg_color="transparent")
        cf.grid(row=r, column=0, padx=16, pady=(0, 6), sticky="ew"); r += 1
        self.fg_var = tk.StringVar(value=self.cfg["fg_color"])
        self.bg_var = tk.StringVar(value=self.cfg["bg_color"])
        _, fg_btn = self._color_row(cf, 0, "Foreground colour", self.fg_var)
        self.bg_swatch, self.bg_btn = self._color_row(cf, 1, "Background colour", self.bg_var)
        Tooltip(fg_btn, TIPS["fg_color"])
        Tooltip(self.bg_btn, TIPS["bg_color"])

        self.trans_var = tk.BooleanVar(value=self.cfg["transparent_bg"])
        tcb = ctk.CTkCheckBox(p, text="Transparent background (PNG + SVG)",
                               variable=self.trans_var, command=self._on_transparent)
        tcb.grid(row=r, column=0, padx=16, pady=(0, 8), sticky="w"); r += 1
        Tooltip(tcb, TIPS["transparent"])

        ctk.CTkLabel(p, text="Module Shape").grid(row=r, column=0, padx=16, sticky="w"); r += 1
        self.shape_var = tk.StringVar(value=self.cfg["module_shape"])
        sh_menu = ctk.CTkOptionMenu(
            p, variable=self.shape_var,
            values=["Square", "Circle", "Rounded"],
            command=lambda _: self._schedule_preview(),
        )
        sh_menu.grid(row=r, column=0, padx=16, pady=(0, 2), sticky="ew"); r += 1
        Tooltip(sh_menu, TIPS["shape"])
        ctk.CTkButton(
            p, text="What do these mean?", height=22,
            fg_color="transparent", text_color="gray60", font=SMAL,
            hover=False, anchor="w",
            command=lambda: self._open_help("Module Shape"),
        ).grid(row=r, column=0, padx=14, pady=(0, 6), sticky="w"); r += 1

        # ── QR Settings ──────────────────────────────────────────────────
        self._separator(p, r); r += 1
        self._section_label(p, r, "QR Settings"); r += 1

        # Error Correction
        ec_hdr = ctk.CTkFrame(p, fg_color="transparent")
        ec_hdr.grid(row=r, column=0, padx=16, sticky="ew"); r += 1
        ctk.CTkLabel(ec_hdr, text="Error Correction").grid(row=0, column=0, sticky="w")
        ec_q = ctk.CTkButton(
            ec_hdr, text="?", width=20, height=20, corner_radius=10,
            fg_color="transparent", border_width=1, font=ctk.CTkFont(size=10),
            command=lambda: self._open_help("Error Correction"),
        )
        ec_q.grid(row=0, column=1, padx=(6, 0))
        Tooltip(ec_q, "Click for a full explanation of Error Correction levels")

        self.ec_var = tk.StringVar(value=self.cfg["error_correction"])
        ec_seg = ctk.CTkSegmentedButton(
            p, values=["L", "M", "Q", "H"],
            variable=self.ec_var,
            command=self._on_ec_change,
        )
        ec_seg.grid(row=r, column=0, padx=16, pady=(4, 2), sticky="ew"); r += 1
        Tooltip(ec_seg, TIPS["ec"])

        self.ec_desc = ctk.CTkLabel(
            p, text=EC_DESCRIPTIONS.get(self.cfg["error_correction"], ""),
            text_color="gray60", font=SMAL,
            wraplength=275, justify="left", anchor="w",
        )
        self.ec_desc.grid(row=r, column=0, padx=16, pady=(0, 8), sticky="w"); r += 1

        # Quiet Zone
        qz_hdr = ctk.CTkFrame(p, fg_color="transparent")
        qz_hdr.grid(row=r, column=0, padx=16, sticky="ew"); r += 1
        ctk.CTkLabel(qz_hdr, text="Quiet Zone").grid(row=0, column=0, sticky="w")
        qz_q = ctk.CTkButton(
            qz_hdr, text="?", width=20, height=20, corner_radius=10,
            fg_color="transparent", border_width=1, font=ctk.CTkFont(size=10),
            command=lambda: self._open_help("Quiet Zone"),
        )
        qz_q.grid(row=0, column=1, padx=(6, 0))
        Tooltip(qz_q, "Click for a full explanation of the Quiet Zone")

        ctk.CTkLabel(p, text="Blank border around the QR code (standard = 4 modules)",
                     text_color="gray60", font=SMAL).grid(
            row=r, column=0, padx=16, sticky="w"); r += 1
        self.qz_var = tk.StringVar(value=str(self.cfg["quiet_zone"]))
        qz_menu = ctk.CTkOptionMenu(
            p, variable=self.qz_var,
            values=[str(x) for x in range(0, 11)],
            command=lambda _: self._schedule_preview(),
        )
        qz_menu.grid(row=r, column=0, padx=16, pady=(2, 8), sticky="ew"); r += 1
        Tooltip(qz_menu, TIPS["quiet_zone"])

        # ── Logo / Icon ───────────────────────────────────────────────────
        self._separator(p, r); r += 1
        self._section_label(p, r, "Logo / Icon"); r += 1
        ctk.CTkLabel(p, text="Set Error Correction to H when using a logo",
                     text_color="gray60", font=SMAL).grid(
            row=r, column=0, padx=16, sticky="w"); r += 1

        lrow = ctk.CTkFrame(p, fg_color="transparent")
        lrow.grid(row=r, column=0, padx=16, pady=(4, 2), sticky="ew"); r += 1
        lrow.grid_columnconfigure(0, weight=1)
        self.logo_var = tk.StringVar(value=self.cfg["logo_path"])
        le = ctk.CTkEntry(lrow, textvariable=self.logo_var,
                          placeholder_text="No logo selected")
        le.grid(row=0, column=0, sticky="ew")
        Tooltip(le, TIPS["logo"])
        ctk.CTkButton(lrow, text="...", width=34,
                      command=self._browse_logo).grid(row=0, column=1, padx=(4, 0))
        ctk.CTkButton(lrow, text="X", width=28,
                      command=lambda: self.logo_var.set("")).grid(
            row=0, column=2, padx=(4, 0))
        self.logo_var.trace_add("write", lambda *_: self._schedule_preview())

        ctk.CTkLabel(p, text="Logo Size (% of QR width)").grid(
            row=r, column=0, padx=16, sticky="w"); r += 1
        self.logo_pct_var = tk.DoubleVar(value=float(self.cfg["logo_size_pct"]))
        ls = ctk.CTkSlider(
            p, from_=5, to=35, variable=self.logo_pct_var,
            number_of_steps=30, command=lambda _: self._schedule_preview(),
        )
        ls.grid(row=r, column=0, padx=16, pady=(0, 2), sticky="ew"); r += 1
        Tooltip(ls, TIPS["logo_size"])
        self.logo_pct_label = ctk.CTkLabel(
            p, text=f"{int(self.logo_pct_var.get())}%", font=SMAL)
        self.logo_pct_label.grid(row=r, column=0, padx=16, sticky="w"); r += 1
        self.logo_pct_var.trace_add(
            "write", lambda *_: self.logo_pct_label.configure(
                text=f"{int(self.logo_pct_var.get())}%"))

        # ── Actions ───────────────────────────────────────────────────────
        self._separator(p, r); r += 1
        self._section_label(p, r, "Actions"); r += 1

        self.clip_var = tk.BooleanVar(value=self.cfg["copy_to_clipboard"])
        ccb = ctk.CTkCheckBox(p, text="Copy PNG to clipboard after saving",
                               variable=self.clip_var)
        ccb.grid(row=r, column=0, padx=16, pady=(0, 8), sticky="w"); r += 1
        Tooltip(ccb, TIPS["clipboard"])

        trow = ctk.CTkFrame(p, fg_color="transparent")
        trow.grid(row=r, column=0, padx=16, pady=(0, 8), sticky="ew"); r += 1
        ctk.CTkLabel(trow, text="Theme:").grid(row=0, column=0, sticky="w")
        self.theme_var = tk.StringVar(value=self.cfg.get("theme", "dark").capitalize())
        ctk.CTkOptionMenu(
            trow, variable=self.theme_var,
            values=["Dark", "Light", "System"],
            command=lambda v: ctk.set_appearance_mode(v.lower()),
            width=120,
        ).grid(row=0, column=1, padx=8)

        ctk.CTkButton(
            p, text="+ Create Desktop Shortcut",
            fg_color="transparent", hover=False,
            text_color=("gray40", "gray60"),
            font=ctk.CTkFont(size=11),
            anchor="w", height=20,
            command=self._create_shortcut,
        ).grid(row=r, column=0, padx=14, pady=(0, 20), sticky="w"); r += 1

    def _build_right(self, p: ctk.CTkFrame) -> None:
        pf = ctk.CTkFrame(p, corner_radius=12)
        pf.grid(row=0, column=0, sticky="nsew", pady=(0, 12))
        pf.grid_rowconfigure(0, weight=1)
        pf.grid_columnconfigure(0, weight=1)
        self.preview_lbl = ctk.CTkLabel(
            pf, text="Enter a URL to see a live preview",
            font=ctk.CTkFont(size=13))
        self.preview_lbl.grid(row=0, column=0, padx=24, pady=24)

        bot = ctk.CTkFrame(p, fg_color="transparent")
        bot.grid(row=1, column=0, sticky="ew")
        bot.grid_columnconfigure(0, weight=1)
        self.gen_btn = ctk.CTkButton(
            bot, text="Generate & Save QR Code",
            height=46, font=ctk.CTkFont(size=15, weight="bold"),
            command=self._generate,
        )
        self.gen_btn.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        Tooltip(self.gen_btn, TIPS["gen"])

        self.status_var = tk.StringVar(value="Ready")
        ctk.CTkLabel(bot, textvariable=self.status_var,
                     text_color="gray60", font=ctk.CTkFont(size=12)).grid(row=1, column=0)

    # ── Small UI helpers ───────────────────────────────────────────────────

    def _section_label(self, parent, row: int, text: str) -> None:
        ctk.CTkLabel(parent, text=text,
                     font=ctk.CTkFont(weight="bold")).grid(
            row=row, column=0, padx=16, pady=(6, 2), sticky="w")

    def _separator(self, parent, row: int) -> None:
        ctk.CTkFrame(parent, height=1, fg_color="gray40").grid(
            row=row, column=0, padx=8, pady=5, sticky="ew")

    def _color_row(self, parent, row: int, label: str, var: tk.StringVar):
        swatch = ctk.CTkFrame(parent, width=22, height=22,
                              corner_radius=4, fg_color=var.get())
        swatch.grid(row=row, column=0, padx=(0, 6), pady=3)
        swatch.grid_propagate(False)
        btn = ctk.CTkButton(
            parent, text=label, width=140, height=28,
            command=lambda: self._pick_color(var, swatch),
        )
        btn.grid(row=row, column=1, pady=3, sticky="w")
        return swatch, btn

    def _pick_color(self, var: tk.StringVar, swatch: ctk.CTkFrame) -> None:
        result = colorchooser.askcolor(color=var.get(), title="Pick a colour")
        if result and result[1]:
            var.set(result[1])
            swatch.configure(fg_color=result[1])
            self._schedule_preview()

    def _on_transparent(self) -> None:
        self.bg_btn.configure(state="disabled" if self.trans_var.get() else "normal")
        self._schedule_preview()

    def _on_ec_change(self, value: str = "") -> None:
        v = value or self.ec_var.get()
        self.ec_desc.configure(text=EC_DESCRIPTIONS.get(v, ""))
        self._schedule_preview()

    def _browse_folder(self) -> None:
        d = filedialog.askdirectory(initialdir=self.folder_var.get() or DOWNLOADS)
        if d:
            self.folder_var.set(d)

    def _browse_logo(self) -> None:
        f = filedialog.askopenfilename(
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp"), ("All", "*.*")])
        if f:
            self.logo_var.set(f)

    # ── Scroll forwarding ──────────────────────────────────────────────────

    def _on_mousewheel(self, event) -> None:
        """Forward scroll-wheel events to the left panel when the cursor is over it."""
        try:
            lx = self._left_frame.winfo_rootx()
            lw = self._left_frame.winfo_width()
            if lx <= event.x_root <= lx + lw:
                self._left_frame._parent_canvas.yview_scroll(
                    -1 * (event.delta // 120), "units")
        except Exception:
            pass

    # ── About ──────────────────────────────────────────────────────────────

    def _open_about(self) -> None:
        if self._about_win and self._about_win.winfo_exists():
            self._about_win.focus()
            return
        self._about_win = AboutDialog(self, self._create_shortcut)

    # ── Help ───────────────────────────────────────────────────────────────

    def _open_help(self, tab: str = "") -> None:
        if self._help_win and self._help_win.winfo_exists():
            if tab:
                self._help_win.tabs.set(tab)
            self._help_win.focus()
            return
        self._help_win = HelpDialog(self, initial_tab=tab)

    # ── URL reachability ───────────────────────────────────────────────────

    def _on_url_change(self) -> None:
        self._schedule_preview()
        self._schedule_url_check()

    def _schedule_url_check(self) -> None:
        if self._check_url_id:
            self.after_cancel(self._check_url_id)
        url = normalise_url(self.url_var.get())
        if url:
            self._set_url_status("checking", "Checking...")
            self._check_url_id = self.after(900, lambda: self._run_url_check(url))
        else:
            self._set_url_status("", "")
            self._check_url_id = None

    def _run_url_check(self, url: str) -> None:
        def _work():
            state, msg = check_url(url)
            self.after(0, lambda: self._set_url_status(state, msg))
        threading.Thread(target=_work, daemon=True).start()

    def _set_url_status(self, state: str, msg: str) -> None:
        COLORS = {
            "ok":       "#2ecc71",
            "warn":     "#f39c12",
            "error":    "#e74c3c",
            "checking": "gray60",
            "":         "gray60",
        }
        ICONS = {"ok": "✓", "warn": "⚠", "error": "✗",
                 "checking": "", "": ""}
        icon  = ICONS.get(state, "")
        color = COLORS.get(state, "gray60")
        text  = f"{icon}  {msg}".strip() if msg else ""
        self.url_status_var.set(text)
        self.url_status_lbl.configure(text_color=color)

    # ── Settings snapshot ──────────────────────────────────────────────────

    def _snap(self) -> dict:
        return {
            "error_correction":  self.ec_var.get(),
            "fg_color":          self.fg_var.get(),
            "bg_color":          self.bg_var.get(),
            "transparent_bg":    bool(self.trans_var.get()),
            "module_shape":      self.shape_var.get(),
            "quiet_zone":        int(self.qz_var.get()),
            "png_size":          int(self.size_var.get()),
            "output_folder":     self.folder_var.get(),
            "filename_template": self.fname_var.get(),
            "logo_path":         self.logo_var.get(),
            "logo_size_pct":     int(self.logo_pct_var.get()),
            "copy_to_clipboard": bool(self.clip_var.get()),
            "theme":             self.theme_var.get().lower(),
        }

    # ── Live preview ───────────────────────────────────────────────────────

    def _schedule_preview(self) -> None:
        if self._debounce_id:
            self.after_cancel(self._debounce_id)
        self._debounce_id = self.after(350, self._refresh_preview)

    def _refresh_preview(self) -> None:
        url = normalise_url(self.url_var.get())
        if not url:
            self.preview_lbl.configure(
                text="Enter a URL to see a live preview", image=None)
            return
        try:
            s   = {**self._snap(), "png_size": 380}
            qr  = segno.make(url, error=s["error_correction"])
            png = render_png(
                qr, 380,
                s["fg_color"], s["bg_color"], s["transparent_bg"],
                s["module_shape"], s["quiet_zone"],
                s["logo_path"], s["logo_size_pct"],
            )
            photo = ImageTk.PhotoImage(png)
            self._photo_ref = photo
            self.preview_lbl.configure(image=photo, text="")
        except Exception as exc:
            self.preview_lbl.configure(text=f"Preview error:\n{exc}", image=None)

    # ── Generate & save ────────────────────────────────────────────────────

    def _generate(self) -> None:
        url = normalise_url(self.url_var.get())
        if not url:
            self.status_var.set("Please enter a URL first.")
            return

        self.gen_btn.configure(state="disabled", text="Generating...")
        self.status_var.set("Generating...")
        s = self._snap()

        def _work() -> None:
            try:
                qr  = segno.make(url, error=s["error_correction"])
                png = render_png(
                    qr, s["png_size"],
                    s["fg_color"], s["bg_color"], s["transparent_bg"],
                    s["module_shape"], s["quiet_zone"],
                    s["logo_path"], s["logo_size_pct"],
                )
                svg = render_svg(
                    qr, s["fg_color"], s["bg_color"],
                    s["transparent_bg"], s["quiet_zone"],
                )
                folder = s["output_folder"] or DOWNLOADS
                os.makedirs(folder, exist_ok=True)
                stem     = build_filename(s["filename_template"], url)
                png_path = os.path.join(folder, stem + ".png")
                svg_path = os.path.join(folder, stem + ".svg")
                png.save(png_path, format="PNG")
                with open(svg_path, "wb") as fh:
                    fh.write(svg)
                if s["copy_to_clipboard"]:
                    _copy_png_to_clipboard(png_path)
                recent = [url] + [u for u in self.cfg.get("recent_urls", [])
                                  if u != url]
                self.cfg.update(s)
                self.cfg["recent_urls"] = recent[:10]
                save_settings(self.cfg)
                self.after(0, lambda: self._on_save_done(png_path))
            except Exception as exc:
                self.after(0, lambda: self._on_save_error(str(exc)))

        threading.Thread(target=_work, daemon=True).start()

    def _on_save_done(self, png_path: str) -> None:
        self.gen_btn.configure(state="normal", text="Generate & Save QR Code")
        self.status_var.set(
            f"Saved {os.path.basename(png_path)} + SVG  →  {os.path.dirname(png_path)}")
        self._refresh_preview()
        recent = self.cfg.get("recent_urls", [])
        if recent:
            self.url_combo.configure(values=recent[:10])

    def _on_save_error(self, msg: str) -> None:
        self.gen_btn.configure(state="normal", text="Generate & Save QR Code")
        self.status_var.set(f"Error: {msg}")
        messagebox.showerror("Generation Failed", msg)

    # ── Close & persist ────────────────────────────────────────────────────

    def _on_close(self) -> None:
        self.cfg.update(self._snap())
        self.cfg["window_geometry"] = self.wm_geometry()
        self.cfg["window_state"]    = self.state()
        save_settings(self.cfg)
        self.destroy()

    # ── Desktop shortcut ───────────────────────────────────────────────────

    def _create_shortcut(self) -> None:
        try:
            script  = os.path.abspath(__file__)
            ico     = os.path.join(ASSETS_DIR, "icon.ico")
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            lnk     = os.path.join(desktop, "QR Code Builder.lnk")
            workdir = os.path.dirname(script)
            ps = f"""
$ws    = New-Object -ComObject WScript.Shell
$sc    = $ws.CreateShortcut('{lnk}')
$pyCmd = Get-Command pythonw -ErrorAction SilentlyContinue
if ($pyCmd) {{ $py = $pyCmd.Source }} else {{ $py = (Get-Command python).Source }}
$sc.TargetPath       = $py
$sc.Arguments        = '"{script}"'
$sc.WorkingDirectory = '{workdir}'
$sc.IconLocation     = '{ico},0'
$sc.Description      = 'QR Code Builder'
$sc.Save()
"""
            result = subprocess.run(
                ["powershell", "-Command", ps],
                capture_output=True, text=True)
            if result.returncode == 0:
                messagebox.showinfo("Shortcut Created",
                                    f"Desktop shortcut created:\n{lnk}")
            else:
                messagebox.showerror("Error",
                                     result.stderr or "Failed to create shortcut.")
        except Exception as exc:
            messagebox.showerror("Error", str(exc))


# ── Clipboard ─────────────────────────────────────────────────────────────────

def _copy_png_to_clipboard(png_path: str) -> None:
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "Add-Type -AssemblyName System.Drawing; "
        f'$img = [System.Drawing.Image]::FromFile("{png_path}"); '
        "[System.Windows.Forms.Clipboard]::SetImage($img); "
        "$img.Dispose()"
    )
    try:
        subprocess.run(["powershell", "-Command", ps],
                       capture_output=True, timeout=15)
    except Exception:
        pass


# ── Window icon ────────────────────────────────────────────────────────────────

def _apply_window_icon(window) -> None:
    ico = os.path.join(ASSETS_DIR, "icon.ico")
    if os.path.exists(ico):
        try:
            window.iconbitmap(ico)
        except Exception:
            pass


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    App().mainloop()
