# QR Code Builder

A feature-rich Windows desktop app for generating QR codes as both **PNG** and **SVG** — with a live preview, logo embedding, custom colours, flexible export options, and settings that persist between sessions.

Built with Python and CustomTkinter for a clean, modern look that works in dark and light themes.

---

## Why this app?

Most QR code tools fall into one of three categories: **online generators**, **mobile apps**, or **enterprise software**. None of them are ideal for a designer, developer, or business owner who needs to produce clean, customised QR codes repeatedly on a desktop.

| | Online generators | Mobile apps | QR Code Builder |
|---|---|---|---|
| Works offline | ✗ | ✓ | ✓ |
| Exports true SVG | Rarely | ✗ | ✓ |
| Custom colours & shapes | Limited | Limited | ✓ |
| Logo embedding | Paid tier | Paid tier | ✓ |
| No watermarks | Paid tier | Paid tier | ✓ |
| No account required | ✗ | ✗ | ✓ |
| Settings persist | ✗ | ✓ | ✓ |
| Open source | ✗ | Rarely | ✓ |

**Online generators** (QR Code Generator, QRCode Monkey, etc.) are quick for one-offs but require an internet connection, often add watermarks on free plans, and rarely export a true scalable SVG — they embed a raster image inside an SVG wrapper. Your data also passes through a third-party server.

**Mobile apps** are convenient but poor for production work: small screens, no fine colour control, and no path to a print-ready vector file.

**QR Code Builder** is a free, open-source desktop app that runs entirely on your machine. It produces a genuine SVG (via the [segno](https://github.com/heuer/segno) library) alongside a high-resolution PNG, supports every common customisation option in a single window, and remembers your settings between sessions so repeat work is instant.

---

## Features

- **Live preview** — QR code updates as you type the URL
- **Dual output** — saves both a PNG (raster) and an SVG (infinitely scalable vector) in one click
- **Custom colours** — foreground and background colour pickers
- **Transparent background** — PNG with alpha channel and SVG with no fill
- **Three module shapes** — Square, Rounded, or Circle (PNG only)
- **Four error correction levels** — L / M / Q / H with in-app explanations
- **Configurable quiet zone** — adjustable border width (QR standard = 4 modules)
- **Logo embedding** — paste any image into the centre of the code
- **URL reachability check** — HEAD request verifies the URL is live before you generate
- **Recent URL history** — dropdown of your last 10 URLs
- **Filename template** — `{domain}` and `{date}` placeholders for automatic naming
- **Copy to clipboard** — optionally copies the PNG immediately after saving
- **Dark / Light / System theme** — persists across sessions
- **Desktop shortcut creator** — one-click `.lnk` shortcut on your desktop
- **All settings persist** — window size, theme, colours, folder, and more saved to `~/.qrbuilder/settings.json`

---

## Requirements

- **Python 3.10+**
- **Windows** (clipboard copy and desktop shortcut use PowerShell; the QR generator itself is cross-platform)

---

## Quick Start

### Option A — installer script (recommended)

```bat
install.bat
```

This will:
1. Install all Python dependencies via pip
2. Generate the app icon (`assets/icon.png` and `assets/icon.ico`)
3. Offer to launch the app immediately

### Option B — manual

```bash
pip install -r requirements.txt
python make_icon.py        # generates assets/icon.png + icon.ico
python main.py
```

---

## Dependencies

| Library | Version | Purpose |
|---------|---------|---------|
| [segno](https://github.com/heuer/segno) | ≥ 1.6.1 | QR code generation — native PNG and SVG output |
| [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) | ≥ 5.2.0 | Modern GUI framework built on top of Tkinter |
| [Pillow](https://github.com/python-pillow/Pillow) | ≥ 9.2.0 | Image rendering, module shapes, and logo embedding |

---

## Settings Reference

| Setting | Description | Default |
|---------|-------------|---------|
| **Error Correction** | How much of the code can be damaged and still scan (L=7%, M=15%, Q=25%, H=30%) | M |
| **PNG Size** | Export resolution in pixels | 512 px |
| **Output Folder** | Where PNG and SVG files are saved | ~/Downloads |
| **Filename Template** | Supports `{domain}` and `{date}` placeholders | `{domain}_{date}` |
| **Foreground Colour** | Colour of the dark QR modules | #000000 |
| **Background Colour** | Colour of the light QR modules | #ffffff |
| **Transparent Background** | PNG alpha channel + SVG no-fill | Off |
| **Module Shape** | Square / Rounded / Circle (PNG only; SVG is always square) | Square |
| **Quiet Zone** | Blank border around the code in modules (QR standard = 4) | 4 |
| **Logo Path** | Image file to embed in the QR centre | None |
| **Logo Size** | Logo width as a percentage of the QR code width | 20% |
| **Copy to Clipboard** | Copies the saved PNG to the clipboard automatically | Off |
| **Theme** | Dark / Light / System | Dark |

---

## Error Correction Levels

| Level | Recovery | When to use |
|-------|----------|-------------|
| **L** | 7% | Perfect print quality, no logo, smallest code |
| **M** | 15% | Most digital and everyday print uses (default) |
| **Q** | 25% | Stickers, packaging, outdoor signage — surfaces that wear |
| **H** | 30% | **Always use H when embedding a logo** |

---

## Filename Template

The filename template supports two placeholders:

| Placeholder | Replaced with | Example |
|-------------|---------------|---------|
| `{domain}` | URL domain with dots converted to dashes | `github-com` |
| `{date}` | Current date-time in `YYYYMMDD_HHMMSS` format | `20261016_143022` |

**Example:** template `{domain}_{date}` + URL `https://github.com` → `github-com_20261016_143022.png`

---

## Tips

- Use **H** error correction whenever you embed a logo — the logo physically obstructs the centre of the code, and H-level redundancy compensates for that data loss.
- **Circle** modules are decorative — always test scan reliability before printing at scale. Use Q or H correction with circles.
- The **SVG** is infinitely scalable; set the PNG size large (1024–2048 px) only if you need raster output at high resolution.
- Keep foreground-to-background contrast at a **4:1 ratio or better** for reliable scanning across devices and lighting conditions.
- A **quiet zone** below 2 modules can cause scan failures, especially on busy or coloured backgrounds. The QR specification requires a minimum of 4.
- After generating, use **Copy to Clipboard** to paste the QR code directly into Word, Slack, email, or any design tool without navigating to the output folder.

---

## Project Structure

```
QR Code Builder/
├── main.py              # Main application (GUI + QR logic)
├── make_icon.py         # Generates assets/icon.png and icon.ico
├── requirements.txt     # Python dependencies
├── install.bat          # Windows setup script
├── LICENSE
├── README.md
└── assets/
    ├── icon.png         # 1024×1024 app icon (generated)
    └── icon.ico         # Multi-resolution icon (generated)
```

Settings are stored at `~/.qrbuilder/settings.json` and are never committed to the repository.

---

## Credits

Created by **Martin Pavion**.

Built with open-source libraries:

- **segno** — [github.com/heuer/segno](https://github.com/heuer/segno) — QR code generation
- **CustomTkinter** — [github.com/TomSchimansky/CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) — GUI framework
- **Pillow** — [github.com/python-pillow/Pillow](https://github.com/python-pillow/Pillow) — Image processing

---

## License

[MIT License](LICENSE) — © 2026 Martin Pavion
