import os, sys, json, shutil, subprocess, uuid, random, re, time, tempfile, zipfile, logging, stat, urllib.request
from pathlib import Path
from abc import ABC, abstractmethod


def _ffmpeg_in_path(name: str) -> bool:
    try:
        subprocess.check_output([name, "-version"], stderr=subprocess.DEVNULL)
        return True
    except Exception:
        pass
    # Also check %APPDATA%\ffmpeg\ffmpeg.exe
    if name == "ffmpeg":
        appdata_exe = Path(os.environ.get("APPDATA", "")) / "ffmpeg" / "ffmpeg.exe"
        if appdata_exe.exists():
            _add_to_path(str(appdata_exe.parent))
            return True
    return False

def _ytdlp_in_path(name: str) -> bool:
    try:
        subprocess.check_output([name, "--version"], stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False

def _add_to_path(directory: str):
    d = str(directory)
    if d not in os.environ.get("PATH", ""):
        os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")

def _bootstrap_install():
    import io
    sys.modules['cStringIO'] = io
    print("────────────────────────────────────────────────────────")
    pip_pkgs = [
        ("PyQt5",    "PyQt5"),
        ("PIL",      "Pillow"),
        ("psutil",   "psutil"),
        ("requests", "requests"),
        ("tqdm",     "tqdm"),
    ]
    optional_pkgs = [
        ("cv2",        "opencv-python"),
        ("tinify",     "tinify"),
        ("selenium",   "selenium"),
        ("krakenio",   "krakenio"),
        ("imagekitio", "imagekitio"),
        ("cloudinary", "cloudinary"),
    ]

    def pip_install(import_name, pkg_name):
        """
        Returns:
          (ok, already_present, err_str)
        """
        try:
            __import__(import_name)
            return True, True, ""
        except ImportError:
            pass
        print(f"[PIP] Installing {pkg_name}...")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--quiet", pkg_name],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            print(f"[PIP] {pkg_name} ✓")
            return True, False, ""
        except Exception as e:
            print(f"[PIP] {pkg_name} failed: {e}")
            return False, False, str(e)

    print("[BOOTSTRAP] ── Python packages ───────────────────")
    py_installed = []
    py_failed = []
    for imp, pkg in pip_pkgs:
        ok, _, _err = pip_install(imp, pkg)
        if ok:
            py_installed.append(pkg)
        else:
            py_failed.append(pkg)
    if py_failed:
        print(f"[BOOTSTRAP] Missing (needs install): {', '.join(py_failed)}")
    if py_installed:
        print(f"[BOOTSTRAP] Installed/OK: {', '.join(py_installed)}")

    print("[BOOTSTRAP] ── Optional packages ─────────────────")
    opt_installed = []
    opt_failed = []
    for imp, pkg in optional_pkgs:
        ok, _, _err = pip_install(imp, pkg)
        if ok:
            opt_installed.append(pkg)
        else:
            opt_failed.append(pkg)
    if opt_failed:
        print(f"[BOOTSTRAP] Optional missing (skipped/needs install): {', '.join(opt_failed)}")
    if opt_installed:
        print(f"[BOOTSTRAP] Optional installed/OK: {', '.join(opt_installed)}")

    print("[BOOTSTRAP] ── ffmpeg and yt-dlp tools ───────────")

    is_win   = sys.platform.startswith("win")
    is_mac   = sys.platform == "darwin"

    # ── Per-OS expected ffmpeg locations ──────────────────────────────────────
    if is_win:
        _ff_dirs = [
            Path(os.environ.get("APPDATA", "")) / "ffmpeg",
            Path(os.environ.get("LOCALAPPDATA", "")) / "ffmpeg",
            Path("C:/ffmpeg/bin"),
        ]
        _ff_exe = "ffmpeg.exe"
    elif is_mac:
        _ff_dirs = [
            Path("/opt/homebrew/bin"),
            Path("/usr/local/bin"),
            Path.home() / ".local" / "bin",
        ]
        _ff_exe = "ffmpeg"
    else:
        _ff_dirs = [
            Path("/usr/bin"),
            Path("/usr/local/bin"),
            Path.home() / ".local" / "bin",
        ]
        _ff_exe = "ffmpeg"

    def _find_ffmpeg():
        """Return Path to ffmpeg if found in known locations or PATH."""
        for d in _ff_dirs:
            f = d / _ff_exe
            if f.exists():
                return f
        # Also check plain PATH
        try:
            out = subprocess.check_output(
                ["ffmpeg", "-version"], stderr=subprocess.DEVNULL
            )
            return Path("ffmpeg")
        except Exception:
            return None

    ff_path = _find_ffmpeg()
    ffmpeg_method = {"v": None}
    if ff_path:
        ffmpeg_method["v"] = "found"
        print(f"[BOOTSTRAP] ffmpeg found: {ff_path} ✓")
        _add_to_path(str(ff_path.parent) if ff_path.name != "ffmpeg" or ff_path.parent != Path(".") else "")
    else:
        print("[BOOTSTRAP] ffmpeg not found — attempting install...")

        ffmpeg_method["v"] = None

        def _try_win_install_ffmpeg():
            """Windows: try winget → scoop → choco → direct download."""
            for mgr, cmd in [
                ("winget",  ["winget", "install", "--id", "Gyan.FFmpeg", "-e", "--silent",
                              "--accept-package-agreements", "--accept-source-agreements"]),
                ("scoop",   ["scoop", "install", "ffmpeg"]),
                ("choco",   ["choco", "install", "ffmpeg", "-y"]),
            ]:
                try:
                    print(f"[BOOTSTRAP] Trying {mgr}...")
                    r = subprocess.run(cmd, timeout=300, capture_output=True)
                    if r.returncode == 0:
                        ff = _find_ffmpeg()
                        if ff:
                            ffmpeg_method["v"] = f"installed via {mgr}"
                            print(f"[BOOTSTRAP] ffmpeg installed via {mgr} ✓")
                            return ff
                except Exception:
                    pass

            # Direct download from BtbN GitHub releases
            print("[BOOTSTRAP] Trying direct download (BtbN)...")
            try:
                import urllib.request, zipfile as _zf, tempfile as _tmp
                api = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest"
                with urllib.request.urlopen(api, timeout=20) as r:
                    data = json.loads(r.read())
                asset_url = next(
                    a["browser_download_url"] for a in data["assets"]
                    if "win64" in a["name"] and "gpl" in a["name"]
                    and a["name"].endswith(".zip") and "shared" not in a["name"]
                )
                tmp = Path(_tmp.mkdtemp())
                zp  = tmp / "ffmpeg.zip"
                print(f"[BOOTSTRAP] Downloading {asset_url} ...")
                urllib.request.urlretrieve(asset_url, zp)
                with _zf.ZipFile(zp) as z:
                    z.extractall(tmp)
                ff_exe = next(tmp.rglob("ffmpeg.exe"), None)
                if ff_exe:
                    dst_dir = Path(os.environ.get("APPDATA", Path.home())) / "ffmpeg"
                    dst_dir.mkdir(parents=True, exist_ok=True)
                    for exe in ("ffmpeg.exe", "ffprobe.exe"):
                        src = next(tmp.rglob(exe), None)
                        if src:
                            import shutil as _sh
                            _sh.copy2(src, dst_dir / exe)
                    _add_to_path(str(dst_dir))
                    import shutil as _sh2; _sh2.rmtree(tmp, ignore_errors=True)
                    ff = _find_ffmpeg()
                    if ff:
                        ffmpeg_method["v"] = "installed via direct download (BtbN)"
                        print(f"[BOOTSTRAP] ffmpeg installed via direct download ✓")
                        return ff
            except Exception as e:
                print(f"[BOOTSTRAP] Direct download failed: {e}")
            return None

        def _try_unix_install_ffmpeg():
            """macOS/Linux: try brew/apt/dnf/pacman → pip static build."""
            managers = []
            if is_mac:
                managers = [
                    ["brew",   "install", "ffmpeg"],
                    ["port",   "install", "ffmpeg"],
                ]
            else:
                managers = [
                    ["apt-get", "install", "-y", "ffmpeg"],
                    ["apt",     "install", "-y", "ffmpeg"],
                    ["dnf",     "install", "-y", "ffmpeg"],
                    ["pacman",  "-S", "--noconfirm", "ffmpeg"],
                    ["apk",     "add", "ffmpeg"],
                ]
            for cmd in managers:
                try:
                    print(f"[BOOTSTRAP] Trying {cmd[0]}...")
                    r = subprocess.run(["sudo"] + cmd if not is_mac else cmd,
                                       timeout=300, capture_output=True)
                    if r.returncode == 0:
                        ff = _find_ffmpeg()
                        if ff:
                            ffmpeg_method["v"] = f"installed via {cmd[0]}"
                            print(f"[BOOTSTRAP] ffmpeg installed via {cmd[0]} ✓")
                            return ff
                except Exception:
                    pass

            # Static binary fallback
            try:
                import urllib.request, tempfile as _tmp, stat as _stat
                if is_mac:
                    url = "https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip"
                else:
                    url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
                print(f"[BOOTSTRAP] Downloading static ffmpeg from {url} ...")
                tmp = Path(_tmp.mkdtemp())
                arch = tmp / ("ff.zip" if is_mac else "ff.tar.xz")
                urllib.request.urlretrieve(url, arch)
                if is_mac:
                    import zipfile as _zf
                    with _zf.ZipFile(arch) as z: z.extractall(tmp)
                else:
                    subprocess.run(["tar", "-xf", str(arch), "-C", str(tmp)],
                                   check=True, capture_output=True)
                ff_bin = next(tmp.rglob("ffmpeg"), None)
                if ff_bin and ff_bin.is_file():
                    dst = Path.home() / ".local" / "bin" / "ffmpeg"
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    import shutil as _sh; _sh.copy2(ff_bin, dst)
                    dst.chmod(dst.stat().st_mode | _stat.S_IEXEC | _stat.S_IXGRP | _stat.S_IXOTH)
                    _add_to_path(str(dst.parent))
                    import shutil as _sh2; _sh2.rmtree(tmp, ignore_errors=True)
                    ff = _find_ffmpeg()
                    if ff:
                        ffmpeg_method["v"] = "installed via static binary"
                        print(f"[BOOTSTRAP] ffmpeg installed via static binary ✓")
                        return ff
            except Exception as e:
                print(f"[BOOTSTRAP] Static install failed: {e}")
            return None

        ff_path = _try_win_install_ffmpeg() if is_win else _try_unix_install_ffmpeg()
        if not ff_path:
            print("[BOOTSTRAP] ⚠ Could not install ffmpeg automatically. Please install manually.")
    if ff_path:
        print(f"[BOOTSTRAP] ffmpeg status: OK ({ffmpeg_method['v'] or 'unknown'})")
    else:
        print("[BOOTSTRAP] ffmpeg status: MISSING (needs manual install)")

    # Store resolved path for use by Worker
    if ff_path and ff_path != Path("ffmpeg"):
        os.environ["_HRZN_FFMPEG_EXE"] = str(ff_path)

    # yt-dlp: ensure installed via pip
    ytdlp_method = {"v": None}
    try:
        subprocess.check_output(["yt-dlp", "--version"], stderr=subprocess.DEVNULL)
        ytdlp_method["v"] = "found in PATH"
        print("[BOOTSTRAP] yt-dlp found ✓")
    except Exception:
        print("[BOOTSTRAP] yt-dlp not found — installing via pip...")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--quiet", "--upgrade", "yt-dlp"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            ytdlp_method["v"] = "installed via pip"
            print("[BOOTSTRAP] yt-dlp installed ✓")
        except Exception as e:
            print(f"[BOOTSTRAP] yt-dlp install failed: {e}")
            ytdlp_method["v"] = None

    if ytdlp_method["v"]:
        print(f"[BOOTSTRAP] yt-dlp status: OK ({ytdlp_method['v']})")
    else:
        print("[BOOTSTRAP] yt-dlp status: MISSING (needs manual install)")

    # NodeJS: ensure Node >= 20 so yt-dlp can run --js-runtimes node when building.
    node_method = {"v": None}
    node_attempts = []
    def _node_major_version():
        try:
            out = subprocess.check_output(
                ["node", "--version"], stderr=subprocess.DEVNULL, text=True
            ).strip()
            if out.startswith("v"):
                out = out[1:]
            return int(out.split(".", 1)[0])
        except Exception:
            return None

    def _get_latest_node_v20_tag():
        """Return latest v20.x tag like 'v20.18.0' (best-effort)."""
        try:
            with urllib.request.urlopen("https://nodejs.org/dist/index.json", timeout=20) as r:
                data = json.loads(r.read().decode("utf-8", errors="ignore"))
            v20 = [x.get("version") for x in data if str(x.get("version", "")).startswith("v20.")]
            v20 = [v for v in v20 if v]
            if not v20:
                return "v20.18.0"
            return sorted(v20)[-1]
        except Exception:
            return "v20.18.0"

    def _direct_download_install_node(min_major: int = 20) -> bool:
        import zipfile as _zf
        import tarfile as _tarfile
        import platform as _platform

        tag = _get_latest_node_v20_tag()
        major = int(tag.lstrip("v").split(".", 1)[0])
        if major < min_major:
            return False

        arch_raw = (_platform.machine() or "").lower()
        if is_win:
            node_arch = "arm64" if ("arm" in arch_raw or "aarch64" in arch_raw) else "x64"
            url = f"https://nodejs.org/dist/{tag}/node-{tag}-win-{node_arch}.zip"
            ext = "zip"
        elif is_mac:
            node_arch = "arm64" if ("arm" in arch_raw or "aarch64" in arch_raw) else "x64"
            url = f"https://nodejs.org/dist/{tag}/node-{tag}-darwin-{node_arch}.tar.gz"
            ext = "tar.gz"
        else:
            node_arch = "arm64" if ("arm" in arch_raw or "aarch64" in arch_raw) else "x64"
            url = f"https://nodejs.org/dist/{tag}/node-{tag}-linux-{node_arch}.tar.xz"
            ext = "tar.xz"

        print(f"[BOOTSTRAP] Installing Node.js {tag} via direct download...")
        tmp = Path(tempfile.mkdtemp())
        try:
            archive_path = tmp / ("node." + ext.replace(".", "_"))
            urllib.request.urlretrieve(url, archive_path)

            if is_win:
                with _zf.ZipFile(archive_path) as z:
                    z.extractall(tmp)
            else:
                mode = "r:gz" if ext == "tar.gz" else "r:xz"
                with _tarfile.open(archive_path, mode) as t:
                    t.extractall(tmp)

            extracted_root = next(tmp.rglob(f"node-{tag}-*"), None)
            if extracted_root is None:
                # As fallback, try the canonical prefix: node-v<version>...
                extracted_root = next(tmp.rglob(f"node-v{tag[1:]}-*"), None)
            if extracted_root is None or not extracted_root.exists():
                raise RuntimeError("Could not locate extracted Node directory.")

            dest_parent = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local"))) / "nodejs"
            dest_parent.mkdir(parents=True, exist_ok=True)
            dest_root = dest_parent / extracted_root.name
            if not dest_root.exists():
                shutil.copytree(extracted_root, dest_root)
            _add_to_path(str(dest_root / "bin"))
            return True
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    try:
        node_major = _node_major_version()
        if node_major is not None and node_major >= 20:
            node_method["v"] = f"found (Node major={node_major})"
            print("[BOOTSTRAP] Node.js >=20 found ✓")
        else:
            print("[BOOTSTRAP] Node.js < 20 or not found — attempting install...")

            if is_win:
                # Try package managers first.
                for mgr, cmd in [
                    ("winget", ["winget", "install", "--id", "OpenJS.NodeJS.LTS", "-e", "--silent"]),
                    ("scoop",  ["scoop", "install", "nodejs-lts"]),
                    ("choco",  ["choco", "install", "nodejs-lts", "-y"]),
                ]:
                    try:
                        print(f"[BOOTSTRAP] Trying {mgr}...")
                        node_attempts.append(mgr)
                        r = subprocess.run(cmd, timeout=600, capture_output=True)
                        if r.returncode == 0 and _node_major_version() and _node_major_version() >= 20:
                            node_method["v"] = f"installed via {mgr}"
                            print(f"[BOOTSTRAP] Node.js installed via {mgr} ✓")
                            break
                    except Exception:
                        pass
            elif is_mac:
                # Best-effort brew install (may or may not provide Node 20 LTS)
                for mgr, cmd in [
                    ("brew", ["brew", "install", "node@20"]),
                    ("brew", ["brew", "install", "node"]),
                ]:
                    try:
                        print(f"[BOOTSTRAP] Trying {mgr}...")
                        node_attempts.append(mgr)
                        r = subprocess.run(cmd, timeout=600, capture_output=True)
                        if r.returncode == 0 and _node_major_version() and _node_major_version() >= 20:
                            node_method["v"] = f"installed via {mgr}"
                            print(f"[BOOTSTRAP] Node.js installed via {mgr} ✓")
                            break
                    except Exception:
                        pass
            else:
                # Linux: try common package managers (best-effort). If still <20,
                # fallback to direct Node v20 download.
                # Note: command may fail depending on distro permissions/tools.
                linux_steps = [
                    ("apt-get(nodejs/npm)", [
                        ["sudo", "apt-get", "update"],
                        ["sudo", "apt-get", "install", "-y", "nodejs", "npm"],
                    ]),
                    ("apt(nodejs/npm)", [
                        ["sudo", "apt", "update"],
                        ["sudo", "apt", "install", "-y", "nodejs", "npm"],
                    ]),
                    ("dnf(nodejs/npm)", [
                        ["sudo", "dnf", "install", "-y", "nodejs", "npm"],
                    ]),
                    ("yum(nodejs/npm)", [
                        ["sudo", "yum", "install", "-y", "nodejs", "npm"],
                    ]),
                    ("pacman(nodejs/npm)", [
                        ["sudo", "pacman", "-S", "--noconfirm", "nodejs", "npm"],
                    ]),
                    ("zypper(nodejs/npm)", [
                        ["sudo", "zypper", "install", "-y", "nodejs", "npm"],
                    ]),
                    ("apk(nodejs/npm)", [
                        ["sudo", "apk", "add", "nodejs", "npm"],
                    ]),
                ]

                for label, cmds in linux_steps:
                    try:
                        print(f"[BOOTSTRAP] Trying {label}...")
                        node_attempts.append(label)
                        for c in cmds:
                            subprocess.run(c, timeout=600, capture_output=True)

                        maj = _node_major_version()
                        if maj is not None and maj >= 20:
                            node_method["v"] = f"installed via {label}"
                            print(f"[BOOTSTRAP] Node.js installed via {label} ✓")
                            break
                    except Exception:
                        pass

            # Direct download fallback (works without admin, across all OSes).
            if _node_major_version() is None or _node_major_version() < 20:
                if _direct_download_install_node(20):
                    node_method["v"] = "installed via direct download"
                    print("[BOOTSTRAP] Node.js installed via direct download ✓")
    except Exception as e:
        print(f"[BOOTSTRAP] Node.js auto-install failed: {e}")

    node_final_major = _node_major_version()
    if node_final_major is not None and node_final_major >= 20:
        print(
            f"[BOOTSTRAP] Node.js status: OK (major={node_final_major}, via={node_method['v'] or 'unknown'})"
        )
    else:
        attempts_str = ", ".join(dict.fromkeys(node_attempts)) if node_attempts else "(no attempts recorded)"
        print(
            f"[BOOTSTRAP] Node.js status: MISSING (needs Node.js >=20). Attempts: {attempts_str}"
        )

    print("[BOOTSTRAP] ── Done ──────────────────────────────")

# CLI arguments removed: debug mode is controlled only via Settings.
_IS_DEBUG = False

# Pre-add %APPDATA%\ffmpeg to PATH so bootstrap tool checks can find it
_appdata_ffmpeg = Path(os.environ.get("APPDATA", "")) / "ffmpeg"
if _appdata_ffmpeg.exists():
    _add_to_path(str(_appdata_ffmpeg))

_bootstrap_install()

def _node_major_version():
    """Return Node major version (e.g. 20) or None if node is unavailable."""
    try:
        out = subprocess.check_output(
            ["node", "--version"], stderr=subprocess.DEVNULL, text=True
        ).strip()
        if out.startswith("v"):
            out = out[1:]
        return int(out.split(".", 1)[0])
    except Exception:
        return None

def _get_yt_dlp_js_runtimes_args():
    """
    yt-dlp option: --js-runtimes node
    Only enabled when Node >= 20.
    """
    major = _node_major_version()
    if major is not None and major >= 20:
        return ["--js-runtimes", "node"]
    return []


def _get_ffmpeg_exe() -> str:
    """Return the ffmpeg executable path, preferring the one found/installed by bootstrap."""
    # Check env var set by bootstrap first
    env_path = os.environ.get("_HRZN_FFMPEG_EXE", "")
    if env_path and Path(env_path).exists():
        return env_path
    # Check %APPDATA%\ffmpeg\ffmpeg.exe (Windows)
    appdata_ffmpeg = Path(os.environ.get("APPDATA", "")) / "ffmpeg" / "ffmpeg.exe"
    if appdata_ffmpeg.exists():
        return str(appdata_ffmpeg)
    return "ffmpeg"

import requests
import psutil
from PIL import Image, ImageFilter
from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import Qt, QSize, QTimer, QRectF
from PyQt5.QtGui import QIcon, QPixmap, QFont, QColor, QPalette, QPainter, QPainterPath
from PyQt5.QtWidgets import (
    QApplication, QWidget, QDialog, QGridLayout, QFormLayout, QLabel,
    QLineEdit, QPushButton, QFileDialog, QComboBox, QSpinBox,
    QDoubleSpinBox, QTextEdit, QMessageBox, QProgressBar, QGroupBox,
    QVBoxLayout, QHBoxLayout, QScrollArea, QSizePolicy, QFrame,
    QStackedWidget, QListWidget, QListWidgetItem, QAbstractItemView,
    QCheckBox, QSlider, QRubberBand, QRadioButton, QButtonGroup,
)

config = {}
for line in urllib.request.urlopen("https://tubeo5866.github.io/config.txt").read().decode().splitlines():
    if "=" in line:
        k, v = line.split("=", 1)
        config[k.strip()] = v.strip()

WINDOW_TITLE        = f"TuBeo5866's HorizonUI/NekoUI Extension Studio (v{config['VERSION']}_{config['COMMIT']})"
MAX_FRAMES          = 9999
DEFAULT_FPS         = 20
MEMORY_THRESHOLD    = 80

ANIM_BG_DIR         = "hrzn_animated_background"
LOADING_BG_DIR      = "hrzn_loading_background"
CONTAINER_BG_DIR    = "hrzn_container_background"
SOUNDS_DIR          = "sounds/music/bgm"
UI_DIR              = "ui"

CONTAINER_BG_URL    = "https://tubeo5866.github.io/files/hrzn_container_background.zip"

FRAME_PREFIX_ANIM   = "hans_common_"

class PackIconCropDialog(QDialog):
    """
    Shows a preview of the selected PNG and lets the user drag a square crop
    region plus zoom with a slider. Output is always a 256×256 PNG.
    """

    _PREVIEW_SIZE = 480

    def __init__(self, image_path: str, parent=None):
        super().__init__(parent)
        self._src_path = Path(image_path)
        self._orig_pil = Image.open(str(self._src_path)).convert("RGBA")
        self._zoom      = 1.0
        self._offset_x  = 0
        self._offset_y  = 0
        self._drag_start = None
        self._drag_offset_start = None
        self._result_pil = None

        self.setWindowTitle("Crop & Zoom Pack Icon")
        self.setFixedSize(self._PREVIEW_SIZE + 40, self._PREVIEW_SIZE + 160)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._build()
        self._reset_view()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        hdr = QLabel("🖼  Drag to pan · Scroll or use slider to zoom · Output: 256×256")
        hdr.setStyleSheet("font-weight:bold; font-size:11px;")
        layout.addWidget(hdr)

        self._canvas = QLabel()
        self._canvas.setFixedSize(self._PREVIEW_SIZE, self._PREVIEW_SIZE)
        self._canvas.setStyleSheet(
            "border: 2px solid #555; border-radius: 4px; background: #111;"
        )
        self._canvas.setAlignment(Qt.AlignCenter)
        self._canvas.setCursor(Qt.OpenHandCursor)
        self._canvas.mousePressEvent   = self._on_mouse_press
        self._canvas.mouseMoveEvent    = self._on_mouse_move
        self._canvas.mouseReleaseEvent = self._on_mouse_release
        self._canvas.wheelEvent        = self._on_wheel
        layout.addWidget(self._canvas, alignment=Qt.AlignHCenter)

        zoom_row = QHBoxLayout()
        zoom_row.addWidget(QLabel("Zoom:"))
        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(10, 500)
        self._slider.setValue(100)
        self._slider.setTickInterval(10)
        self._slider.valueChanged.connect(self._on_slider_zoom)
        zoom_row.addWidget(self._slider)
        self._zoom_lbl = QLabel("1.00×")
        self._zoom_lbl.setFixedWidth(46)
        zoom_row.addWidget(self._zoom_lbl)
        layout.addLayout(zoom_row)

        btn_reset = QPushButton("↺  Reset View")
        btn_reset.clicked.connect(self._reset_view)
        layout.addWidget(btn_reset)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine); sep.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("✖  Cancel")
        btn_ok = QPushButton("✔  Use This Crop")
        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self._accept)
        btn_row.addWidget(btn_cancel)
        btn_row.addSpacing(6)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def _reset_view(self):
        """Fit the whole image into the canvas (zoom so the whole image is visible)."""
        w, h = self._orig_pil.size
        short = min(w, h)
        self._zoom = self._PREVIEW_SIZE / short
        self._offset_x = (w - self._PREVIEW_SIZE / self._zoom) / 2
        self._offset_y = (h - self._PREVIEW_SIZE / self._zoom) / 2
        self._clamp_offset()
        self._slider.setValue(int(self._zoom * 100))
        self._refresh()

    def _clamp_offset(self):
        w, h = self._orig_pil.size
        view = self._PREVIEW_SIZE / self._zoom
        self._offset_x = max(0.0, min(self._offset_x, w - view))
        self._offset_y = max(0.0, min(self._offset_y, h - view))

    def _refresh(self):
        w, h = self._orig_pil.size
        view = self._PREVIEW_SIZE / self._zoom

        x0 = int(max(0, self._offset_x))
        y0 = int(max(0, self._offset_y))
        x1 = int(min(w, self._offset_x + view))
        y1 = int(min(h, self._offset_y + view))

        cropped = self._orig_pil.crop((x0, y0, x1, y1))
        preview = cropped.resize((self._PREVIEW_SIZE, self._PREVIEW_SIZE), Image.LANCZOS)

        data = preview.tobytes("raw", "RGBA")
        qimg = QtGui.QImage(data, self._PREVIEW_SIZE, self._PREVIEW_SIZE,
                            QtGui.QImage.Format_RGBA8888)
        px = QPixmap.fromImage(qimg)

        painter = QPainter(px)
        painter.setPen(QtGui.QPen(QColor(255, 255, 255, 80), 1))
        c = self._PREVIEW_SIZE // 2
        painter.drawLine(c - 20, c, c + 20, c)
        painter.drawLine(c, c - 20, c, c + 20)
        painter.end()

        self._canvas.setPixmap(px)
        self._zoom_lbl.setText(f"{self._zoom:.2f}×")

    def _on_mouse_press(self, ev):
        if ev.button() == Qt.LeftButton:
            self._drag_start = ev.pos()
            self._drag_offset_start = (self._offset_x, self._offset_y)
            self._canvas.setCursor(Qt.ClosedHandCursor)

    def _on_mouse_move(self, ev):
        if self._drag_start is not None:
            dx = ev.pos().x() - self._drag_start.x()
            dy = ev.pos().y() - self._drag_start.y()
            src_per_px = 1.0 / self._zoom
            self._offset_x = self._drag_offset_start[0] - dx * src_per_px
            self._offset_y = self._drag_offset_start[1] - dy * src_per_px
            self._clamp_offset()
            self._refresh()

    def _on_mouse_release(self, ev):
        self._drag_start = None
        self._canvas.setCursor(Qt.OpenHandCursor)

    def _on_wheel(self, ev):
        delta = ev.angleDelta().y()
        factor = 1.1 if delta > 0 else 0.9
        mx = ev.pos().x()
        my = ev.pos().y()
        src_per_px = 1.0 / self._zoom
        sx = self._offset_x + mx * src_per_px
        sy = self._offset_y + my * src_per_px
        self._zoom = max(0.1, min(5.0, self._zoom * factor))
        src_per_px_new = 1.0 / self._zoom
        self._offset_x = sx - mx * src_per_px_new
        self._offset_y = sy - my * src_per_px_new
        self._clamp_offset()
        self._slider.blockSignals(True)
        self._slider.setValue(int(self._zoom * 100))
        self._slider.blockSignals(False)
        self._refresh()

    def _on_slider_zoom(self, val):
        new_zoom = val / 100.0
        w, h = self._orig_pil.size
        old_view = self._PREVIEW_SIZE / self._zoom
        new_view = self._PREVIEW_SIZE / new_zoom
        cx = self._offset_x + old_view / 2
        cy = self._offset_y + old_view / 2
        self._zoom = new_zoom
        self._offset_x = cx - new_view / 2
        self._offset_y = cy - new_view / 2
        self._clamp_offset()
        self._refresh()

    def _accept(self):
        w, h = self._orig_pil.size
        view = self._PREVIEW_SIZE / self._zoom
        x0 = int(max(0, self._offset_x))
        y0 = int(max(0, self._offset_y))
        x1 = int(min(w, self._offset_x + view))
        y1 = int(min(h, self._offset_y + view))
        cropped = self._orig_pil.crop((x0, y0, x1, y1))
        self._result_pil = cropped.resize((256, 256), Image.LANCZOS)
        self.accept()

    def get_result(self) -> Image.Image:
        """Returns the cropped 256×256 PIL Image, or None if cancelled."""
        return self._result_pil


# ── Container Background slot definitions ────────────────────────────────────
CONTAINER_BG_SLOTS = [
    ("Anvil",              "anvil_screen.png"),
    ("Beacon",             "beacon_screen.png"),
    ("Brewing",            "brewing_screen.png"),
    ("Cartography",        "cartography_screen.png"),
    ("Chest",              "chest_background.png"),
    ("Enchanting",         "enchanting_screen.png"),
    ("Furnace",            "furnace_background.png"),
    ("Grindstone",         "grindstone_screen.png"),
    ("Horse Inventory",    "horse_screen.png"),
    ("Player Inventory",   "inventory_background.png"),
    ("Loom",               "loom_screen.png"),
    ("Redstone Commons",   "redstone_screen_common.png"),
    ("Smithing",           "smithing_table.png"),
    ("Stone Cutter",       "stone_cutter_screen.png"),
]


class ContainerBgDialog(QDialog):
    """
    Dialog for customising individual container background images.

    Left panel  – one row per slot (label + path field + Browse button).
    Right panel – live preview of the currently focused slot.

    Each slot may have a custom PIL Image (after crop) or a raw path,
    or be left empty (use the ZIP defaults).
    """

    _PREVIEW_W = 280
    _PREVIEW_H = 280

    def __init__(self, slot_data: dict, parent=None):
        """
        slot_data: dict mapping filename → {"pil": PIL.Image|None, "path": str}
                   Mutated in-place on Accept.
        """
        super().__init__(parent)
        self.setWindowTitle("Custom Container Backgrounds")
        self.setMinimumSize(780, 560)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._slot_data   = slot_data          # filename → {"pil", "path"}
        self._focused_key = None
        self._build()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(8)

        hint = QLabel("Optional — leave any field empty to use the default from the downloaded ZIP.")
        hint.setStyleSheet("color:#888; font-size:10px;")
        outer.addWidget(hint)

        splitter_w = QWidget()
        split_h = QHBoxLayout(splitter_w)
        split_h.setContentsMargins(0, 0, 0, 0)
        split_h.setSpacing(10)

        # ── Left: slot rows ───────────────────────────────────────────────────
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_inner = QWidget()
        grid = QGridLayout(left_inner)
        grid.setSpacing(5)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setColumnStretch(1, 1)

        self._fields  = {}   # filename → QLineEdit
        self._previews = {}  # filename → PIL image (after crop) or None

        for row_idx, (label, fname) in enumerate(CONTAINER_BG_SLOTS):
            lbl = QLabel(f"{label}:")
            lbl.setFixedWidth(120)

            field = QLineEdit()
            field.setReadOnly(True)
            field.setPlaceholderText("(default)")
            # Restore previous value if any
            saved = self._slot_data.get(fname, {})
            if saved.get("path"):
                field.setText(saved["path"])
            self._fields[fname] = field

            # Focus → update preview
            field.mousePressEvent = lambda ev, f=fname: self._set_focus(f)

            # Clear button
            btn_clear = QPushButton("✖")
            btn_clear.setFixedWidth(26)
            btn_clear.setToolTip("Clear")
            btn_clear.clicked.connect(lambda _, f=fname: self._clear_slot(f))

            btn = QPushButton("Browse…")
            btn.setFixedWidth(72)
            btn.clicked.connect(lambda _, f=fname: self._browse_slot(f))

            # Thumbnail
            thumb = QLabel()
            thumb.setFixedSize(28, 28)
            thumb.setStyleSheet("border:1px solid #555; border-radius:2px; background:#1a1a1a;")
            thumb.setAlignment(Qt.AlignCenter)
            self._previews[fname] = {"thumb": thumb, "pil": saved.get("pil")}
            if saved.get("pil"):
                self._update_thumb(fname, saved["pil"])

            grid.addWidget(lbl,       row_idx, 0)
            grid.addWidget(field,     row_idx, 1)
            grid.addWidget(thumb,     row_idx, 2)
            grid.addWidget(btn_clear, row_idx, 3)
            grid.addWidget(btn,       row_idx, 4)

        left_scroll.setWidget(left_inner)
        split_h.addWidget(left_scroll, stretch=1)

        # ── Right: preview ────────────────────────────────────────────────────
        right_w = QWidget()
        right_w.setFixedWidth(self._PREVIEW_W + 16)
        right_vbox = QVBoxLayout(right_w)
        right_vbox.setContentsMargins(0, 0, 0, 0)
        right_vbox.setSpacing(6)

        self._preview_lbl_title = QLabel("Preview")
        self._preview_lbl_title.setStyleSheet("font-weight:bold; font-size:11px;")
        self._preview_lbl_title.setAlignment(Qt.AlignCenter)
        right_vbox.addWidget(self._preview_lbl_title)

        self._preview_canvas = QLabel()
        self._preview_canvas.setFixedSize(self._PREVIEW_W, self._PREVIEW_H)
        self._preview_canvas.setStyleSheet(
            "border:2px solid #555; border-radius:4px; background:#111;"
        )
        self._preview_canvas.setAlignment(Qt.AlignCenter)
        right_vbox.addWidget(self._preview_canvas)
        right_vbox.addStretch()

        split_h.addWidget(right_w)
        outer.addWidget(splitter_w, stretch=1)

        # ── Buttons ───────────────────────────────────────────────────────────
        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        outer.addWidget(sep)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("Cancel")
        btn_ok     = QPushButton("Apply")
        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self._apply)
        btn_row.addWidget(btn_cancel)
        btn_row.addSpacing(6)
        btn_row.addWidget(btn_ok)
        outer.addLayout(btn_row)

    # ── Slot actions ──────────────────────────────────────────────────────────
    def _set_focus(self, fname: str):
        self._focused_key = fname
        pil = self._previews[fname]["pil"]
        slot_label = next((l for l, f in CONTAINER_BG_SLOTS if f == fname), fname)
        self._preview_lbl_title.setText(slot_label)
        if pil:
            self._show_preview(pil)
        else:
            self._preview_canvas.clear()
            self._preview_canvas.setText("No image selected")

    def _show_preview(self, pil_img: "Image.Image"):
        thumb = pil_img.convert("RGBA").copy()
        thumb.thumbnail((self._PREVIEW_W, self._PREVIEW_H), Image.LANCZOS)
        data = thumb.tobytes("raw", "RGBA")
        qimg = QtGui.QImage(data, thumb.width, thumb.height, QtGui.QImage.Format_RGBA8888)
        self._preview_canvas.setPixmap(
            QPixmap.fromImage(qimg).scaled(
                self._PREVIEW_W, self._PREVIEW_H,
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        )

    def _update_thumb(self, fname: str, pil_img: "Image.Image"):
        t = pil_img.convert("RGBA").copy()
        t.thumbnail((26, 26), Image.LANCZOS)
        data = t.tobytes("raw", "RGBA")
        qimg = QtGui.QImage(data, t.width, t.height, QtGui.QImage.Format_RGBA8888)
        self._previews[fname]["thumb"].setPixmap(QPixmap.fromImage(qimg))

    def _browse_slot(self, fname: str):
        path, _ = QFileDialog.getOpenFileName(
            self, f"Select image for {fname}",
            filter="Images (*.png *.jpg *.jpeg *.webp *.bmp *.tga);;All Files (*)"
        )
        if not path:
            return
        self._set_focus(fname)
        dlg = PackIconCropDialog(path, parent=self)
        dlg.setWindowTitle(f"Crop — {fname}")
        if dlg.exec_() == QDialog.Accepted:
            result = dlg.get_result()
            if result:
                self._previews[fname]["pil"] = result
                self._fields[fname].setText(path)
                self._update_thumb(fname, result)
                self._show_preview(result)

    def _clear_slot(self, fname: str):
        self._previews[fname]["pil"] = None
        self._fields[fname].clear()
        self._previews[fname]["thumb"].clear()
        if self._focused_key == fname:
            self._preview_canvas.clear()
            self._preview_canvas.setText("No image selected")

    # ── Accept ────────────────────────────────────────────────────────────────
    def _apply(self):
        for fname in self._fields:
            self._slot_data[fname] = {
                "pil":  self._previews[fname]["pil"],
                "path": self._fields[fname].text(),
            }
        self.accept()

    def count_filled(self) -> int:
        return sum(1 for fname in self._fields if self._previews[fname]["pil"] is not None)


class Compressor(ABC):
    def __init__(self, cfg, log_func):
        self.cfg = cfg
        self.log = log_func

    @abstractmethod
    def compress(self, frame_dir: Path):
        pass

class LosslessCompressor(Compressor):
    def compress(self, frame_dir: Path):
        self.log("Lossless mode: no compression applied, keeping original PNGs.")

class PillowCompressor(Compressor):
    def compress(self, frame_dir: Path):
        quality_map = {"low": 50, "medium": 70, "high": 85, "maximum": 95}
        quality = quality_map.get(str(self.cfg.get("pillow_quality", "high")).lower(), 85)
        for f in list(frame_dir.glob("*.png")):
            im = Image.open(f)
            if im.mode in ("RGBA", "LA"):
                bg = Image.new("RGB", im.size, (255, 255, 255))
                bg.paste(im, mask=im.split()[-1])
                im = bg
            else:
                im = im.convert("RGB")
            out = f.with_suffix(".jpg")
            im.save(out, quality=quality)
            f.unlink()
            self.log(f"Converted {f.name} → {out.name}")
        self.log(f"Pillow compression done. Total JPG: {len(list(frame_dir.glob('*.jpg')))}")

class FFmpegCompressor(Compressor):
    def compress(self, frame_dir: Path):
        qv = int(self.cfg.get("ffmpeg_qv") or 1)
        for p in sorted(frame_dir.glob("*.png")):
            jpg_out = p.with_suffix(".jpg")
            cmd = ["ffmpeg", "-y", "-i", str(p), "-q:v", str(qv), str(jpg_out)]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            if proc.returncode != 0:
                raise RuntimeError(f"FFmpeg failed on {p.name}")
            p.unlink()
        self.log(f"FFmpeg compression done.")

class TinyPNGCompressor(Compressor):
    def compress(self, frame_dir: Path):
        import tinify
        if not self.cfg.get("tinify_key"):
            raise RuntimeError("TinyPNG API Key is missing.")
        tinify.key = self.cfg.get("tinify_key")
        for f in frame_dir.glob("*.png"):
            tinify.from_file(str(f)).to_file(str(f))
        self.log("TinyPNG compression done.")

class KrakenCompressor(Compressor):
    def compress(self, frame_dir: Path):
        from krakenio import Client
        client = Client(self.cfg.get("kraken_key"), self.cfg.get("kraken_secret"))
        for f in frame_dir.glob("*.png"):
            result = client.upload(str(f), {"wait": True, "lossy": True, "quality": self.cfg.get("kraken_quality", 90)})
            if result.get("success"):
                data = requests.get(result["kraked_url"]).content
                f.write_bytes(data)
        self.log("Kraken.io compression done.")

class ImageKitCompressor(Compressor):
    def compress(self, frame_dir: Path):
        from imagekitio import ImageKit
        from imagekitio.models.UploadFileRequestOptions import UploadFileRequestOptions
        ik = ImageKit(
            private_key=self.cfg.get("imagekit_secret"),
            public_key=self.cfg.get("imagekit_key"),
            url_endpoint=self.cfg.get("imagekit_urlendpoint")
        )
        for f in frame_dir.glob("*.png"):
            opts = UploadFileRequestOptions(
                file=f, file_name=f.name, folder="/",
                transformation=[{"quality": self.cfg.get("imagekit_quality", 90)}, {"fetch_format": "jpg"}]
            )
            result = ik.upload_file(opts)
            if result.url:
                f.with_suffix(".jpg").write_bytes(requests.get(result.url).content)
                f.unlink()
        self.log("ImageKit compression done.")

class CloudinaryCompressor(Compressor):
    def compress(self, frame_dir: Path):
        import cloudinary, cloudinary.uploader, cloudinary.utils
        cloudinary.config(
            cloud_name=self.cfg.get("cloudinary_name"),
            api_key=self.cfg.get("cloudinary_key"),
            api_secret=self.cfg.get("cloudinary_secret")
        )
        q = self.cfg.get("cloudinary_quality", "auto:best")
        for f in frame_dir.glob("*.png"):
            result = cloudinary.uploader.upload(str(f), quality=q, fetch_format="jpg")
            url, _ = cloudinary.utils.cloudinary_url(result["public_id"], fetch_format="jpg", quality=q)
            f.with_suffix(".jpg").write_bytes(requests.get(url).content)
            f.unlink()
        self.log("Cloudinary compression done.")

class ImageCompressrCompressor(Compressor):
    def compress(self, frame_dir: Path):
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        dl_zip = Path.home() / "Downloads" / "compressedImages.zip"
        opts = Options()
        opts.add_argument("--incognito"); opts.add_argument("--disable-gpu")
        opts.add_argument("--no-sandbox"); opts.add_argument("--disable-dev-shm-usage")
        driver = webdriver.Chrome(options=opts)
        driver.get("https://imagecompressr.com/")
        try:
            fi = WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.ID, "fileInput")))
            fi.send_keys("\n".join(str(p.resolve()) for p in frame_dir.glob("*.png")))
            start = WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.start-compression")))
            start.click()
            for _ in range(600):
                if dl_zip.exists(): break
                time.sleep(1)
            tmp = frame_dir / "_tmp"
            tmp.mkdir(exist_ok=True)
            with zipfile.ZipFile(dl_zip) as zf: zf.extractall(tmp)
            for f in tmp.rglob("*.png"):
                (frame_dir / f.name).write_bytes(f.read_bytes())
            shutil.rmtree(tmp); dl_zip.unlink()
        finally:
            driver.quit()
        self.log("Imagecompressr compression done.")

class CompressorIoCompressor(Compressor):
    def compress(self, frame_dir: Path):
        self.log("CompressorIo: using Pillow as fallback (Selenium optional).")
        PillowCompressor(self.cfg, self.log).compress(frame_dir)

class _ObfuscatedPreview(QWidget):
    """
    Custom widget that renders a parsed sequence of (text, colour, styles, obfuscated)
    spans and animates the obfuscated ones by shuffling random characters every tick.
    """
    _OBFUSC_CHARS = "AaBbCcDdEeFfGgHhIiJjKkLlMmNnOoPpQqRrSsTtUuVvWwXxYyZz0123456789!@#$%^&*()"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._spans = []
        self._rnd_cache = {}
        self.setMinimumHeight(34)
        self.setAutoFillBackground(False)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._timer = QTimer(self)
        self._timer.setInterval(80)
        self._timer.timeout.connect(self._shuffle_obfusc)

    def set_spans(self, spans: list):
        self._spans = spans
        self._rnd_cache = {}
        for i, s in enumerate(spans):
            if s["obfusc"]:
                self._rnd_cache[i] = self._random_str(len(s["text"]))
        has_obfusc = any(s["obfusc"] for s in spans)
        if has_obfusc:
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def _random_str(self, length: int) -> str:
        import random
        return "".join(random.choice(self._OBFUSC_CHARS) for _ in range(max(length, 1)))

    def _shuffle_obfusc(self):
        for i, s in enumerate(self._spans):
            if s["obfusc"]:
                self._rnd_cache[i] = self._random_str(len(s["text"]))
        self.update()

    def closeEvent(self, ev):
        self._timer.stop()
        super().closeEvent(ev)

    def paintEvent(self, event):
        if not self._spans:
            painter = QPainter(self)
            painter.fillRect(self.rect(), QColor("#1a1a1a"))
            painter.setPen(QColor("#555555"))
            f = painter.font(); f.setPointSize(10); painter.setFont(f)
            painter.drawText(self.rect(), Qt.AlignVCenter | Qt.AlignLeft,
                             "  — empty —")
            painter.end()
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.fillRect(self.rect(), QColor("#1a1a1a"))

        base_font = QFont("Consolas, Courier New, Monospace")
        base_font.setPointSize(11)

        x = 8
        y = self.height() // 2

        for i, span in enumerate(self._spans):
            text = self._rnd_cache.get(i, span["text"]) if span["obfusc"] else span["text"]
            if not text:
                continue

            f = QFont(base_font)
            f.setBold(span["bold"])
            f.setItalic(span["italic"])
            if span["strike"] or span["under"]:
                f.setStrikeOut(span["strike"])
                f.setUnderline(span["under"])
            painter.setFont(f)
            painter.setPen(QColor(span["colour"]))

            fm = painter.fontMetrics()
            painter.drawText(x, y + fm.ascent() - fm.height() // 2, text)
            x += fm.horizontalAdvance(text)

        painter.end()

class McFormatDialog(QDialog):
    """
    Small helper that lets the user insert Minecraft § colour / style codes
    into any QLineEdit by picking buttons. Includes a live preview that
    renders § codes with real colours, styles, and animated obfuscation (§k).
    """

    _COLOURS = [
        ("0", "0", "#000000", "#ffffff"),
        ("1", "1", "#0000AA", "#ffffff"),
        ("2", "2", "#00AA00", "#ffffff"),
        ("3", "3", "#00AAAA", "#ffffff"),
        ("4", "4", "#AA0000", "#ffffff"),
        ("5", "5", "#AA00AA", "#ffffff"),
        ("6", "6", "#FFAA00", "#000000"),
        ("7", "7", "#AAAAAA", "#000000"),
        ("8", "8", "#555555", "#ffffff"),
        ("9", "9", "#5555FF", "#ffffff"),
        ("a", "a", "#55FF55", "#000000"),
        ("b", "b", "#55FFFF", "#000000"),
        ("c", "c", "#FF5555", "#000000"),
        ("d", "d", "#FF55FF", "#000000"),
        ("e", "e", "#FFFF55", "#000000"),
        ("f", "f", "#FFFFFF", "#000000"),
    ]
    _COLOUR_MAP = {code: bg for code, _, bg, _ in _COLOURS}

    _STYLES = [
        ("l", "B",  "Bold"),
        ("o", "I",  "Italic"),
        ("m", "S",  "Strikethrough"),
        ("n", "U",  "Underline"),
        ("k", "✦", "Obfuscated (random)"),
        ("r", "R",  "Reset"),
    ]

    def __init__(self, target: "QLineEdit", parent=None):
        super().__init__(parent)
        self._target = target
        self.setWindowTitle("Format Text…")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumWidth(420)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 10, 12, 10)

        hdr = QLabel("Text:")
        hdr.setStyleSheet("font-weight:bold; font-size:11px;")
        layout.addWidget(hdr)

        self._edit = QLineEdit(self._target.text())
        self._edit.setPlaceholderText("Type or use buttons below to insert § codes…")
        self._edit.setMinimumHeight(28)
        self._edit.textChanged.connect(self._update_preview)
        layout.addWidget(self._edit)

        prev_hdr = QLabel("Preview:")
        prev_hdr.setStyleSheet("font-weight:bold; font-size:10px; margin-top:2px;")
        layout.addWidget(prev_hdr)

        self._preview = _ObfuscatedPreview()
        self._preview.setStyleSheet(
            "border:1px solid #555; border-radius:3px; background:#1a1a1a;"
        )
        layout.addWidget(self._preview)

        col_hdr = QLabel("Colours:")
        col_hdr.setStyleSheet("font-weight:bold; font-size:10px; margin-top:4px;")
        layout.addWidget(col_hdr)

        colour_grid = QWidget()
        cg = QGridLayout(colour_grid)
        cg.setSpacing(3)
        cg.setContentsMargins(0, 0, 0, 0)

        for idx, (code, label, bg, fg) in enumerate(self._COLOURS):
            btn = QPushButton(label)
            btn.setFixedSize(36, 28)
            btn.setToolTip(f"§{code}  ({bg})")
            btn.setStyleSheet(
                f"QPushButton {{ background:{bg}; color:{fg}; "
                f"border:1px solid #555; border-radius:3px; "
                f"font-weight:bold; font-size:12px; }}"
                f"QPushButton:hover {{ border:2px solid #fff; }}"
            )
            btn.clicked.connect(lambda _, c=code: self._insert(c))
            cg.addWidget(btn, idx // 8, idx % 8)

        layout.addWidget(colour_grid)

        style_hdr = QLabel("Styles:")
        style_hdr.setStyleSheet("font-weight:bold; font-size:10px; margin-top:4px;")
        layout.addWidget(style_hdr)

        style_row = QHBoxLayout()
        style_row.setSpacing(4)
        style_row.setContentsMargins(0, 0, 0, 0)

        _style_css = {
            "B": "font-weight:bold;",
            "I": "font-style:italic;",
            "S": "text-decoration:line-through;",
            "U": "text-decoration:underline;",
            "✦": "font-size:11px;",
            "R": "color:#e07b00; font-weight:bold;",
        }

        for code, label, tip in self._STYLES:
            btn = QPushButton(label)
            btn.setFixedSize(38, 28)
            btn.setToolTip(f"§{code}  —  {tip}")
            extra = _style_css.get(label, "")
            btn.setStyleSheet(
                f"QPushButton {{ border:1px solid #666; border-radius:3px; "
                f"background:#2a2a2a; color:#ddd; {extra} }}"
                f"QPushButton:hover {{ background:#3a3a3a; border-color:#aaa; }}"
            )
            btn.clicked.connect(lambda _, c=code: self._insert(c))
            style_row.addWidget(btn)

        style_row.addStretch()
        layout.addLayout(style_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("✖  Cancel")
        btn_ok = QPushButton("✔  OK")
        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self._ok)
        btn_ok.setDefault(True)
        btn_row.addWidget(btn_cancel)
        btn_row.addSpacing(6)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

        self._update_preview(self._edit.text())

    def _insert(self, code: str):
        """Insert §<code> at the current cursor position."""
        cursor_pos = self._edit.cursorPosition()
        text = self._edit.text()
        new_text = text[:cursor_pos] + f"§{code}" + text[cursor_pos:]
        self._edit.setText(new_text)
        self._edit.setCursorPosition(cursor_pos + 2)
        self._edit.setFocus()

    def _update_preview(self, text: str):
        """Parse § codes and hand spans to the preview widget."""
        self._preview.set_spans(self._parse_spans(text))

    @classmethod
    def _parse_spans(cls, text: str) -> list:
        """
        Parse a § formatted string into a list of span dicts:
          {text, colour, bold, italic, strike, under, obfusc}
        Follows Minecraft behaviour: colour codes reset all style flags.
        """
        import re
        parts = re.split(r"(§.)", text)

        cur_colour = "#ffffff"
        bold = italic = strike = under = obfusc = False

        spans = []
        for part in parts:
            if len(part) == 2 and part[0] == "§":
                code = part[1].lower()
                if code in cls._COLOUR_MAP:
                    cur_colour = cls._COLOUR_MAP[code]
                    bold = italic = strike = under = obfusc = False
                elif code == "l": bold   = True
                elif code == "o": italic = True
                elif code == "m": strike = True
                elif code == "n": under  = True
                elif code == "k": obfusc = True
                elif code == "r":
                    cur_colour = "#ffffff"
                    bold = italic = strike = under = obfusc = False
            else:
                if part:
                    spans.append({
                        "text":   part,
                        "colour": cur_colour,
                        "bold":   bold,
                        "italic": italic,
                        "strike": strike,
                        "under":  under,
                        "obfusc": obfusc,
                    })
        return spans

    def _ok(self):
        self._target.setText(self._edit.text())
        self._preview._timer.stop()
        self.accept()

    def reject(self):
        self._preview._timer.stop()
        super().reject()

class ImageOrderDialog(QDialog):

    def __init__(self, images: list, parent=None):
        super().__init__(parent)
        self._images = list(images)
        self.setWindowTitle("Set Loading Background Image Order")
        self.setMinimumSize(520, 560)
        self._build()

    def _build(self):

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(14, 14, 14, 12)

        hdr = QLabel("🖼  Drag to reorder — top = frame 1, bottom = last frame")
        hdr.setStyleSheet("font-weight:bold; font-size:12px;")
        layout.addWidget(hdr)

        sub = QLabel(
            f"Found <b>{len(self._images)}</b> image(s) with non-numeric names. "
            "Arrange them in the desired playback order, then click <b>OK</b>."
        )
        sub.setWordWrap(True)
        sub.setStyleSheet("color:#555; margin-bottom:4px;")
        layout.addWidget(sub)

        self._list = QListWidget()
        self._list.setDragDropMode(QAbstractItemView.InternalMove)
        self._list.setDefaultDropAction(QtCore.Qt.MoveAction)
        self._list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._list.setIconSize(QSize(64, 64))
        self._list.setSpacing(2)
        self._list.setStyleSheet(
            "QListWidget{border:1px solid #aaa; border-radius:4px;}"
            "QListWidget::item{padding:4px; border-bottom:1px solid #eee;}"
            "QListWidget::item:selected{background:#d0e8ff;}"
        )

        for img_path in self._images:
            item = QListWidgetItem()
            item.setText(f"  {img_path.name}")
            item.setData(QtCore.Qt.UserRole, str(img_path))
            try:
                px = QPixmap(str(img_path)).scaled(
                    64, 64,
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation
                )
                item.setIcon(QIcon(px))
            except Exception:
                pass
            self._list.addItem(item)

        layout.addWidget(self._list, stretch=1)

        note = QLabel("💡 Tip: select an item then use ↑ / ↓ buttons to move it.")
        note.setStyleSheet("color:#888; font-size:10px;")
        layout.addWidget(note)

        ud_row = QHBoxLayout()
        btn_up = QPushButton("▲  Move Up")
        btn_dn = QPushButton("▼  Move Down")
        btn_up.clicked.connect(self._move_up)
        btn_dn.clicked.connect(self._move_down)
        ud_row.addWidget(btn_up); ud_row.addWidget(btn_dn); ud_row.addStretch()
        layout.addLayout(ud_row)

        line = QFrame(); line.setFrameShape(QFrame.HLine); line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("✖  Cancel")
        btn_ok = QPushButton("✔  OK — Use This Order")
        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self.accept)
        btn_row.addWidget(btn_cancel); btn_row.addSpacing(6); btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def _move_up(self):
        row = self._list.currentRow()
        if row > 0:
            item = self._list.takeItem(row)
            self._list.insertItem(row - 1, item)
            self._list.setCurrentRow(row - 1)

    def _move_down(self):
        row = self._list.currentRow()
        if row < self._list.count() - 1:
            item = self._list.takeItem(row)
            self._list.insertItem(row + 1, item)
            self._list.setCurrentRow(row + 1)

    def ordered_paths(self) -> list:
        result = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            result.append(Path(item.data(QtCore.Qt.UserRole)))
        return result

class Worker(QtCore.QThread):
    log_signal         = QtCore.pyqtSignal(str)
    done_signal        = QtCore.pyqtSignal(bool, str)
    progress_signal    = QtCore.pyqtSignal(int)
    show_order_dialog  = QtCore.pyqtSignal(list)

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self._stop_requested = False
        self._temp_files = []

    def stop(self):
        self._stop_requested = True

    def log(self, msg: str):
        self.log_signal.emit(str(msg))
        if _IS_DEBUG:
            print(f"[DEBUG] {msg}", flush=True)

    def _success_message(self) -> str:
        return "✅ .mcpack created successfully!"

    def run(self):
        try:
            ok = self.process()
            self.done_signal.emit(True, self._success_message())
        except Exception as e:
            import traceback
            self.log(traceback.format_exc())
            self.done_signal.emit(False, f"❌ Error: {e}")
        finally:
            self._cleanup()

    def _cleanup(self):
        for p in self._temp_files:
            p = Path(p)
            try:
                if p.is_dir():  shutil.rmtree(p, ignore_errors=True)
                elif p.exists(): p.unlink()
            except Exception: pass

    def _ensure_dir(self, p: Path):
        p.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def parse_time(value):
        if not value: return None
        if isinstance(value, (int, float)): return int(value)
        parts = str(value).split(":")
        try: parts = [int(p) for p in parts]
        except ValueError: raise ValueError(f"Invalid time: {value}")
        if len(parts) == 1: return parts[0]
        if len(parts) == 2: return parts[0]*60+parts[1]
        if len(parts) == 3: return parts[0]*3600+parts[1]*60+parts[2]
        raise ValueError(f"Invalid time: {value}")

    def _run_subprocess(self, cmd, **kwargs):
        result = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
        if result.returncode != 0:
            raise RuntimeError(f"Command failed: {' '.join(str(c) for c in cmd)}\n{result.stderr}")
        return result

    def _run_ffmpeg(self, args):
        return self._run_subprocess([_get_ffmpeg_exe()] + args)

    def _monitor_memory(self):
        mem = psutil.virtual_memory()
        if mem.percent > MEMORY_THRESHOLD:
            self.log(f"⚠️ High memory: {mem.percent:.0f}%")

    def _get_ytdlp_cookie_args(self) -> list:
        """
        Return yt-dlp cookie args based on cfg:
        - yt_cookies_file set → --cookies <path>
        - yt_cookies_browser set → export via --cookies-from-browser, then --cookies <tmp>
        - neither → attempt without cookies
        """
        # Direct cookies.txt file takes priority
        cookie_file = self.cfg.get("yt_cookies_file", "").strip()
        if cookie_file and Path(cookie_file).exists():
            self.log(f"Using cookies.txt: {cookie_file}")
            return ["--cookies", cookie_file]

        browser = self.cfg.get("yt_cookies_browser", "").strip().lower()
        if not browser:
            self.log("⚠️ No cookies source specified, attempting without cookies")
            return []

        cookies_txt = Path(tempfile.mkdtemp()) / "cookies.txt"
        self._temp_files.append(cookies_txt.parent)
        self.log(f"Exporting cookies from {browser} → {cookies_txt}")
        try:
            js_args = _get_yt_dlp_js_runtimes_args()
            r = subprocess.run(
                ["yt-dlp", "--cookies-from-browser", browser] + js_args +
                ["--cookies", str(cookies_txt),
                 "--simulate", "--quiet", "--no-warnings",
                 "https://www.youtube.com/"],
                capture_output=True, timeout=30
            )
            if cookies_txt.exists() and cookies_txt.stat().st_size > 0:
                self.log(f"Cookies exported ✓ ({cookies_txt.stat().st_size} bytes)")
                return ["--cookies", str(cookies_txt)]
            else:
                self.log(f"⚠️ Cookie export returned code {r.returncode}, trying --cookies-from-browser directly")
                return ["--cookies-from-browser", browser]
        except Exception as e:
            self.log(f"⚠️ Cookie export failed: {e}, trying --cookies-from-browser directly")
            return ["--cookies-from-browser", browser]

    def _download_youtube(self, url: str, output_dir: Path) -> Path:
        if self._stop_requested: raise RuntimeError("Cancelled.")
        self._ensure_dir(output_dir)
        out_path = output_dir / "input_video.%(ext)s"
        start = self.cfg.get("start_seconds")
        end   = self.cfg.get("end_seconds")
        cookie_args = self._get_ytdlp_cookie_args()
        js_args = _get_yt_dlp_js_runtimes_args()
        cmd = (
            ["yt-dlp"] + cookie_args + js_args + ["--remote-components", "ejs:github"] +
            ["-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
             "--merge-output-format", "mp4", "-o", str(out_path), url]
        )
        if start is not None and end is not None and end > start:
            cmd += ["--download-sections", f"*{start}-{end}"]
            self.cfg["is_trimmed"] = True
        else:
            self.cfg["is_trimmed"] = False
        self.log("Downloading YouTube video...")
        self._run_subprocess(cmd)
        mp4s = list(output_dir.glob("input_video*.mp4"))
        if not mp4s: raise RuntimeError("❌ YouTube download failed.")
        self.log(f"Downloaded → {mp4s[0].name}")
        return mp4s[0]

    def _download_container_bg(self, pack_root: Path):
        if self._stop_requested: raise RuntimeError("Cancelled.")
        dst = pack_root / CONTAINER_BG_DIR
        self._ensure_dir(dst)
        self.log(f"Downloading container background from {CONTAINER_BG_URL}...")
        try:
            r = requests.get(CONTAINER_BG_URL, timeout=60)
            r.raise_for_status()
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp.write(r.content)
                tmp_path = Path(tmp.name)
            with zipfile.ZipFile(tmp_path) as zf:
                zf.extractall(dst)
            tmp_path.unlink()
            self.log(f"Container background extracted → {dst}")
        except Exception as e:
            self.log(f"⚠️ Failed to download container background: {e}")
        # Apply custom container background images (overwrite ZIP defaults)
        self._apply_custom_container_bg(dst)

    def _apply_custom_container_bg(self, dst_dir: Path):
        """Overwrite ZIP-extracted images with any user-supplied custom PIL images."""
        images = self.cfg.get("container_bg_images", {})
        if not images:
            return
        count = 0
        for fname, slot in images.items():
            if not slot:
                continue
            pil_img = slot.get("pil") if isinstance(slot, dict) else slot
            if pil_img is None:
                continue
            out = dst_dir / fname
            try:
                pil_img.save(str(out), "PNG")
                self.log(f"Custom container bg applied: {fname}")
                count += 1
            except Exception as e:
                self.log(f"⚠️ Failed to save custom container bg {fname}: {e}")
        if count:
            self.log(f"✓ {count} custom container background(s) applied")

    def _extract_frames_anim(self, video: Path, pack_root: Path) -> Path:
        if self._stop_requested: raise RuntimeError("Cancelled.")
        dst = pack_root / ANIM_BG_DIR
        if dst.exists(): shutil.rmtree(dst)
        self._ensure_dir(dst)

        n = int(self.cfg.get("anim_frames", MAX_FRAMES))
        out_pattern = dst / f"{FRAME_PREFIX_ANIM}%03d.png"
        self.log(f"Extracting {n} anim frames → {dst}")

        args = ["-y"]
        if not self.cfg.get("is_trimmed"):
            ss = self.cfg.get("start_seconds")
            en = self.cfg.get("end_seconds")
            if ss is not None: args += ["-ss", str(ss)]
            if en is not None and ss is not None: args += ["-t", str(en - ss)]

        fps = self.cfg.get("fps", DEFAULT_FPS)
        args += ["-i", str(video), "-vf", f"fps={fps}", "-frames:v", str(n), str(out_pattern)]
        self._run_ffmpeg(args)
        return dst

    def _gen_black_loading_frame(self, load_dir: Path):
        """Generate a single black 1×1 PNG as the loading background."""
        self._ensure_dir(load_dir)
        black = Image.new("RGB", (1, 1), (0, 0, 0))
        black.save(str(load_dir / "1.png"), "PNG")
        self.log("Loading background: black frame generated ✓")

    def _extract_frames_loading(self, video: Path, pack_root: Path) -> Path:
        if self._stop_requested: raise RuntimeError("Cancelled.")
        dst = pack_root / LOADING_BG_DIR
        if dst.exists(): shutil.rmtree(dst)
        self._ensure_dir(dst)

        n = int(self.cfg.get("load_frames", MAX_FRAMES))
        tmp_pat = dst / "load_%03d.png"
        fps = self.cfg.get("fps", DEFAULT_FPS)

        args = ["-y"]
        if not self.cfg.get("is_trimmed"):
            ss = self.cfg.get("start_seconds")
            en = self.cfg.get("end_seconds")
            if ss is not None: args += ["-ss", str(ss)]
            if en is not None and ss is not None: args += ["-t", str(en - ss)]
        args += ["-i", str(video), "-vf", f"fps={fps}", "-frames:v", str(n), str(tmp_pat)]
        self._run_ffmpeg(args)

        for f in sorted(dst.glob("load_*.png")):
            m = re.match(r"load_(\d+)\.png", f.name)
            if m:
                idx = int(m.group(1))
                f.rename(dst / f"{idx}.png")

        self.log(f"Loading frames extracted → {dst}")
        return dst

    def _make_blur_png(self, anim_dir: Path):
        if self._stop_requested: raise RuntimeError("Cancelled.")
        frames = sorted(anim_dir.glob(f"{FRAME_PREFIX_ANIM}*.png"))
        if not frames:
            raise FileNotFoundError("No animated frames found to create blur.png.")
        src = frames[0]
        blur_out = anim_dir / "blur.png"

        try:
            import cv2
            img = cv2.imread(str(src))
            if img is not None:
                blurred = cv2.GaussianBlur(img, (31, 31), 0)
                cv2.imwrite(str(blur_out), blurred)
                self.log(f"blur.png created via OpenCV → {blur_out}")
                return
        except Exception as e:
            self.log(f"OpenCV blur failed: {e}, falling back to Pillow...")

        im = Image.open(src)
        im.filter(ImageFilter.GaussianBlur(radius=15)).save(blur_out)
        self.log(f"blur.png created via Pillow → {blur_out}")

    def _download_audio(self, video: Path, pack_root: Path):
        if self._stop_requested: raise RuntimeError("Cancelled.")
        bgm_name = re.sub(r'[\\/:*?"<>|]', "_", self.cfg.get("bgm_name", "bgm").strip()) or "bgm"
        sounds_path = pack_root / SOUNDS_DIR / f"{bgm_name}.ogg"
        self._ensure_dir(sounds_path.parent)
        self.log(f"Extracting audio → {sounds_path}")
        self._run_ffmpeg(["-y", "-i", str(video), "-vn", "-acodec", "libvorbis", str(sounds_path)])
        self.log("Audio extracted ✓")

    def _download_youtube_audio(self, url: str, pack_root: Path):
        bgm_name = re.sub(r'[\\/:*?"<>|]', "_", self.cfg.get("bgm_name", "bgm").strip()) or "bgm"
        dst = pack_root / SOUNDS_DIR
        self._ensure_dir(dst)
        out_tmpl = dst / f"{bgm_name}.%(ext)s"
        cookie_args = self._get_ytdlp_cookie_args()
        js_args = _get_yt_dlp_js_runtimes_args()
        cmd = ["yt-dlp"] + cookie_args + js_args + ["--remote-components", "ejs:github"] + ["-x", "--audio-format", "vorbis", "-o", str(out_tmpl), url]
        self._run_subprocess(cmd)
        self.log("YouTube audio downloaded ✓")

    def _copy_bgm_file(self, pack_root: Path):
        if self._stop_requested: raise RuntimeError("Cancelled.")
        bgm_file = self.cfg.get("bgm_file", "").strip()
        if not bgm_file:
            return
        src = Path(bgm_file)
        if not src.exists():
            raise FileNotFoundError(f"BGM file not found: {src}")

        bgm_name = re.sub(r'[\\/:*?"<>|]', "_", src.stem).strip() or "background_music"
        self.cfg["bgm_name"] = bgm_name

        dst_dir = pack_root / SOUNDS_DIR
        self._ensure_dir(dst_dir)
        dst = dst_dir / f"{bgm_name}.ogg"

        if src.suffix.lower() == ".ogg":
            shutil.copy2(src, dst)
            self.log(f"BGM copied: {src.name} → {dst.name}")
        else:
            self.log(f"Converting {src.name} → {dst.name} (Vorbis OGG)...")
            self._run_ffmpeg(["-y", "-i", str(src), "-acodec", "libvorbis", "-q:a", "6", str(dst)])
            self.log("BGM conversion done ✓")

    def _copy_pack_icon(self, pack_root: Path):
        if self._stop_requested: raise RuntimeError("Cancelled.")

        pil_img = self.cfg.get("pack_icon_pil")
        raw_path = self.cfg.get("pack_icon_path", "").strip()

        if pil_img is not None:
            dst = pack_root / "pack_icon.png"
            pil_img.save(str(dst), "PNG")
            self.log(f"pack_icon.png saved (cropped 256×256) → {dst}")
        elif raw_path:
            src = Path(raw_path)
            if not src.exists():
                self.log(f"⚠️ Pack icon not found: {src} — skipping.")
                return
            dst = pack_root / "pack_icon.png"
            shutil.copy2(src, dst)
            self.log(f"pack_icon.png copied → {dst}")
        else:
            self.log("No pack icon specified — skipping.")

    def _gen_bg_anim_json(self, anim_dir: Path, pack_root: Path):
        _ANIM_EXTS = [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tga"]
        frames = []
        for _ext in _ANIM_EXTS:
            frames = sorted(anim_dir.glob(f"{FRAME_PREFIX_ANIM}*{_ext}"))
            if frames:
                break
        n = len(frames)
        if n == 0:
            self.log("⚠️ No anim frames found, skipping .hrzn_public_bg_anim.json")
            return

        lines = []
        lines.append('  "namespace": "hrzn_ui_wextension",')
        lines.append('  "hrzn_ui_settings_bg@core_img": { "texture": "hrzn_animated_background/blur" },')
        lines.append('  "img": { "type": "image", "fill": true, "property_bag": {"#true": "0"}, "bindings": [ { "binding_name": "#collection_index", "binding_type": "collection_details", "binding_collection_name": "animated_background" }, { "binding_type": "view", "source_property_name": "(\'#\' + (#collection_index < 9))", "target_property_name": "#pad00" }, { "binding_type": "view", "source_property_name": "(\'#\' + (#collection_index < 99))", "target_property_name": "#pad0" }, { "binding_type": "view", "source_property_name": "(\'hrzn_animated_background/hans\' + \'_common_\' + #pad00 + #pad0 + (#collection_index + 1))", "target_property_name": "#texture" } ] },')
        lines.append(f'  "hrzn_ui_main_bg": {{ "size": [ "100%", "100%" ], "type": "stack_panel", "anchor_from": "top_left", "anchor_to": "top_left", "offset": "@hrzn_ui_wextension.01", "$duration_per_frame|default": 0.03333333, "$frames|default": {n}, "collection_name": "animated_background", "factory": {{"name": "test", "control_name": "hrzn_ui_wextension.img"}}, "property_bag": {{"#frames": "$frames"}}, "bindings": [ {{ "binding_type": "view", "source_property_name": "(#frames*1)", "target_property_name": "#collection_length" }} ] }},')
        lines.append('  "hans_anim_base": { "destroy_at_end": "@hrzn_ui_wextension.bg_anim", "anim_type": "offset", "easing": "linear", "duration": "$duration_per_frame", "from": "$anm_offset", "to": "$anm_offset" },')
        lines.append('')

        for i in range(1, n + 1):
            key       = f"{i:02d}"
            y_pct     = "0%" if i == 1 else f"-{(i-1)*100}%"
            next_key  = f"{(i % n) + 1:02d}"
            lines.append(f'  "{key}@hrzn_ui_wextension.hans_anim_base":{{"$anm_offset": [ "0px", "{y_pct}" ],"next": "@hrzn_ui_wextension.{next_key}"}},')

        lines[-1] = lines[-1].rstrip(",")

        content = "{\n" + "\n".join(lines) + "\n}"
        out_path = pack_root / ".hrzn_public_bg_anim.json"
        out_path.write_text(content, encoding="utf-8")
        self.log(f".hrzn_public_bg_anim.json generated ({n} frames)")

    def _gen_bg_load_json(self, load_dir: Path, pack_root: Path):
        IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
        all_imgs = [f for f in load_dir.iterdir() if f.suffix.lower() in IMG_EXT]
        frames = sorted(all_imgs, key=lambda p: int(p.stem) if p.stem.isdigit() else 0)
        n = len(frames)
        if n == 0:
            self.log("⚠️ No loading frames found, skipping .hrzn_public_bg_load.json")
            return

        ctrl_lines = []
        for i in range(1, n + 1):
            trailing = "," if i < n else ""
            ctrl_lines.append(f'      {{ "{i}@hrzn_ui_load_wextension.img": {{ "$img": "{i}" }} }}{trailing}')

        anim_lines = []
        for i in range(1, n + 1):
            key      = f"{i:02d}"
            y_pct    = "0%" if i == 1 else f"-{(i-1)*100}%"
            next_key = f"{(i % n) + 1:02d}"
            trailing = "," if i < n else ""
            anim_lines.append(f'  "{key}@hrzn_ui_load_wextension.anim_base":{{"$anm_offset": [ 0, "{y_pct}" ],"next": "@hrzn_ui_load_wextension.{next_key}"}}{trailing}')

        content = """{
  "namespace": "hrzn_ui_load_wextension",

  "anim_base": {
    "anim_type": "offset",
    "easing": "linear",
    "duration": "$duration_loading_per_frame",
    "from": "$anm_offset",
    "to": "$anm_offset"
  },

  "img": {
    "type": "image",
    "fill": true,
    "bilinear": true,
    "size": [ "100%", "100%" ],
    "texture": "('hrzn_loading_background/' + $img )"
  },

  "hans_load_background": {
    "type": "stack_panel",
    "size": [ "100%", "100%" ],
    "anchor_from": "top_left",
    "anchor_to": "top_left",
    "offset": "@hrzn_ui_load_wextension.01",
    "$duration_per_frame|default": 1.5,
    "controls": [
""" + "\n".join(ctrl_lines) + """
    ]
  },
  /*///// FRAMES /////*/
""" + "\n".join(anim_lines) + """
}"""
        out_path = pack_root / ".hrzn_public_bg_load.json"
        out_path.write_text(content, encoding="utf-8")
        self.log(f".hrzn_public_bg_load.json generated ({n} frames)")

    def _pack_display_name(self, ext_name: str) -> str:
        return f"§l§dHorizon§bUI: {ext_name}"

    def _gen_manifest(self, pack_root: Path):
        creator  = self.cfg.get("creator", "Unknown")
        ext_name = self.cfg.get("new_pack_name", "MyExtension")

        ver_x = int(self.cfg.get("ext_ver_x", 201))
        ver_y = int(self.cfg.get("ext_ver_y", 1))
        ver_z = int(self.cfg.get("ext_ver_z", 0))
        version_tuple = [ver_x, ver_y, ver_z]

        desc = (
            f"§lFirst use restart the game!\n"
            f"Original Creator : Han's404 | Youtube: @zxyn404 ( Han's )\n"
            f"Extension Creator : {creator}\n"
            f"Built with TuBeo5866's HorizonUI/NekoUI Extension Studio"
        )

        data = {
            "format_version": 2,
            "header": {
                "description": desc,
                "name": self._pack_display_name(ext_name),
                "uuid": str(uuid.uuid4()),
                "version": version_tuple,
                "min_engine_version": [1, 21, 114]
            },
            "modules": [{
                "description": desc,
                "type": "resources",
                "uuid": str(uuid.uuid4()),
                "version": version_tuple
            }]
        }

        if self.cfg.get("bg_mode") == "both":
            data["subpacks"] = [
                {
                    "folder_name": "static",
                    "name": "Background: Static [ Unanimated§f ]",
                    "memory_tier": 1
                },
                {
                    "folder_name": "dynamic",
                    "name": "Background: Dynamic [ Animated ]",
                    "memory_tier": 1
                }
            ]
            self.log("manifest.json: subpacks (static + dynamic) added ✓")

        out = pack_root / "manifest.json"
        out.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")
        self.log(f"manifest.json generated ✓  (version {ver_x}.{ver_y}.{ver_z})")

    def _gen_global_variables(self, pack_root: Path):
        creator = self.cfg.get("creator", "Unknown")
        ver_x   = int(self.cfg.get("ext_ver_x", 201))
        ver_y   = int(self.cfg.get("ext_ver_y", 1))
        ver_z   = int(self.cfg.get("ext_ver_z", 0))
        content = f"""{{
  /* -------------------------- EXTENSION -------------------------- */
  // To display Extension Version and Extension Creator Name in NekoUI About Settings
  // Default = True

  "$hrzn.ui.use_extension": true,
  "$hrzn.ui.creator_name": "{creator}",
  "$hrzn.ui.extension_version": "{ver_x}.{ver_y}.{ver_z}", // Numbers only!
  "$duration_per_frame": 0.05, // Main Screen UI
  "$duration_loading_per_frame": 2, // Loading Screen UI

  "$horizon_radio_unchecked_color": [1, 1, 1, 0],
  "$horizon_radio_unchecked_hover_color": [1, 1, 1, 0],
  "$horizon_radio_checked_color": [1, 1, 1, 0],
  "$horizon_radio_checked_hover_color": [1, 1, 1, 0],

  "$horizon_slider_step_background_color": [1, 1, 1, 0],
  "$horizon_slider_step_background_hover_color": [1, 1, 1, 0],
  "$horizon_slider_step_progress_progress_color": [1, 1, 1, 0],
  "$horizon_slider_step_progress_progress_hover_color": [1, 1, 1, 0],
  "$horizon_slider_background_color": [1, 1, 1, 0],
  "$horizon_slider_background_hover_color": [1, 1, 1, 0],
  "$horizon_slider_progress_color": [1, 1, 1, 0],
  "$horizon_slider_progress_hover_color": [1, 1, 1, 0],

  "$horizon_slider_slider_border_color": [1, 1, 1, 0],

  "$horizon_toggle_on_hover_color": [1, 1, 1, 0],
  "$horizon_toggle_on_color": [1, 1, 1, 0],
  "$horizon_toggle_off_color": [1, 1, 1, 0],
  "$horizon_toggle_off_hover_color": [1, 1, 1, 0],

  "$light_toggle_default_text_color": [1, 1, 1, 0],
  "$light_toggle_hover_text_color": [1, 1, 1, 0],
  "$light_toggle_checked_hover_text_color": [1, 1, 1, 0],
  "$light_toggle_checked_default_text_color": [1, 1, 1, 0],

  "$hrzn.ui.force_skin": false,

  "$hrzn.ui.do_not_use_viegnette": false

  /* -------------------------- EXTENSION -------------------------- */

}}"""
        ui_dir = pack_root / UI_DIR
        self._ensure_dir(ui_dir)
        (ui_dir / "_global_variables.json").write_text(content, encoding="utf-8")
        self.log("ui/_global_variables.json generated ✓")

    def _gen_music_definitions(self, pack_root: Path):
        content = {
            "menu": {
                "event_name": "music.menu",
                "max_delay": 30,
                "min_delay": 0
            }
        }
        out = pack_root / "sounds" / "music_definitions.json"
        self._ensure_dir(out.parent)
        out.write_text(json.dumps(content, ensure_ascii=False, indent=3), encoding="utf-8")
        self.log("sounds/music_definitions.json generated ✓")

    def _gen_sound_definitions(self, pack_root: Path):
        bgm_name = re.sub(r'[\\/:*?"<>|]', "_", self.cfg.get("bgm_name", "bgm").strip()) or "bgm"
        content = {
            "format_version": "1.20.20",
            "sound_definitions": {
                "music.menu": {
                    "__use_legacy_max_distance": "true",
                    "category": "music",
                    "max_distance": None,
                    "min_distance": None,
                    "sounds": [
                        {
                            "name": f"sounds/music/bgm/{bgm_name}",
                            "stream": True,
                            "volume": 0.30
                        }
                    ]
                }
            }
        }
        out = pack_root / "sounds" / "sound_definitions.json"
        self._ensure_dir(out.parent)
        out.write_text(json.dumps(content, ensure_ascii=False, indent=3), encoding="utf-8")
        self.log("sounds/sound_definitions.json generated ✓")

    def _copy_loading_bg_folder(self, pack_root: Path):
        if self._stop_requested: raise RuntimeError("Cancelled.")
        src_folder = self.cfg.get("loading_bg_folder", "").strip()
        if not src_folder:
            self.log("No Loading Background folder specified, skipping.")
            return

        src = Path(src_folder)
        if not src.is_dir():
            self.log(f"⚠️ Loading BG folder not found: {src}")
            return

        IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
        images = sorted([f for f in src.iterdir() if f.suffix.lower() in IMG_EXT])
        if not images:
            self.log(f"⚠️ No images found in {src}")
            return

        dst = pack_root / LOADING_BG_DIR
        if dst.exists():
            shutil.rmtree(dst)
        dst.mkdir(parents=True, exist_ok=True)

        def _all_numeric(files):
            try:
                nums = [int(f.stem) for f in files]
                return nums
            except ValueError:
                return None

        nums = _all_numeric(images)
        if nums is not None:
            for new_idx, img in enumerate(
                sorted(images, key=lambda f: int(f.stem)), start=1
            ):
                dst_name = dst / f"{new_idx}{img.suffix.lower()}"
                shutil.copy2(img, dst_name)
                self.log(f"Copied {img.name} → {dst_name.name}")
            self.log(f"✓ {len(images)} loading BG images copied (numeric order).")
        else:
            self.log("Loading BG images are not numerically named – requesting order from user...")
            ordered = self._request_image_order(images)
            if ordered is None:
                self.log("⚠️ User cancelled image ordering – loading BG folder not copied.")
                return
            for new_idx, img in enumerate(ordered, start=1):
                dst_name = dst / f"{new_idx}{img.suffix.lower()}"
                shutil.copy2(img, dst_name)
                self.log(f"Copied {img.name} → {dst_name.name}")
            self.log(f"✓ {len(ordered)} loading BG images copied (custom order).")

    _order_request_signal  = QtCore.pyqtSignal(list)
    _order_response_signal = QtCore.pyqtSignal(list)

    def _deliver_order(self, ordered: list):
        self._order_result = ordered
        self._order_event.set()

    def _request_image_order(self, images: list):
        import threading
        self._order_result = None
        self._order_event  = threading.Event()

        self.show_order_dialog.emit([str(p) for p in images])

        self._order_event.wait()

        result = self._order_result
        return result if result else None

    def _extract_frame_static(self, video: "Path", pack_root: "Path") -> "Path":
        if self._stop_requested: raise RuntimeError("Cancelled.")
        dst = pack_root / ANIM_BG_DIR
        if dst.exists(): shutil.rmtree(dst)
        self._ensure_dir(dst)

        out_pattern = dst / f"{FRAME_PREFIX_ANIM}%03d.png"
        self.log(f"Static mode: extracting 1 frame -> {dst}")

        args = ["-y"]
        if not self.cfg.get("is_trimmed"):
            ss = self.cfg.get("start_seconds")
            if ss is not None: args += ["-ss", str(ss)]
        args += ["-i", str(video), "-vf", "fps=1", "-frames:v", "1", str(out_pattern)]
        self._run_ffmpeg(args)
        self.log(f"Static frame extracted -> {dst}")
        return dst

    def _use_image_as_background(self, img_src: "Path", pack_root: "Path") -> "Path":
        if self._stop_requested: raise RuntimeError("Cancelled.")
        dst = pack_root / ANIM_BG_DIR
        if dst.exists(): shutil.rmtree(dst)
        self._ensure_dir(dst)

        out_name = f"{FRAME_PREFIX_ANIM}001.png"
        out_path = dst / out_name

        if img_src.suffix.lower() == ".png":
            shutil.copy2(img_src, out_path)
            self.log(f"Image is already PNG — copied as {out_name}")
        else:
            self.log(f"Converting {img_src.name} → PNG…")
            img = Image.open(str(img_src)).convert("RGBA")
            img.save(str(out_path), "PNG")
            self.log(f"Converted {img_src.name} → {out_name}")

        return dst

    def _make_blur_png_for_dir(self, anim_dir: "Path"):
        if self._stop_requested: raise RuntimeError("Cancelled.")
        frames = sorted(anim_dir.glob(f"{FRAME_PREFIX_ANIM}*.png"))
        if not frames:
            raise FileNotFoundError(f"No frames in {anim_dir} to create blur.png.")
        src = frames[0]
        blur_out = anim_dir / "blur.png"
        try:
            import cv2
            img = cv2.imread(str(src))
            if img is not None:
                blurred = cv2.GaussianBlur(img, (31, 31), 0)
                cv2.imwrite(str(blur_out), blurred)
                self.log(f"blur.png created via OpenCV -> {blur_out}")
                return
        except Exception as e:
            self.log(f"OpenCV blur failed: {e}, falling back to Pillow...")
        im = Image.open(src)
        im.filter(ImageFilter.GaussianBlur(radius=15)).save(blur_out)
        self.log(f"blur.png created via Pillow -> {blur_out}")

    def _gen_bg_anim_json_for_dir(self, anim_dir: "Path", dest_root: "Path"):
        _ANIM_EXTS = [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tga"]
        frames = []
        for _ext in _ANIM_EXTS:
            frames = sorted(anim_dir.glob(f"{FRAME_PREFIX_ANIM}*{_ext}"))
            if frames:
                break
        n = len(frames)
        if n == 0:
            self.log(f"No frames in {anim_dir} - skipping .hrzn_public_bg_anim.json")
            return

        lines = []
        lines.append('  "namespace": "hrzn_ui_wextension",')
        lines.append('  "hrzn_ui_settings_bg@core_img": { "texture": "hrzn_animated_background/blur" },')
        lines.append('  "img": { "type": "image", "fill": true, "property_bag": {"#true": "0"}, "bindings": [ { "binding_name": "#collection_index", "binding_type": "collection_details", "binding_collection_name": "animated_background" }, { "binding_type": "view", "source_property_name": "(\'#\' + (#collection_index < 9))", "target_property_name": "#pad00" }, { "binding_type": "view", "source_property_name": "(\'#\' + (#collection_index < 99))", "target_property_name": "#pad0" }, { "binding_type": "view", "source_property_name": "(\'hrzn_animated_background/hans\' + \'_common_\' + #pad00 + #pad0 + (#collection_index + 1))", "target_property_name": "#texture" } ] },')
        lines.append(f'  "hrzn_ui_main_bg": {{ "size": [ "100%", "100%" ], "type": "stack_panel", "anchor_from": "top_left", "anchor_to": "top_left", "offset": "@hrzn_ui_wextension.01", "$duration_per_frame|default": 0.03333333, "$frames|default": {n}, "collection_name": "animated_background", "factory": {{"name": "test", "control_name": "hrzn_ui_wextension.img"}}, "property_bag": {{"#frames": "$frames"}}, "bindings": [ {{ "binding_type": "view", "source_property_name": "(#frames*1)", "target_property_name": "#collection_length" }} ] }},')
        lines.append('  "hans_anim_base": { "destroy_at_end": "@hrzn_ui_wextension.bg_anim", "anim_type": "offset", "easing": "linear", "duration": "$duration_per_frame", "from": "$anm_offset", "to": "$anm_offset" },')
        lines.append('')

        for i in range(1, n + 1):
            key      = f"{i:02d}"
            y_pct    = "0%" if i == 1 else f"-{(i-1)*100}%"
            next_key = f"{(i % n) + 1:02d}"
            lines.append(f'  "{key}@hrzn_ui_wextension.hans_anim_base":{{"$anm_offset": [ "0px", "{y_pct}" ],"next": "@hrzn_ui_wextension.{next_key}"}},')

        lines[-1] = lines[-1].rstrip(",")
        content = "{\n" + "\n".join(lines) + "\n}"
        out_path = dest_root / ".hrzn_public_bg_anim.json"
        out_path.write_text(content, encoding="utf-8")
        self.log(f".hrzn_public_bg_anim.json generated ({n} frame(s)) -> {out_path}")

    def _build_both_subpacks(self, video: "Path", pack_root: "Path") -> "Path":
        if self._stop_requested: raise RuntimeError("Cancelled.")

        anim_dir = self._extract_frames_anim(video, pack_root)

        static_anim_dir = pack_root / "subpacks" / "static" / ANIM_BG_DIR
        self._ensure_dir(static_anim_dir)

        frames = sorted(anim_dir.glob(f"{FRAME_PREFIX_ANIM}*.png"))
        if not frames:
            self.log("No anim frames found - skipping static subpack.")
            return anim_dir

        first_frame = frames[0]
        shutil.copy2(first_frame, static_anim_dir / first_frame.name)
        self.log(f"Static subpack: copied {first_frame.name} -> {static_anim_dir}")

        self._make_blur_png_for_dir(static_anim_dir)

        static_root = pack_root / "subpacks" / "static"
        self._gen_bg_anim_json_for_dir(static_anim_dir, static_root)

        self.log("Both mode: dynamic + static subpack prepared")
        return anim_dir

    def _get_compressor(self, method: str):
        m = {
            "tinypng": TinyPNGCompressor, "imagecompressr": ImageCompressrCompressor,
            "pillow": PillowCompressor, "ffmpeg": FFmpegCompressor,
            "kraken": KrakenCompressor, "imagekit": ImageKitCompressor,
            "cloudinary": CloudinaryCompressor, "compressor": CompressorIoCompressor,
            "lossless": LosslessCompressor, "none": LosslessCompressor,
        }
        cls = m.get(method.lower())
        return cls(self.cfg, self.log) if cls else None

    def process(self):
        self._monitor_memory()
        total_steps = 15
        step = [0]

        def tick(label=""):
            step[0] += 1
            pct = int(step[0] / total_steps * 100)
            self.progress_signal.emit(pct)
            if label: self.log(f"[{step[0]}/{total_steps}] {label}")

        output_folder = Path(self.cfg["output_folder"]).resolve()
        self._ensure_dir(output_folder)
        ext_name = self.cfg["new_pack_name"].strip()
        pack_root = output_folder / ext_name
        if pack_root.exists(): shutil.rmtree(pack_root)
        self._ensure_dir(pack_root)
        self._temp_files.append(pack_root)
        tick("Pack folder created")

        for d in [ANIM_BG_DIR, LOADING_BG_DIR, CONTAINER_BG_DIR,
                  SOUNDS_DIR, UI_DIR]:
            self._ensure_dir(pack_root / d)
        tick("Folder structure created")

        video_input = self.cfg["video_path"]
        source_is_image = self.cfg.get("source_is_image", False)
        delete_after = False

        if source_is_image:
            img_src = Path(video_input).resolve()
            if not img_src.exists():
                raise FileNotFoundError(f"Image not found: {img_src}")
            video = None
            tick("Image source ready")

            anim_dir = self._use_image_as_background(img_src, pack_root)
            tick("Image placed as background frame")

            if self.cfg.get("loading_bg_folder", "").strip():
                self._copy_loading_bg_folder(pack_root)
                load_dir = pack_root / LOADING_BG_DIR
                tick("Loading background images copied from folder")
            else:
                load_dir = pack_root / LOADING_BG_DIR
                self._ensure_dir(load_dir)
                src_frame = anim_dir / f"{FRAME_PREFIX_ANIM}001.png"
                shutil.copy2(src_frame, load_dir / "1.png")
                self.log(f"Image mode: using bg image as loading frame")
                tick("Loading background frame set from image")

        else:
            if re.match(r"^https?://(www\.)?(youtube\.com|youtu\.be)/", video_input):
                self.cfg["is_trimmed"] = False
                video = self._download_youtube(video_input, output_folder / "_tmp_yt")
                self._temp_files.append(video.parent)
                delete_after = True
            else:
                video = Path(video_input).resolve()
                if not video.exists():
                    raise FileNotFoundError(f"Video not found: {video}")
                self.cfg["is_trimmed"] = False
            tick("Video ready")

            bg_mode = self.cfg.get("bg_mode", "dynamic")
            self.log(f"Background mode: {bg_mode}")

            if bg_mode == "static":
                anim_dir = self._extract_frame_static(video, pack_root)
                tick("Static background frame extracted")
            elif bg_mode == "both":
                anim_dir = self._build_both_subpacks(video, pack_root)
                tick("Dynamic + static subpack frames prepared")
            else:
                anim_dir = self._extract_frames_anim(video, pack_root)
                tick("Animated background frames extracted")

            if self.cfg.get("loading_bg_folder", "").strip():
                self._copy_loading_bg_folder(pack_root)
                load_dir = pack_root / LOADING_BG_DIR
                tick("Loading background images copied from folder")
            elif self.cfg.get("use_black_loading"):
                load_dir = pack_root / LOADING_BG_DIR
                self._gen_black_loading_frame(load_dir)
                tick("Loading background: black frame")
            else:
                load_dir = self._extract_frames_loading(video, pack_root)
                tick("Loading background frames extracted")

        self._make_blur_png_for_dir(anim_dir)
        tick("blur.png created")

        method = self.cfg.get("compress_method", "lossless").lower()
        compressor = self._get_compressor(method)
        if compressor:
            self.log(f"Compressing anim frames via {method}...")
            compressor.compress(anim_dir)
        tick("Anim frames compressed")

        if compressor:
            self.log(f"Compressing loading frames via {method}...")
            compressor.compress(load_dir)
        tick("Loading frames compressed")

        self._download_container_bg(pack_root)
        tick("Container background downloaded")

        if self.cfg.get("bgm_file", "").strip():
            self._copy_bgm_file(pack_root)
        elif re.match(r"^https?://(www\.)?(youtube\.com|youtu\.be)/", video_input):
            self._download_youtube_audio(video_input, pack_root)
        else:
            self._download_audio(video, pack_root)
        tick("Audio prepared")

        self._copy_pack_icon(pack_root)
        tick("Pack icon copied")

        self._gen_bg_anim_json(anim_dir, pack_root)
        self._gen_bg_load_json(load_dir, pack_root)
        self._gen_manifest(pack_root)
        self._gen_global_variables(pack_root)
        self._gen_music_definitions(pack_root)
        self._gen_sound_definitions(pack_root)
        tick("JSON files generated")

        zip_base = output_folder / (ext_name + ".mcpack")
        if zip_base.exists(): zip_base.unlink()
        self.log(f"Packing → {zip_base}")
        shutil.make_archive(str(zip_base.with_suffix("")), "zip", pack_root)
        zip_tmp = zip_base.with_suffix(".zip")
        if zip_tmp.exists(): zip_tmp.rename(zip_base)
        tick("mcpack created")

        shutil.rmtree(pack_root, ignore_errors=True)
        self._temp_files.remove(pack_root)
        if delete_after:
            shutil.rmtree(video.parent, ignore_errors=True)
        tick("Cleanup done")

        self.log(f"\n✅ Done! Output: {zip_base}")
        self.progress_signal.emit(100)
        return True

# ══════════════════════════════════════════════════════════════════════════════
# AnnouncementBanner — NEW CLASS
# Fetches banner.txt from the remote URL and displays it as a dismissible
# top bar spanning the full width of the main window.
# ══════════════════════════════════════════════════════════════════════════════

class NekoWorker(Worker):
    """
    Subclass of Worker that builds NekoUI-format mcpacks instead of HorizonUI.

    Directory structure produced:
        <pack_root>/
        ├── .hans_common_files/
        │   ├── hans_animated_background.json
        │   └── hans_loading_background.json
        ├── neko_ui_public_animated_background/
        ├── neko_ui_public_container_background/
        ├── neko_ui_public_loading_background/
        ├── sounds/music/background music/  (bgm.ogg)
        ├── subpacks/
        │   ├── dynamic/
        │   └── static/
        │       ├── .hans_common_files/
        │       └── neko_ui_public_animated_background/
        ├── ui/
        │   ├── _ui_defs.json
        │   └── _global_variables.json
        ├── sounds/sound_definitions.json
        └── manifest.json
    """

    # NekoUI directory names
    NEKO_ANIM_BG_DIR      = "neko_ui_public_animated_background"
    NEKO_LOADING_BG_DIR   = "neko_ui_public_loading_background"
    NEKO_CONTAINER_BG_DIR = "neko_ui_public_container_background"
    NEKO_COMMON_DIR       = ".hans_common_files"
    NEKO_SOUNDS_DIR       = "sounds/music/background music"

    NEKO_CONTAINER_BG_URL = "https://tubeo5866.github.io/files/hrzn_container_background.zip"

    def _pack_display_name(self, ext_name: str) -> str:
        return f"§l§eNeko§bUI: {ext_name}"

    # ── helpers ───────────────────────────────────────────────────────────────

    def _neko_extract_frames_anim(self, video: Path, pack_root: Path) -> Path:
        if self._stop_requested: raise RuntimeError("Cancelled.")
        dst = pack_root / self.NEKO_ANIM_BG_DIR
        if dst.exists(): shutil.rmtree(dst)
        self._ensure_dir(dst)
        n = int(self.cfg.get("anim_frames", MAX_FRAMES))
        out_pattern = dst / f"{FRAME_PREFIX_ANIM}%03d.png"
        self.log(f"[NekoUI] Extracting {n} anim frames → {dst}")
        args = ["-y"]
        if not self.cfg.get("is_trimmed"):
            ss = self.cfg.get("start_seconds")
            en = self.cfg.get("end_seconds")
            if ss is not None: args += ["-ss", str(ss)]
            if en is not None and ss is not None: args += ["-t", str(en - ss)]
        fps = self.cfg.get("fps", DEFAULT_FPS)
        args += ["-i", str(video), "-vf", f"fps={fps}", "-frames:v", str(n), str(out_pattern)]
        self._run_ffmpeg(args)
        return dst

    def _neko_extract_frames_loading(self, video: Path, pack_root: Path) -> Path:
        if self._stop_requested: raise RuntimeError("Cancelled.")
        dst = pack_root / self.NEKO_LOADING_BG_DIR
        if dst.exists(): shutil.rmtree(dst)
        self._ensure_dir(dst)
        n = int(self.cfg.get("load_frames", MAX_FRAMES))
        tmp_pat = dst / "load_%03d.png"
        fps = self.cfg.get("fps", DEFAULT_FPS)
        args = ["-y"]
        if not self.cfg.get("is_trimmed"):
            ss = self.cfg.get("start_seconds")
            en = self.cfg.get("end_seconds")
            if ss is not None: args += ["-ss", str(ss)]
            if en is not None and ss is not None: args += ["-t", str(en - ss)]
        args += ["-i", str(video), "-vf", f"fps={fps}", "-frames:v", str(n), str(tmp_pat)]
        self._run_ffmpeg(args)
        for f in sorted(dst.glob("load_*.png")):
            m = re.match(r"load_(\d+)\.png", f.name)
            if m:
                f.rename(dst / f"{int(m.group(1))}.png")
        self.log(f"[NekoUI] Loading frames extracted → {dst}")
        return dst

    def _neko_extract_frame_static(self, video: Path, pack_root: Path) -> Path:
        if self._stop_requested: raise RuntimeError("Cancelled.")
        dst = pack_root / self.NEKO_ANIM_BG_DIR
        if dst.exists(): shutil.rmtree(dst)
        self._ensure_dir(dst)
        out_pattern = dst / f"{FRAME_PREFIX_ANIM}%03d.png"
        self.log(f"[NekoUI] Static mode: extracting 1 frame → {dst}")
        args = ["-y"]
        if not self.cfg.get("is_trimmed"):
            ss = self.cfg.get("start_seconds")
            if ss is not None: args += ["-ss", str(ss)]
        args += ["-i", str(video), "-vf", "fps=1", "-frames:v", "1", str(out_pattern)]
        self._run_ffmpeg(args)
        return dst

    def _neko_use_image_as_background(self, img_src: Path, pack_root: Path) -> Path:
        if self._stop_requested: raise RuntimeError("Cancelled.")
        dst = pack_root / self.NEKO_ANIM_BG_DIR
        if dst.exists(): shutil.rmtree(dst)
        self._ensure_dir(dst)
        out_path = dst / f"{FRAME_PREFIX_ANIM}001.png"
        if img_src.suffix.lower() == ".png":
            shutil.copy2(img_src, out_path)
            self.log(f"[NekoUI] Image is already PNG — copied as {out_path.name}")
        else:
            self.log(f"[NekoUI] Converting {img_src.name} → PNG…")
            Image.open(str(img_src)).convert("RGBA").save(str(out_path), "PNG")
        return dst

    def _neko_copy_loading_bg_folder(self, pack_root: Path) -> Path:
        src_folder = self.cfg.get("loading_bg_folder", "").strip()
        dst = pack_root / self.NEKO_LOADING_BG_DIR
        self._ensure_dir(dst)
        if not src_folder:
            return dst
        src = Path(src_folder)
        if not src.is_dir():
            self.log(f"⚠️ [NekoUI] Loading BG folder not found: {src}")
            return dst
        IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
        images = sorted([f for f in src.iterdir() if f.suffix.lower() in IMG_EXT])
        if not images:
            return dst
        try:
            nums = [int(f.stem) for f in images]
            for new_idx, img in enumerate(
                sorted(images, key=lambda f: int(f.stem)), start=1
            ):
                shutil.copy2(img, dst / f"{new_idx}{img.suffix.lower()}")
            self.log(f"[NekoUI] ✓ {len(images)} loading BG images copied (numeric order).")
        except ValueError:
            self.log("[NekoUI] Loading BG images are not numerically named – requesting order from user...")
            ordered = self._request_image_order(images)
            if ordered is None:
                self.log("[NekoUI] ⚠️ User cancelled image ordering.")
                return dst
            for new_idx, img in enumerate(ordered, start=1):
                shutil.copy2(img, dst / f"{new_idx}{img.suffix.lower()}")
            self.log(f"[NekoUI] ✓ {len(ordered)} loading BG images copied (custom order).")
        return dst

    def _neko_download_container_bg(self, pack_root: Path):
        if self._stop_requested: raise RuntimeError("Cancelled.")
        dst = pack_root / self.NEKO_CONTAINER_BG_DIR
        self._ensure_dir(dst)
        self.log(f"[NekoUI] Downloading container background...")
        try:
            r = requests.get(self.NEKO_CONTAINER_BG_URL, timeout=60)
            r.raise_for_status()
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp.write(r.content)
                tmp_path = Path(tmp.name)
            with zipfile.ZipFile(tmp_path) as zf:
                zf.extractall(dst)
            tmp_path.unlink()
            self.log(f"[NekoUI] Container background extracted → {dst}")
        except Exception as e:
            self.log(f"⚠️ [NekoUI] Failed to download container background: {e}")
        self._apply_custom_container_bg(dst)

    def _neko_copy_bgm(self, pack_root: Path):
        if self._stop_requested: raise RuntimeError("Cancelled.")
        bgm_file = self.cfg.get("bgm_file", "").strip()
        if not bgm_file:
            return
        src = Path(bgm_file)
        if not src.exists():
            raise FileNotFoundError(f"BGM file not found: {src}")
        dst_dir = pack_root / self.NEKO_SOUNDS_DIR
        self._ensure_dir(dst_dir)
        dst = dst_dir / "bgm1.ogg"
        if src.suffix.lower() == ".ogg":
            shutil.copy2(src, dst)
            self.log(f"[NekoUI] BGM copied → bgm1.ogg")
        else:
            self.log(f"[NekoUI] Converting {src.name} → bgm1.ogg (Vorbis OGG)…")
            self._run_ffmpeg(["-y", "-i", str(src), "-acodec", "libvorbis", "-q:a", "6", str(dst)])
            self.log("[NekoUI] BGM conversion done ✓")

    def _neko_download_audio(self, video: Path, pack_root: Path):
        if self._stop_requested: raise RuntimeError("Cancelled.")
        dst_dir = pack_root / self.NEKO_SOUNDS_DIR
        self._ensure_dir(dst_dir)
        dst = dst_dir / "bgm1.ogg"
        self.log(f"[NekoUI] Extracting audio → {dst}")
        self._run_ffmpeg(["-y", "-i", str(video), "-vn", "-acodec", "libvorbis", str(dst)])
        self.log("[NekoUI] Audio extracted ✓")

    def _neko_download_youtube_audio(self, url: str, pack_root: Path):
        dst_dir = pack_root / self.NEKO_SOUNDS_DIR
        self._ensure_dir(dst_dir)
        out_tmpl = dst_dir / "bgm1.%(ext)s"
        cookie_args = self._get_ytdlp_cookie_args()
        js_args = _get_yt_dlp_js_runtimes_args()
        cmd = ["yt-dlp"] + cookie_args + js_args + ["--remote-components", "ejs:github"] + ["-x", "--audio-format", "vorbis", "-o", str(out_tmpl), url]
        self._run_subprocess(cmd)
        self.log("[NekoUI] YouTube audio downloaded ✓")

    def _neko_make_blur(self, anim_dir: Path):
        self._make_blur_png_for_dir(anim_dir)

    # ── JSON generators ───────────────────────────────────────────────────────

    def _neko_gen_hans_animated_background(self, anim_dir: Path, common_dir: Path):
        """Generate hans_animated_background.json in .hans_common_files/"""
        _ANIM_EXTS = [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tga"]
        frames = []
        for ext in _ANIM_EXTS:
            frames = sorted(anim_dir.glob(f"{FRAME_PREFIX_ANIM}*{ext}"))
            if frames: break
        n = len(frames)
        if n == 0:
            self.log("[NekoUI] ⚠️ No anim frames – skipping hans_animated_background.json")
            return

        dur = round(1.0 / max(self.cfg.get("fps", DEFAULT_FPS), 1), 9)

        lines = []
        lines.append('  "namespace": "hans_animated_background",')
        lines.append('  "core_img": { "type": "image","fill": true,"layer": 1 },')
        lines.append('  "blur@core_img": { "texture": "neko_ui_public_animated_background/blur" },')
        lines.append(
            '  "viewgnette_effect": { "type": "panel", "controls": "$hans_viewgnette_effect",'
            ' "bindings": [ { "binding_type": "view", "source_control_name": "nekoui_hidegui",'
            ' "source_property_name": "( not #toggle_state )", "target_property_name": "#visible" } ],'
            ' "variables": [ { "requires": "$win10_edition",'
            ' "$hans_viewgnette_effect": [ { "vieg_windows@core_img": { "texture": ".hans_common_files/vieg_win" }}] },'
            ' { "requires": "( not $win10_edition )",'
            ' "$hans_viewgnette_effect": [ { "vieg_windows@core_img": { "texture": ".hans_common_files/vieg" }}] } ] },'
        )
        lines.append(
            '  "img": { "type": "image", "fill": true, "property_bag": {"#true": "0"},'
            ' "bindings": [ { "binding_name": "#collection_index", "binding_type": "collection_details",'
            ' "binding_collection_name": "animated_background" },'
            ' { "binding_type": "view", "source_property_name": "(\'#\' + (#collection_index < 9))", "target_property_name": "#pad00" },'
            ' { "binding_type": "view", "source_property_name": "(\'#\' + (#collection_index < 99))", "target_property_name": "#pad0" },'
            ' { "binding_type": "view",'
            ' "source_property_name": "(\'neko_ui_public_animated_background/hans\' + \'_common_\' + #pad00 + #pad0 + (#collection_index + 1))",'
            ' "target_property_name": "#texture" } ] },'
        )
        lines.append(
            '  "bg_anim": { "type": "panel", "size": [ "100%", "100%" ],'
            ' "controls": [ { "viewgnette_effect@hans_animated_background.viewgnette_effect": {} },'
            ' { "bg_anim_b@hans_animated_background.bg_anim_b": {} } ] },'
        )
        lines.append(
            f'  "bg_anim_b": {{ "size": [ "100%", "100%" ], "type": "stack_panel",'
            f' "anchor_from": "top_left", "anchor_to": "top_left", "offset": "@hans_animated_background.01",'
            f' "$duration_per_frame|default": {dur}, "$frames|default": {n},'
            f' "collection_name": "animated_background",'
            f' "factory": {{"name": "test", "control_name": "hans_animated_background.img"}},'
            f' "property_bag": {{"#frames": "$frames"}},'
            f' "bindings": [ {{ "binding_type": "view", "source_property_name": "(#frames*1)",'
            f' "target_property_name": "#collection_length" }} ] }},'
        )
        lines.append(
            '  "hans_anim_base": { "destroy_at_end": "@hans_animated_background.bg_anim",'
            ' "anim_type": "offset", "easing": "linear",'
            ' "duration": "$duration_per_frame", "from": "$anm_offset", "to": "$anm_offset" },'
        )
        lines.append('')

        for i in range(1, n + 1):
            key      = f"{i:02d}"
            y_pct    = "0%" if i == 1 else f"-{(i-1)*100}%"
            next_key = f"{(i % n) + 1:02d}"
            trailing = "," if i < n else ""
            lines.append(
                f'  "{key}@hans_animated_background.hans_anim_base":'
                f'{{"$anm_offset": [ "0px", "{y_pct}" ],"next": "@hans_animated_background.{next_key}"}}{trailing}'
            )

        content = "{\n" + "\n".join(lines) + "\n}"
        out = common_dir / "hans_animated_background.json"
        out.write_text(content, encoding="utf-8")
        self.log(f"[NekoUI] hans_animated_background.json generated ({n} frames) → {out}")

    def _neko_gen_hans_loading_background(self, load_dir: Path, common_dir: Path):
        """Generate hans_loading_background.json in .hans_common_files/"""
        IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
        all_imgs = [f for f in load_dir.iterdir() if f.suffix.lower() in IMG_EXT]
        frames = sorted(all_imgs, key=lambda p: int(p.stem) if p.stem.isdigit() else 0)
        n = len(frames)
        if n == 0:
            self.log("[NekoUI] ⚠️ No loading frames – skipping hans_loading_background.json")
            return

        ctrl_lines = []
        for i in range(1, n + 1):
            trailing = "," if i < n else ""
            ctrl_lines.append(f'      {{ "{i}@bgl_animations.img": {{ "$img": "{i}" }} }}{trailing}')

        anim_lines = []
        for i in range(1, n + 1):
            key      = f"{i:02d}"
            y_pct    = "0%" if i == 1 else f"-{(i-1)*100}%"
            next_key = f"{(i % n) + 1:02d}"
            trailing = "," if i < n else ""
            anim_lines.append(
                f'  "{key}@bgl_animations.anim_base":'
                f'{{"$anm_offset": [ 0, "{y_pct}" ],"next": "@bgl_animations.{next_key}"}}{trailing}'
            )

        content = """{
  "namespace": "bgl_animations",
  "anim_base": {
    "anim_type": "offset",
    "easing": "linear",
    "duration": "$duration_per_frame",
    "from": "$anm_offset",
    "to": "$anm_offset"
  },
  "img": {
    "type": "image",
    "fill": true,
    "bilinear": true,
    "size": [ "100%", "100%" ],
    "texture": "('neko_ui_public_loading_background/' + $img )"
  },
  "bg_anim": {
    "type": "stack_panel",
    "size": [ "100%", "100%" ],
    "anchor_from": "top_left",
    "anchor_to": "top_left",
    "offset": "@bgl_animations.01",
    "$duration_per_frame|default": 1.5,
    "controls": [
""" + "\n".join(ctrl_lines) + """
    ]
  },
  /*///// FRAMES /////*/
""" + "\n".join(anim_lines) + """
}"""
        out = common_dir / "hans_loading_background.json"
        out.write_text(content, encoding="utf-8")
        self.log(f"[NekoUI] hans_loading_background.json generated ({n} frames) → {out}")

    def _neko_gen_sound_definitions(self, pack_root: Path):
        content = """{
  "music.menu": {
    "category": "music",
    "sounds": [
      {
        "name": "sounds/music/background music/bgm1",
        "stream": true,
        "volume": 0.3
      }
    ]
  }
}"""
        out = pack_root / "sounds" / "sound_definitions.json"
        self._ensure_dir(out.parent)
        out.write_text(content, encoding="utf-8")
        self.log("[NekoUI] sounds/sound_definitions.json generated ✓")

    def _neko_gen_sub_backgrounds(self, common_dir: Path):
        """Generate the sub_backgrounds UI definition JSON in .hans_common_files/"""
        content = """{
    "namespace": "hans_sub_backgrounds",

    "common_panel": { "type": "panel" },
    "common_image": { "type": "image", "texture": "( 'neko_ui_public_container_background/' + $neko_container_bg )", "$neko_container_bg|default": "default" },

    "horse_screen@hans_sub_backgrounds.common_image": {"$neko_container_bg": "horse_screen"},
    "hans_anvil_screen@hans_sub_backgrounds.common_image": {"$neko_container_bg": "cartography_screen"},
    "loom_screen@hans_sub_backgrounds.common_image": {"$neko_container_bg": "loom_screen"},
    "cartography_screen@hans_sub_backgrounds.common_image": {"$neko_container_bg": "anvil_screen"},
    "hans_chest_background@hans_sub_backgrounds.common_image": {"$neko_container_bg": "chest_background"},
    "hans_chest_background_large@hans_sub_backgrounds.common_image": {"$neko_container_bg": "chest_background_large"},
    "hans_enchanting_screen@hans_sub_backgrounds.common_image": {"$neko_container_bg": "enchanting_screen"},
    "hans_furnace_background@hans_sub_backgrounds.common_image": {"$neko_container_bg": "furnace_background"},
    "hans_grindstone_screen@hans_sub_backgrounds.common_image": {"$neko_container_bg": "grindstone_screen"},
    "hans_inventory_background@hans_sub_backgrounds.common_image": {"$neko_container_bg": "inventory_background"},
    "hans_smithing_table@hans_sub_backgrounds.common_image": {"$neko_container_bg": "smithing_table"},
    "hans_stone_cutter_screen@hans_sub_backgrounds.common_image": {"$neko_container_bg": "stone_cutter_screen"},
    "hans_brewing_screen@hans_sub_backgrounds.common_image": {"$neko_container_bg": "brewing_screen"},
    "hans_beacon_screen@hans_sub_backgrounds.common_image": {"$neko_container_bg": "beacon_screen"},
    "hans_common_redstone_screen@hans_sub_backgrounds.common_image": {"$neko_container_bg": "redstone_screen_common"}
}"""
        out = common_dir / "sub_backgrounds.json"
        out.write_text(content, encoding="utf-8")
        self.log("[NekoUI] .hans_common_files/sub_backgrounds.json generated ✓")

    def _neko_gen_ui_defs(self, pack_root: Path):
        content = """{
    "ui_defs": [
        ".hans_common_files/hans_animated_background.json",
        ".hans_common_files/hans_loading_background.json"
    ]
}"""
        ui_dir = pack_root / UI_DIR
        self._ensure_dir(ui_dir)
        (ui_dir / "_ui_defs.json").write_text(content, encoding="utf-8")
        self.log("[NekoUI] ui/_ui_defs.json generated ✓")

    def _neko_gen_global_variables(self, pack_root: Path):
        creator  = self.cfg.get("creator", "Unknown")
        ver_x    = int(self.cfg.get("ext_ver_x", 201))
        ver_y    = int(self.cfg.get("ext_ver_y", 1))
        ver_z    = int(self.cfg.get("ext_ver_z", 0))
        ext_name = self.cfg.get("new_pack_name", "MyExtension")
        content = f"""{{
  /* -------------------------- EXTENSION -------------------------- */
  // To display Extension Version and Extension Creator Name in NekoUI About Settings
  // Default = True

  "$neko_ui_use_extension": true,
  "$neko_ui_extension_version": "{ext_name}",
  "$neko_ui_extension_creator_name": "{creator}"

  /* -------------------------- EXTENSION -------------------------- */
}}"""
        ui_dir = pack_root / UI_DIR
        self._ensure_dir(ui_dir)
        (ui_dir / "_global_variables.json").write_text(content, encoding="utf-8")
        self.log("[NekoUI] ui/_global_variables.json generated ✓")

    def _neko_gen_static_anim_bg_json(self, static_anim_dir: Path, static_root: Path):
        """Generate hans_animated_background.json for the static subpack."""
        common_dir = static_root / self.NEKO_COMMON_DIR
        self._ensure_dir(common_dir)
        self._neko_gen_hans_animated_background(static_anim_dir, common_dir)

    def _neko_build_both_subpacks(self, video: Path, pack_root: Path) -> Path:
        if self._stop_requested: raise RuntimeError("Cancelled.")

        anim_dir = self._neko_extract_frames_anim(video, pack_root)

        static_anim_dir = pack_root / "subpacks" / "static" / self.NEKO_ANIM_BG_DIR
        self._ensure_dir(static_anim_dir)

        # Copy first frame into static subpack
        frames = sorted(anim_dir.glob(f"{FRAME_PREFIX_ANIM}*.png"))
        if not frames:
            self.log("[NekoUI] No anim frames found - skipping static subpack.")
            return anim_dir

        first_frame = frames[0]
        shutil.copy2(first_frame, static_anim_dir / first_frame.name)
        self.log(f"[NekoUI] Static subpack: copied {first_frame.name} → {static_anim_dir}")

        self._make_blur_png_for_dir(static_anim_dir)

        static_root = pack_root / "subpacks" / "static"
        self._neko_gen_static_anim_bg_json(static_anim_dir, static_root)

        self.log("[NekoUI] Both mode: dynamic + static subpack prepared")
        return anim_dir

    # ── main process override ─────────────────────────────────────────────────

    def process(self):
        self._monitor_memory()
        total_steps = 15
        step = [0]

        def tick(label=""):
            step[0] += 1
            pct = int(step[0] / total_steps * 100)
            self.progress_signal.emit(pct)
            if label: self.log(f"[{step[0]}/{total_steps}] {label}")

        output_folder = Path(self.cfg["output_folder"]).resolve()
        self._ensure_dir(output_folder)
        ext_name  = self.cfg["new_pack_name"].strip()
        pack_root = output_folder / ext_name
        if pack_root.exists(): shutil.rmtree(pack_root)
        self._ensure_dir(pack_root)
        self._temp_files.append(pack_root)
        tick("Pack folder created")

        # Create NekoUI folder structure
        for d in [
            self.NEKO_ANIM_BG_DIR,
            self.NEKO_LOADING_BG_DIR,
            self.NEKO_CONTAINER_BG_DIR,
            self.NEKO_COMMON_DIR,
            self.NEKO_SOUNDS_DIR,
            UI_DIR,
            "subpacks/dynamic",
            "subpacks/static/" + self.NEKO_COMMON_DIR,
            "subpacks/static/" + self.NEKO_ANIM_BG_DIR,
        ]:
            self._ensure_dir(pack_root / d)
        tick("NekoUI folder structure created")

        video_input     = self.cfg["video_path"]
        source_is_image = self.cfg.get("source_is_image", False)
        delete_after    = False

        if source_is_image:
            img_src = Path(video_input).resolve()
            if not img_src.exists():
                raise FileNotFoundError(f"Image not found: {img_src}")
            video = None
            tick("Image source ready")

            anim_dir = self._neko_use_image_as_background(img_src, pack_root)
            tick("Image placed as background frame")

            if self.cfg.get("loading_bg_folder", "").strip():
                load_dir = self._neko_copy_loading_bg_folder(pack_root)
                tick("Loading background images copied from folder")
            else:
                load_dir = pack_root / self.NEKO_LOADING_BG_DIR
                self._ensure_dir(load_dir)
                src_frame = anim_dir / f"{FRAME_PREFIX_ANIM}001.png"
                shutil.copy2(src_frame, load_dir / "1.png")
                self.log("[NekoUI] Image mode: using bg image as loading frame")
                tick("Loading background frame set from image")
        else:
            if re.match(r"^https?://(www\.)?(youtube\.com|youtu\.be)/", video_input):
                self.cfg["is_trimmed"] = False
                video = self._download_youtube(video_input, output_folder / "_tmp_yt")
                self._temp_files.append(video.parent)
                delete_after = True
            else:
                video = Path(video_input).resolve()
                if not video.exists():
                    raise FileNotFoundError(f"Video not found: {video}")
                self.cfg["is_trimmed"] = False
            tick("Video ready")

            bg_mode = self.cfg.get("bg_mode", "dynamic")
            self.log(f"[NekoUI] Background mode: {bg_mode}")

            if bg_mode == "static":
                anim_dir = self._neko_extract_frame_static(video, pack_root)
                tick("Static background frame extracted")
            elif bg_mode == "both":
                anim_dir = self._neko_build_both_subpacks(video, pack_root)
                tick("Dynamic + static subpack frames prepared")
            else:
                anim_dir = self._neko_extract_frames_anim(video, pack_root)
                tick("Animated background frames extracted")

            if self.cfg.get("loading_bg_folder", "").strip():
                load_dir = self._neko_copy_loading_bg_folder(pack_root)
                tick("Loading background images copied from folder")
            elif self.cfg.get("use_black_loading"):
                load_dir = pack_root / self.NEKO_LOADING_BG_DIR
                self._gen_black_loading_frame(load_dir)
                tick("Loading background: black frame")
            else:
                load_dir = self._neko_extract_frames_loading(video, pack_root)
                tick("Loading background frames extracted")

        self._make_blur_png_for_dir(anim_dir)
        tick("blur.png created")

        method = self.cfg.get("compress_method", "lossless").lower()
        compressor = self._get_compressor(method)
        if compressor:
            self.log(f"[NekoUI] Compressing anim frames via {method}...")
            compressor.compress(anim_dir)
        tick("Anim frames compressed")

        if compressor:
            self.log(f"[NekoUI] Compressing loading frames via {method}...")
            compressor.compress(load_dir)
        tick("Loading frames compressed")

        self._neko_download_container_bg(pack_root)
        tick("Container background downloaded")

        if self.cfg.get("bgm_file", "").strip():
            self._neko_copy_bgm(pack_root)
        elif re.match(r"^https?://(www\.)?(youtube\.com|youtu\.be)/", video_input):
            self._neko_download_youtube_audio(video_input, pack_root)
        elif video:
            self._neko_download_audio(video, pack_root)
        tick("Audio prepared")

        self._copy_pack_icon(pack_root)
        tick("Pack icon copied")

        # Generate all NekoUI JSON files
        common_dir = pack_root / self.NEKO_COMMON_DIR
        self._neko_gen_hans_animated_background(anim_dir, common_dir)
        self._neko_gen_hans_loading_background(load_dir, common_dir)
        self._neko_gen_sub_backgrounds(common_dir)
        self._neko_gen_sound_definitions(pack_root)
        self._neko_gen_ui_defs(pack_root)
        self._neko_gen_global_variables(pack_root)
        self._gen_manifest(pack_root)
        tick("JSON files generated")

        zip_base = output_folder / (ext_name + ".mcpack")
        if zip_base.exists(): zip_base.unlink()
        self.log(f"[NekoUI] Packing → {zip_base}")
        shutil.make_archive(str(zip_base.with_suffix("")), "zip", pack_root)
        zip_tmp = zip_base.with_suffix(".zip")
        if zip_tmp.exists(): zip_tmp.rename(zip_base)
        tick("mcpack created")

        shutil.rmtree(pack_root, ignore_errors=True)
        self._temp_files.remove(pack_root)
        if delete_after and video:
            shutil.rmtree(video.parent, ignore_errors=True)
        tick("Cleanup done")

        self.log(f"\n✅ [NekoUI] Done! Output: {zip_base}")
        self.progress_signal.emit(100)
        return True


class JavaWorker(Worker):
    """
    Builds a Java Edition resource pack (.zip) with a simple structure:

        {extension_name}/
        ├── assets/
        │   └── nekoui/
        │       └── background/
        │           └── {extension_name}/
        │               ├── {extension_name}1.png
        │               ├── {extension_name}2.png
        │               └── ...
        └── pack.mcmeta

    The pack is zipped as {extension_name}.zip (not .mcpack).
    Works for both HorizonUI and NekoUI Java tabs — same structure.
    """

    def _java_safe_name(self) -> str:
        """Strip §-codes and filesystem-unsafe chars for use in file/folder names."""
        name = self.cfg.get("new_pack_name", "MyExtension").strip()
        name = re.sub(r"§.", "", name)          # strip §x colour/format codes
        name = re.sub(r'[\\/:*?"<>|]', "_", name)  # strip filesystem-unsafe chars
        return name.strip("_ ") or "MyExtension"

    def _success_message(self) -> str:
        return "✅ .zip created successfully!"

    def _java_extract_frames(self, video: Path, frames_dir: Path) -> Path:
        if self._stop_requested: raise RuntimeError("Cancelled.")
        if frames_dir.exists(): shutil.rmtree(frames_dir)
        self._ensure_dir(frames_dir)
        n   = int(self.cfg.get("anim_frames", 100))
        fps = self.cfg.get("fps", DEFAULT_FPS)
        tmp = frames_dir / "frame_%03d.png"
        args = ["-y"]
        if not self.cfg.get("is_trimmed"):
            ss = self.cfg.get("start_seconds")
            en = self.cfg.get("end_seconds")
            if ss is not None: args += ["-ss", str(ss)]
            if en is not None and ss is not None: args += ["-t", str(en - ss)]
        args += ["-i", str(video), "-vf", f"fps={fps}", "-frames:v", str(n), str(tmp)]
        self._run_ffmpeg(args)
        return frames_dir

    def _java_rename_frames(self, frames_dir: Path, safe_name: str) -> int:
        """Rename frame_001.png → {name}1.png, frame_002.png → {name}2.png …"""
        frames = sorted(frames_dir.glob("frame_*.png"))
        for idx, f in enumerate(frames, start=1):
            f.rename(frames_dir / f"{safe_name}{idx}.png")
        return len(frames)

    def _java_use_image(self, img_src: Path, frames_dir: Path, safe_name: str) -> int:
        if self._stop_requested: raise RuntimeError("Cancelled.")
        self._ensure_dir(frames_dir)
        out = frames_dir / f"{safe_name}1.png"
        if img_src.suffix.lower() == ".png":
            shutil.copy2(img_src, out)
        else:
            Image.open(str(img_src)).convert("RGBA").save(str(out), "PNG")
        self.log(f"[Java] Image placed as {out.name}")
        return 1

    def _java_copy_pack_icon(self, pack_root: Path):
        """Save pack icon as pack.png (Java Edition convention)."""
        if self._stop_requested: raise RuntimeError("Cancelled.")
        pil_img  = self.cfg.get("pack_icon_pil")
        raw_path = self.cfg.get("pack_icon_path", "").strip()
        if pil_img is not None:
            dst = pack_root / "pack.png"
            pil_img.save(str(dst), "PNG")
            self.log(f"[Java] pack.png saved (cropped 256×256) → {dst}")
        elif raw_path:
            src = Path(raw_path)
            if src.exists():
                dst = pack_root / "pack.png"
                shutil.copy2(src, dst)
                self.log(f"[Java] pack.png copied → {dst}")
        else:
            self.log("[Java] No pack icon specified — skipping pack.png.")

    def _java_gen_pack_mcmeta(self, pack_root: Path):
        name    = self.cfg.get("new_pack_name", "MyExtension").strip()
        creator = self.cfg.get("creator", "Unknown")
        ver_x   = int(self.cfg.get("ext_ver_x", 1))
        ver_y   = int(self.cfg.get("ext_ver_y", 0))
        ver_z   = int(self.cfg.get("ext_ver_z", 0))
        desc    = f"§fNekoUI AB - {name} (v{ver_x}.{ver_y}.{ver_z}) - by {creator} | Built with TuBeo5866's Extension Studio"
        content = json.dumps({
            "pack": {
                "pack_format": 15,
                "description": desc
            }
        }, indent=2, ensure_ascii=False)
        (pack_root / "pack.mcmeta").write_text(content, encoding="utf-8")
        self.log("[Java] pack.mcmeta generated ✓")

    def process(self):
        self._monitor_memory()
        total_steps = 8
        step = [0]

        def tick(label=""):
            step[0] += 1
            self.progress_signal.emit(int(step[0] / total_steps * 100))
            if label: self.log(f"[{step[0]}/{total_steps}] {label}")

        output_folder = Path(self.cfg["output_folder"]).resolve()
        self._ensure_dir(output_folder)
        ext_name  = self.cfg["new_pack_name"].strip()
        safe_name = self._java_safe_name()
        pack_root = output_folder / safe_name
        if pack_root.exists(): shutil.rmtree(pack_root)
        self._ensure_dir(pack_root)
        self._temp_files.append(pack_root)
        tick("Pack folder created")

        frames_dir = pack_root / "assets" / "nekoui" / "background" / safe_name
        self._ensure_dir(frames_dir)
        tick("Folder structure created")

        video_input     = self.cfg["video_path"]
        source_is_image = self.cfg.get("source_is_image", False)
        delete_after    = False

        if source_is_image:
            img_src = Path(video_input).resolve()
            if not img_src.exists():
                raise FileNotFoundError(f"Image not found: {img_src}")
            n = self._java_use_image(img_src, frames_dir, safe_name)
            tick(f"Image placed ({n} frame)")
        else:
            if re.match(r"^https?://(www\.)?(youtube\.com|youtu\.be)/", video_input):
                self.cfg["is_trimmed"] = False
                video = self._download_youtube(video_input, output_folder / "_tmp_yt")
                self._temp_files.append(video.parent)
                delete_after = True
            else:
                video = Path(video_input).resolve()
                if not video.exists():
                    raise FileNotFoundError(f"Video not found: {video}")
                self.cfg["is_trimmed"] = False
            tick("Video ready")

            self._java_extract_frames(video, frames_dir)
            n = self._java_rename_frames(frames_dir, safe_name)
            tick(f"{n} frames extracted and renamed")

        method = self.cfg.get("compress_method", "lossless").lower()
        compressor = self._get_compressor(method)
        if compressor:
            self.log(f"[Java] Compressing frames via {method}...")
            compressor.compress(frames_dir)
        tick("Frames compressed")

        self._java_copy_pack_icon(pack_root)
        self._java_gen_pack_mcmeta(pack_root)
        tick("Metadata generated")

        zip_base = output_folder / (safe_name + ".zip")
        if zip_base.exists(): zip_base.unlink()
        self.log(f"[Java] Packing → {zip_base}")
        shutil.make_archive(str(zip_base.with_suffix("")), "zip", pack_root)
        # make_archive always produces .zip so no rename needed
        tick(".zip created")

        shutil.rmtree(pack_root, ignore_errors=True)
        self._temp_files.remove(pack_root)
        if delete_after:
            shutil.rmtree(video.parent, ignore_errors=True)
        tick("Cleanup done")

        self.log(f"\n✅ [Java] Done! Output: {zip_base}")
        self.progress_signal.emit(100)
        return True


class AnnouncementBanner(QWidget):
    """
    Floating pill-shaped announcement banner.
    - Right-aligned, width = 2/5 of parent, small right margin
    - 10s countdown then auto-dismisses with fade animation
    - Draggable: swipe up/right/left to dismiss
    - X button to dismiss immediately
    """
    _FETCH_URL    = "https://tubeo5866.github.io/banner.txt"
    _MIN_HEIGHT   = 38
    _RIGHT_MARGIN = 12
    _TOP_MARGIN   = 10
    _COUNTDOWN    = 10  # seconds
    _V_PADDING    = 10  # vertical padding inside pill

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setWindowFlags(Qt.SubWindow)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.hide()

        self._drag_start  = None
        self._drag_origin = None
        self._dismissed   = False
        self._countdown   = self._COUNTDOWN

        from PyQt5.QtWidgets import QGraphicsOpacityEffect
        self._opacity_fx = QGraphicsOpacityEffect(self)
        self._opacity_fx.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_fx)

        self._fade_anim = QtCore.QPropertyAnimation(self._opacity_fx, b"opacity")
        self._fade_anim.setDuration(300)
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.finished.connect(self._on_fade_done)

        self._slide_anim = QtCore.QPropertyAnimation(self, b"pos")
        self._slide_anim.setDuration(300)
        self._slide_anim.setEasingCurve(QtCore.QEasingCurve.OutCubic)

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)

        self._build()
        self._fetch()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 8, 0)
        layout.setSpacing(6)

        icon_lbl = QLabel("📢")
        icon_lbl.setStyleSheet("font-size:12px; background:transparent;")
        icon_lbl.setFixedWidth(18)
        icon_lbl.setAttribute(Qt.WA_TranslucentBackground)

        self._lbl = QLabel()
        self._lbl.setWordWrap(True)
        self._lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self._lbl.setStyleSheet(
            "font-size:10px; font-weight:bold; color:#ffffff; background:transparent;"
        )
        self._lbl.setAttribute(Qt.WA_TranslucentBackground)

        btn_close = QPushButton("✕")
        btn_close.setFixedSize(20, 20)
        btn_close.setToolTip("Dismiss")
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setAttribute(Qt.WA_TranslucentBackground)
        btn_close.setStyleSheet(
            "QPushButton { background:rgba(255,255,255,30); color:#ffffffcc; "
            "border:none; border-radius:10px; font-size:11px; font-weight:bold; }"
            "QPushButton:hover { background:rgba(255,255,255,70); color:#ffffff; }"
        )
        btn_close.clicked.connect(self._dismiss)

        layout.addWidget(icon_lbl)
        layout.addWidget(self._lbl, stretch=1)
        layout.addWidget(btn_close, alignment=Qt.AlignVCenter)

    # ── Pill painting ─────────────────────────────────────────────────────────
    def paintEvent(self, event):
        from PyQt5.QtGui import QLinearGradient
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 20, 20)
        grad = QLinearGradient(0, 0, self.width(), 0)
        grad.setColorAt(0.0, QColor("#0d1b4b"))
        grad.setColorAt(1.0, QColor("#005f73"))
        painter.fillPath(path, grad)
        painter.setPen(QtGui.QPen(QColor("#00b4d8"), 1.0))
        painter.drawPath(path)
        painter.end()

    # ── Positioning ───────────────────────────────────────────────────────────
    def _reposition(self):
        p = self.parent()
        if p is None:
            return
        pw = p.width()
        pill_w = max(pw * 2 // 5, 180)
        self.setFixedWidth(pill_w)
        # Compute required label height given the pill width
        inner_w = pill_w - 18 - 24 - 20 - 12 - 6 * 3  # subtract icons/btn/margins
        self._lbl.setFixedWidth(max(inner_w, 60))
        lbl_h = self._lbl.heightForWidth(max(inner_w, 60))
        if lbl_h < 1:
            lbl_h = self._lbl.sizeHint().height()
        pill_h = max(lbl_h + self._V_PADDING * 2, self._MIN_HEIGHT)
        self.setFixedHeight(pill_h)
        x = pw - pill_w - self._RIGHT_MARGIN
        self.move(x, self._TOP_MARGIN)

    # ── Countdown ─────────────────────────────────────────────────────────────
    def _on_tick(self):
        self._countdown -= 1
        if self._countdown <= 0:
            self._timer.stop()
            self._dismiss()

    # ── Drag ─────────────────────────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start  = event.globalPos()
            self._drag_origin = self.pos()
            self.setCursor(Qt.ClosedHandCursor)
            self._timer.stop()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start is not None:
            delta = event.globalPos() - self._drag_start
            new_y = min(self._drag_origin.y() + delta.y(), self._drag_origin.y())
            self.move(self._drag_origin.x() + delta.x(), new_y)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_start is not None and self._drag_origin is not None:
            delta = event.globalPos() - self._drag_start
            threshold = 55
            if abs(delta.x()) > threshold or delta.y() < -threshold:
                p = self.parent()
                pw = p.width() if p else 800
                if delta.y() < -threshold:
                    end_pos = QtCore.QPoint(self.x(), -self.height() - 20)
                elif delta.x() > 0:
                    end_pos = QtCore.QPoint(pw + 20, self.y())
                else:
                    end_pos = QtCore.QPoint(-pw - 20, self.y())
                self._slide_anim.setStartValue(self.pos())
                self._slide_anim.setEndValue(end_pos)
                self._slide_anim.start()
                self._fade_anim.start()
                self._dismissed = True
            else:
                snap = QtCore.QPropertyAnimation(self, b"pos")
                snap.setDuration(200)
                snap.setEasingCurve(QtCore.QEasingCurve.OutBack)
                snap.setStartValue(self.pos())
                snap.setEndValue(self._drag_origin)
                snap.start()
                self._snap_anim = snap
                self._timer.start()
        self._drag_start  = None
        self._drag_origin = None
        self.setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def enterEvent(self, event):
        if not self._dismissed:
            self.setCursor(Qt.OpenHandCursor)
            self._timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setCursor(Qt.ArrowCursor)
        if not self._dismissed and self.isVisible():
            self._timer.start()
        super().leaveEvent(event)

    # ── Dismiss ───────────────────────────────────────────────────────────────
    def _dismiss(self):
        if self._dismissed:
            return
        self._dismissed = True
        self._timer.stop()
        end_pos = QtCore.QPoint(self.x(), -self.height() - 20)
        self._slide_anim.setStartValue(self.pos())
        self._slide_anim.setEndValue(end_pos)
        self._slide_anim.start()
        self._fade_anim.start()

    def _on_fade_done(self):
        self.hide()

    # ── Fetch ─────────────────────────────────────────────────────────────────
    def _fetch(self):
        class _Fetcher(QtCore.QThread):
            result = QtCore.pyqtSignal(str)
            def run(self_inner):
                try:
                    import urllib.request
                    with urllib.request.urlopen(
                        AnnouncementBanner._FETCH_URL, timeout=8
                    ) as resp:
                        text = resp.read().decode("utf-8", errors="replace").strip()
                    self_inner.result.emit(text)
                except Exception:
                    self_inner.result.emit("")
        self._fetcher = _Fetcher()
        self._fetcher.result.connect(self._on_fetched)
        self._fetcher.start()

    def _on_fetched(self, text: str):
        if not text:
            return
        self._lbl.setText(text)
        self._reposition()
        self.raise_()
        self.show()
        self._timer.start()


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = None
        self._pack_icon_pil  = None
        self._pack_icon_path = ""
        self.setWindowTitle(WINDOW_TITLE)
        self.setMinimumWidth(860)
        self.setMinimumHeight(740)
        self._set_icon_from_url("https://www.dropbox.com/scl/fi/yymr5hnfkko77aaxadjta/logo_bigger.png?rlkey=gicau4lxtbbhmq9vt2reyrk8c&st=kvv7wolj&dl=1")
        self._about_banner_data = b""
        self._prefetch_banner()
        self._build_ui()

    def _set_icon_from_url(self, url: str):
        try:
            import urllib.request
            data = urllib.request.urlopen(url, timeout=5).read()
            px = QPixmap()
            px.loadFromData(data)
            self.setWindowIcon(QIcon(px))
        except Exception as e:
            print(f"[icon] Could not load icon: {e}")

    def _prefetch_banner(self):
        _BANNER_URL = "https://www.dropbox.com/scl/fi/w61xk942afmyvz54rb8xx/HDILdO1aoAArAMq.jpg?rlkey=rd1bfbpky16kta3jkelsp480e&st=fatacbzw&dl=1"

        class _Fetcher(QtCore.QThread):
            result = QtCore.pyqtSignal(bytes)
            def __init__(self, url):
                super().__init__()
                self._url = url
            def run(self):
                try:
                    import urllib.request
                    data = urllib.request.urlopen(self._url, timeout=10).read()
                    self.result.emit(data)
                except Exception:
                    self.result.emit(b"")

        def _on_data(data):
            self._about_banner_data = data

        self._banner_fetcher = _Fetcher(_BANNER_URL)
        self._banner_fetcher.result.connect(_on_data)
        self._banner_fetcher.start()

    def _build_ui(self):
        from PyQt5.QtWidgets import QSplitter, QTabWidget
        from PyQt5.QtCore import Qt as _Qt

        # ── Announcement banner — floating pill overlay ───────────────────────
        self._announcement_banner = AnnouncementBanner(self)

        # Outer vertical layout (banner is NOT in the layout — it floats above)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        _tab_style = """
            QTabWidget::pane {
                border: 1px solid #444;
                border-top: none;
                background: transparent;
            }
            QTabBar::tab {
                background: #2a2a2a;
                color: #aaa;
                padding: 8px 22px;
                min-width: 80px;
                border: 1px solid #444;
                border-bottom: none;
                border-radius: 4px 4px 0 0;
                font-weight: bold;
                font-size: 11px;
            }
            QTabBar::tab:selected {
                background: #1a1a2e;
                color: #7ec8e3;
                border-bottom: 2px solid #7ec8e3;
            }
            QTabBar::tab:hover:!selected {
                background: #333;
                color: #ccc;
            }
            QTabBar {
                qproperty-expanding: 1;
            }
        """

        # ── Outer tabs: Bedrock Edition | Java Edition + Settings gear ──────────
        self._outer_tab_widget = QTabWidget()
        self._outer_tab_widget.setTabPosition(QTabWidget.North)
        self._outer_tab_widget.setStyleSheet(_tab_style)
        self._outer_tab_widget.currentChanged.connect(self._on_outer_tab_changed)

        # Build / Cancel button — lives in the outer tab bar row
        self.btn_run = QPushButton("Build mcpack\n(Bedrock / HorizonUI)")
        self.btn_run.clicked.connect(self.run_process)
        self.btn_run.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.btn_run.setFixedWidth(180)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setVisible(False)
        self.btn_cancel.clicked.connect(self.cancel_process)
        self.btn_cancel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.btn_cancel.setFixedWidth(180)


        # All buttons go into the right column grid — no corner widgets needed
        self._btn_open_pack = QPushButton("Open…")
        self._btn_open_pack.setToolTip("Load an existing .mcpack or .zip to pre-fill the form")
        self._btn_open_pack.clicked.connect(self._load_pack_from_file)
        self._btn_open_pack.setFixedWidth(90)

        self._btn_settings = QPushButton("Settings")
        self._btn_settings.setToolTip("Options & About")
        self._btn_settings.clicked.connect(self._show_settings_menu)
        self._btn_settings.setFixedWidth(90)

        self._btn_about = QPushButton("About")
        self._btn_about.setToolTip("About this studio")
        self._btn_about.clicked.connect(self._show_about)
        self._btn_about.setFixedWidth(90)

        self._outer_tab_widget.tabBar().setExpanding(True)

        # ── Inner tabs for Bedrock (HorizonUI | NekoUI) ───────────────────────
        self._bedrock_tab_widget = QTabWidget()
        self._bedrock_tab_widget.setTabPosition(QTabWidget.North)
        self._bedrock_tab_widget.setStyleSheet(_tab_style)
        self._bedrock_tab_widget.currentChanged.connect(self._on_tab_changed)
        self._bedrock_tab_widget.tabBar().setExpanding(True)

        for label in ("HorizonUI", "NekoUI"):
            w = QWidget()
            QVBoxLayout(w).setContentsMargins(0, 0, 0, 0)
            self._bedrock_tab_widget.addTab(w, label)

        # Java Edition: no inner tabs needed
        self._java_tab_widget = None

        bedrock_outer = QWidget()
        bedrock_vbox  = QVBoxLayout(bedrock_outer)
        bedrock_vbox.setContentsMargins(0, 0, 0, 0)
        bedrock_vbox.setSpacing(0)
        bedrock_vbox.addWidget(self._bedrock_tab_widget)

        # Java outer — plain widget, no inner tabs (uses same right-column buttons)
        java_outer = QWidget()
        java_outer.setStyleSheet("background: transparent;")
        java_outer_v = QVBoxLayout(java_outer)
        java_outer_v.setContentsMargins(0, 0, 0, 0)

        self._outer_tab_widget.addTab(bedrock_outer, "Bedrock Edition")
        self._outer_tab_widget.addTab(java_outer,    "Java Edition")

        # ── Tab area + right column ────────────────────────────────────────────
        # Right column layout:
        #   col 0          | col 1
        #   [  Open...  ]  | [         ]
        #   [  Settings ]  | [  Build  ]
        from PyQt5.QtWidgets import QGridLayout as _QGL
        tab_build_row = QWidget()
        tab_build_h   = QHBoxLayout(tab_build_row)
        tab_build_h.setContentsMargins(0, 0, 0, 0)
        tab_build_h.setSpacing(0)
        tab_build_h.addWidget(self._outer_tab_widget, stretch=1)

        right_col  = QWidget()
        right_col.setFixedWidth(280)
        right_grid = _QGL(right_col)
        right_grid.setContentsMargins(4, 2, 4, 2)
        right_grid.setSpacing(2)
        right_grid.addWidget(self._btn_open_pack, 0, 0)
        right_grid.addWidget(self._btn_settings,  1, 0)
        right_grid.addWidget(self._btn_about,      2, 0)
        right_grid.addWidget(self.btn_run,         0, 1, 2, 1)
        right_grid.addWidget(self.btn_cancel,      0, 1, 2, 1)
        right_grid.setColumnStretch(0, 0)
        right_grid.setColumnStretch(1, 1)
        tab_build_h.addWidget(right_col)
        tab_build_h.setAlignment(right_col, _Qt.AlignTop)

        outer.addWidget(tab_build_row)

        # Shared inner container (splitter + form) — used for ALL 4 tab combos
        inner_container = QWidget()
        inner_container.setObjectName("inner_container")
        root = QHBoxLayout(inner_container)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        outer.addWidget(inner_container, stretch=1)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter)
        self._splitter = splitter

        left_outer = QWidget()
        left_outer.setMinimumWidth(480)
        left_vbox = QVBoxLayout(left_outer)
        left_vbox.setContentsMargins(0, 0, 0, 0)
        left_vbox.setSpacing(4)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        form_widget = QWidget()
        g = QGridLayout(form_widget)
        g.setSpacing(6)
        g.setContentsMargins(4, 4, 4, 4)
        g.setColumnStretch(1, 1)
        self._form_widget = form_widget
        scroll.setWidget(form_widget)
        left_vbox.addWidget(scroll, stretch=1)

        r = 0

        def _sec(title):
            nonlocal r
            if r > 0:
                sep = QFrame(); sep.setFrameShape(QFrame.HLine)
                sep.setStyleSheet("color:#444;")
                g.addWidget(sep, r, 0, 1, 3); r += 1
            lbl = QLabel(title)
            lbl.setStyleSheet("font-weight:bold;color:#888;font-size:10px;padding-top:2px;")
            g.addWidget(lbl, r, 0, 1, 3); r += 1

        def _row(label, widget, btn=None, tooltip=""):
            nonlocal r
            lbl = QLabel(label)
            if tooltip:
                lbl.setToolTip(tooltip)
            g.addWidget(lbl, r, 0)
            if btn:
                g.addWidget(widget, r, 1)
                g.addWidget(btn, r, 2)
            else:
                g.addWidget(widget, r, 1, 1, 2)
            r += 1

        _sec("OUTPUT")

        self.inp_output = QLineEdit(str(Path.home() / "UI_Extensions"))
        btn_o = QPushButton("Browse…"); btn_o.clicked.connect(self.browse_output)
        _row("Output Folder:", self.inp_output, btn_o)

        self.inp_packname = QLineEdit("MyExtension")
        btn_fmt = QPushButton("Format…")
        btn_fmt.setToolTip("Insert Minecraft § colour / style codes into the extension name")
        btn_fmt.clicked.connect(lambda: self._open_format_dialog(self.inp_packname))
        _row("Extension Name:", self.inp_packname, btn_fmt)

        # Debug-only: log when user edits the field directly (not via Format dialog).
        self._dbg_last_packname = self.inp_packname.text()
        def _on_packname_edited():
            if not _IS_DEBUG:
                return
            new = self.inp_packname.text().strip()
            old = getattr(self, "_dbg_last_packname", "")
            if new != old:
                self.append_log(f"[DEBUG] Extension Name changed: {old!r} → {new!r}")
            self._dbg_last_packname = new
        self.inp_packname.editingFinished.connect(_on_packname_edited)

        self.inp_creator = QLineEdit("Unknown")
        btn_fmt_creator = QPushButton("Format…")
        btn_fmt_creator.setToolTip("Insert Minecraft § colour / style codes into the creator name")
        btn_fmt_creator.clicked.connect(lambda: self._open_format_dialog(self.inp_creator))
        _row("Creator Name:", self.inp_creator, btn_fmt_creator)

        # Debug-only: log when user edits the field directly (not via Format dialog).
        self._dbg_last_creator = self.inp_creator.text()
        def _on_creator_edited():
            if not _IS_DEBUG:
                return
            new = self.inp_creator.text().strip()
            old = getattr(self, "_dbg_last_creator", "")
            if new != old:
                self.append_log(f"[DEBUG] Creator Name changed: {old!r} → {new!r}")
            self._dbg_last_creator = new
        self.inp_creator.editingFinished.connect(_on_creator_edited)

        self.inp_pack_icon = QLineEdit()
        self.inp_pack_icon.setPlaceholderText("(optional) Select a PNG file")
        self.inp_pack_icon.setReadOnly(True)
        self.inp_pack_icon.setToolTip(
            "Choose a PNG to use as the pack icon (pack_icon.png).\n"
            "A crop & zoom dialog will appear so you can frame it perfectly.\n"
            "If the file is already named 'pack_icon', it will be copied as-is."
        )

        self._icon_thumb = QLabel()
        self._icon_thumb.setFixedSize(36, 36)
        self._icon_thumb.setStyleSheet(
            "border:1px solid #555; border-radius:3px; background:#1a1a1a;"
        )
        self._icon_thumb.setAlignment(Qt.AlignCenter)
        self._icon_thumb.setToolTip("Pack icon preview")

        btn_icon = QPushButton("Browse…")
        btn_icon.clicked.connect(self.browse_pack_icon)

        btn_icon_clear = QPushButton("✖")
        btn_icon_clear.setFixedWidth(28)
        btn_icon_clear.setToolTip("Clear pack icon")
        btn_icon_clear.clicked.connect(self.clear_pack_icon)

        icon_row_widget = QWidget()
        icon_row_h = QHBoxLayout(icon_row_widget)
        icon_row_h.setContentsMargins(0, 0, 0, 0)
        icon_row_h.setSpacing(4)
        icon_row_h.addWidget(self._icon_thumb)
        icon_row_h.addWidget(self.inp_pack_icon, stretch=1)

        btn_icon_group = QWidget()
        btn_group_h = QHBoxLayout(btn_icon_group)
        btn_group_h.setContentsMargins(0, 0, 0, 0)
        btn_group_h.setSpacing(2)
        btn_group_h.addWidget(btn_icon)
        btn_group_h.addWidget(btn_icon_clear)

        _row("Pack Icon:", icon_row_widget, btn_icon_group,
             tooltip="PNG image used as the pack icon (pack_icon.png).")

        self._bg_mode_group = QButtonGroup(self)
        self._bg_mode_group.setExclusive(True)

        self.rdo_dynamic = QRadioButton("Dynamic")
        self.rdo_dynamic.setChecked(True)
        self.rdo_dynamic.setToolTip(
            "Extract the requested number of frames into hrzn_animated_background.\n"
            "Produces a fully animated background."
        )

        self.rdo_static = QRadioButton("Static")
        self.rdo_static.setToolTip(
            "Extract a single frame (at the start time) into hrzn_animated_background.\n"
            "Produces a still background image — smaller pack size."
        )

        self.rdo_both = QRadioButton("Both")
        self.rdo_both.setToolTip(
            "Dynamic frames go into hrzn_animated_background (main pack).\n"
            "A ./subpacks/static/ folder is also created with just the first frame\n"
            "plus its own .hrzn_public_bg_anim.json configured for 1 frame."
        )

        for rdo in (self.rdo_dynamic, self.rdo_static, self.rdo_both):
            self._bg_mode_group.addButton(rdo)

        rdo_widget = QWidget()
        self._rdo_bg_widget = rdo_widget
        rdo_h = QHBoxLayout(rdo_widget)
        rdo_h.setContentsMargins(0, 0, 0, 0)
        rdo_h.setSpacing(12)
        rdo_h.addWidget(self.rdo_dynamic)
        rdo_h.addWidget(self.rdo_static)
        rdo_h.addWidget(self.rdo_both)
        rdo_h.addStretch()

        self._lbl_bg_type = QLabel("Background Type:")
        self._lbl_bg_type.setToolTip("Choose how the animated background is built.")
        g.addWidget(self._lbl_bg_type, r, 0)
        g.addWidget(rdo_widget, r, 1, 1, 2)
        r += 1

        ver_widget = QWidget()
        ver_h = QHBoxLayout(ver_widget)
        ver_h.setContentsMargins(0, 0, 0, 0)
        ver_h.setSpacing(4)

        def _make_ver_spin():
            sb = QSpinBox()
            sb.setRange(0, 99999)
            sb.setValue(0)
            sb.setFixedWidth(64)
            sb.setAlignment(Qt.AlignCenter)
            return sb

        self.spn_ver_x = QSpinBox()
        self.spn_ver_x.setRange(0, 99999)
        self.spn_ver_x.setValue(1)
        self.spn_ver_x.setFixedWidth(70)
        self.spn_ver_x.setAlignment(Qt.AlignCenter)

        self.spn_ver_y = _make_ver_spin()
        self.spn_ver_y.setValue(0)

        self.spn_ver_z = _make_ver_spin()

        dot1 = QLabel(".")
        dot1.setStyleSheet("font-weight:bold; font-size:14px;")
        dot2 = QLabel(".")
        dot2.setStyleSheet("font-weight:bold; font-size:14px;")

        ver_h.addWidget(self.spn_ver_x)
        ver_h.addWidget(dot1)
        ver_h.addWidget(self.spn_ver_y)
        ver_h.addWidget(dot2)
        ver_h.addWidget(self.spn_ver_z)
        ver_h.addStretch()

        _row("Extension Version:", ver_widget,
             tooltip="Version embedded in manifest.json — format X.Y.Z (e.g. 201.1.0)")

        _sec("SOURCES")

        src_type_widget = QWidget()
        src_type_hbox = QHBoxLayout(src_type_widget)
        src_type_hbox.setContentsMargins(0, 0, 0, 0)
        self.rdo_src_video   = QRadioButton("Video")
        self.rdo_src_youtube = QRadioButton("YouTube Video")
        self.rdo_src_image   = QRadioButton("Image")
        self.rdo_src_video.setChecked(True)
        self._src_type_group = QButtonGroup(self)
        self._src_type_group.addButton(self.rdo_src_video,   0)
        self._src_type_group.addButton(self.rdo_src_youtube, 1)
        self._src_type_group.addButton(self.rdo_src_image,   2)
        src_type_hbox.addWidget(self.rdo_src_video)
        src_type_hbox.addWidget(self.rdo_src_youtube)
        src_type_hbox.addWidget(self.rdo_src_image)
        src_type_hbox.addStretch()
        _row("Source Type:", src_type_widget)

        self.inp_video = QLineEdit()
        self.inp_video.setPlaceholderText("Local video file path")
        self._btn_browse_video = QPushButton("Browse…"); self._btn_browse_video.clicked.connect(self.browse_video)
        self._lbl_video = QLabel("Video File:")
        g.addWidget(self._lbl_video, r, 0)
        g.addWidget(self.inp_video, r, 1)
        g.addWidget(self._btn_browse_video, r, 2)
        r += 1

        self.inp_yt_url = QLineEdit()
        self.inp_yt_url.setPlaceholderText("https://youtu.be/...")
        self._lbl_yt_url = QLabel("YouTube URL:")
        g.addWidget(self._lbl_yt_url, r, 0)
        g.addWidget(self.inp_yt_url, r, 1, 1, 2)
        r += 1


        # YouTube cookies — cookies.txt file only
        self._lbl_yt_cookies = QLabel("Cookies File:")

        self.inp_yt_cookiefile = QLineEdit()
        self.inp_yt_cookiefile.setPlaceholderText("Select cookies.txt (Netscape format)")
        self.inp_yt_cookiefile.setReadOnly(True)
        self._btn_yt_cookiefile = QPushButton("Browse…")
        self._btn_yt_cookiefile.clicked.connect(self._browse_yt_cookiefile)

        yt_cookies_help = QLabel('<a href="#">?</a>')
        yt_cookies_help.setToolTip(
            "YouTube requires a cookies.txt file to avoid bot detection (HTTP 429).\n"
            "Export your cookies using a browser extension (e.g. 'Get cookies.txt LOCALLY')\n"
            "then browse to the file here.\n\n"
            "Click to open documentation."
        )
        yt_cookies_help.setFixedWidth(16)
        yt_cookies_help.setAlignment(Qt.AlignCenter)
        def _open_yt_docs(_event):
            __import__('webbrowser').open('https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp')
            __import__('webbrowser').open('https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies')
        yt_cookies_help.mousePressEvent = _open_yt_docs

        self._yt_cookies_row = QWidget()
        yt_cookies_h = QHBoxLayout(self._yt_cookies_row)
        yt_cookies_h.setContentsMargins(0, 0, 0, 0)
        yt_cookies_h.setSpacing(4)
        yt_cookies_h.addWidget(self.inp_yt_cookiefile, stretch=1)
        yt_cookies_h.addWidget(self._btn_yt_cookiefile)
        yt_cookies_h.addWidget(yt_cookies_help)

        g.addWidget(self._lbl_yt_cookies, r, 0)
        g.addWidget(self._yt_cookies_row, r, 1, 1, 2)
        r += 1

        self.inp_image_src = QLineEdit()
        self.inp_image_src.setPlaceholderText("PNG, JPG, WEBP, BMP, TGA…")
        self._btn_browse_image = QPushButton("Browse…"); self._btn_browse_image.clicked.connect(self.browse_image_source)
        self._lbl_image_src = QLabel("Image File:")
        g.addWidget(self._lbl_image_src, r, 0)
        g.addWidget(self.inp_image_src, r, 1)
        g.addWidget(self._btn_browse_image, r, 2)
        r += 1

        self.inp_start = QLineEdit("0")
        self._lbl_start = QLabel("Start Time (s or mm:ss):")
        g.addWidget(self._lbl_start, r, 0)
        g.addWidget(self.inp_start, r, 1, 1, 2)
        r += 1

        self.inp_end = QLineEdit("30")
        self._lbl_end = QLabel("End Time (s or mm:ss):")
        g.addWidget(self._lbl_end, r, 0)
        g.addWidget(self.inp_end, r, 1, 1, 2)
        r += 1

        self.spn_fps = QSpinBox(); self.spn_fps.setRange(1, 120); self.spn_fps.setValue(DEFAULT_FPS)
        self._lbl_fps = QLabel("Extract FPS:")
        g.addWidget(self._lbl_fps, r, 0)
        g.addWidget(self.spn_fps, r, 1, 1, 2)
        r += 1

        # Anim Frames — auto-calculated, read-only display
        self._lbl_anim_frames = QLabel("Anim Frames:")
        self._anim_frames_lbl = QLabel("600")
        self._anim_frames_lbl.setStyleSheet("color:#7ec8e3; font-size:10px;")
        self._anim_frames_lbl.setToolTip("Auto-calculated: (End Time − Start Time) × Extract FPS")
        g.addWidget(self._lbl_anim_frames, r, 0)
        g.addWidget(self._anim_frames_lbl, r, 1, 1, 2)
        r += 1

        self.rdo_src_video.toggled.connect(self._toggle_source_type)
        self.rdo_src_youtube.toggled.connect(self._toggle_source_type)
        self.rdo_src_image.toggled.connect(self._toggle_source_type)
        self.inp_start.textChanged.connect(self._update_anim_frames_label)
        self.inp_end.textChanged.connect(self._update_anim_frames_label)
        self.spn_fps.valueChanged.connect(self._update_anim_frames_label)
        self._toggle_source_type()
        self._update_anim_frames_label()

        # ASSETS section header — stored so it can be hidden in Java Edition
        self._sep_assets = QFrame(); self._sep_assets.setFrameShape(QFrame.HLine)
        self._sep_assets.setStyleSheet("color:#444;")
        g.addWidget(self._sep_assets, r, 0, 1, 3); r += 1
        self._lbl_sec_assets = QLabel("ASSETS")
        self._lbl_sec_assets.setStyleSheet("font-weight:bold;color:#888;font-size:10px;padding-top:2px;")
        g.addWidget(self._lbl_sec_assets, r, 0, 1, 3); r += 1

        # Custom Container Background
        self._container_bg_images: dict = {fname: {"pil": None, "path": ""} for _, fname in CONTAINER_BG_SLOTS}
        self._lbl_container_bg       = QLabel("Custom Container Background:")
        self._container_bg_count_lbl = QLabel("0 custom")
        self._container_bg_count_lbl.setStyleSheet("color:#888; font-size:10px;")
        self._btn_container_bg_edit  = QPushButton("Edit")
        self._btn_container_bg_edit.setFixedWidth(110)
        self._btn_container_bg_edit.clicked.connect(self._open_container_bg_dialog)
        self._container_bg_row = QWidget()
        container_bg_h   = QHBoxLayout(self._container_bg_row)
        container_bg_h.setContentsMargins(0, 0, 0, 0)
        container_bg_h.setSpacing(6)
        container_bg_h.addWidget(self._container_bg_count_lbl)
        container_bg_h.addStretch()
        g.addWidget(self._lbl_container_bg, r, 0)
        g.addWidget(self._container_bg_row, r, 1)
        g.addWidget(self._btn_container_bg_edit, r, 2)
        r += 1
        self.inp_bgm = QLineEdit()
        self.inp_bgm.setPlaceholderText("(optional — leave blank to extract from video)")
        self.inp_bgm.setToolTip(
            "Pick an audio file (.ogg, .mp3, .wav, .flac, .m4a, .aac…).\nIf not .ogg, auto-converted to Vorbis OGG.\nLeave blank to extract audio from video."
        )
        self._btn_bgm = QPushButton("Browse…"); self._btn_bgm.clicked.connect(self.browse_bgm)
        self._lbl_bgm = QLabel("Background Music File:")
        g.addWidget(self._lbl_bgm, r, 0)
        g.addWidget(self.inp_bgm, r, 1)
        g.addWidget(self._btn_bgm, r, 2)
        r += 1

        self.inp_loading_bg = QLineEdit()
        self.inp_loading_bg.setPlaceholderText("← leave blank to use a black frame")
        self.inp_loading_bg.setToolTip(
            "Optional: select a folder of images for the loading screen.\n"
            "Leave blank → a single black frame is used automatically."
        )
        self._btn_lbg = QPushButton("Browse Folder…")
        self._btn_lbg.clicked.connect(self.browse_loading_bg)

        btn_lbg_clear = QPushButton("✖")
        btn_lbg_clear.setFixedWidth(26)
        btn_lbg_clear.setToolTip("Clear — use black frame")
        btn_lbg_clear.clicked.connect(lambda: self.inp_loading_bg.clear())

        self._lbg_btn_group = QWidget()
        lbg_btn_h = QHBoxLayout(self._lbg_btn_group)
        lbg_btn_h.setContentsMargins(0, 0, 0, 0)
        lbg_btn_h.setSpacing(2)
        lbg_btn_h.addWidget(self._btn_lbg)
        lbg_btn_h.addWidget(btn_lbg_clear)

        self._lbl_loading_bg = QLabel("Loading Background:")
        g.addWidget(self._lbl_loading_bg, r, 0)
        g.addWidget(self.inp_loading_bg, r, 1)
        g.addWidget(self._lbg_btn_group, r, 2)
        r += 1

        self.inp_loading_bg.textChanged.connect(self._dummy_load_frames_compat)

        _sec("COMPRESSION")
        self.cmb_compress = QComboBox()
        self._compress_methods = [
            "None", "Lossless", "Pillow", "FFmpeg", "TinyPNG",
            "Kraken", "ImageKit", "Cloudinary",
            "Imagecompressr", "Compressor",
        ]
        self.cmb_compress.addItems(self._compress_methods)
        self.cmb_compress.setCurrentText("None")
        _row("Method:", self.cmb_compress)

        self._api_stack = QStackedWidget()
        self._api_stack.setFrameShape(QStackedWidget.StyledPanel)

        def make_panel(rows):
            w = QWidget()
            fl = QFormLayout(w)
            fl.setContentsMargins(8, 6, 8, 6)
            fl.setSpacing(5)
            for lb, wg in rows:
                fl.addRow(lb, wg)
            return w

        # Index 0 — None (no settings shown)
        _nw = QWidget(); self._api_stack.addWidget(_nw)

        _lw = QWidget(); _ll = QLabel("No configuration needed.")
        _ll.setStyleSheet("color:grey;font-style:italic;")
        QVBoxLayout(_lw).addWidget(_ll); self._api_stack.addWidget(_lw)

        self.cmb_pillow_q = QComboBox()
        self.cmb_pillow_q.addItems(["Low", "Medium", "High", "Maximum"])
        self.cmb_pillow_q.setCurrentText("High")
        self._api_stack.addWidget(make_panel([("Quality:", self.cmb_pillow_q)]))

        self.spn_ff_qv = QSpinBox(); self.spn_ff_qv.setRange(1, 31); self.spn_ff_qv.setValue(1)
        self._api_stack.addWidget(make_panel([("QV (1=best, 31=worst):", self.spn_ff_qv)]))

        self.inp_tinify = QLineEdit(); self.inp_tinify.setPlaceholderText("TinyPNG API Key")
        self.inp_tinify.setEchoMode(QLineEdit.Password)
        self._api_stack.addWidget(make_panel([("API Key:", self.inp_tinify)]))

        self.inp_kraken  = QLineEdit(); self.inp_kraken.setPlaceholderText("API Key")
        self.inp_kraken.setEchoMode(QLineEdit.Password)
        self.inp_krakens = QLineEdit(); self.inp_krakens.setPlaceholderText("API Secret")
        self.inp_krakens.setEchoMode(QLineEdit.Password)
        self.spn_kraken_q = QSpinBox(); self.spn_kraken_q.setRange(1, 100); self.spn_kraken_q.setValue(90)
        self._api_stack.addWidget(make_panel([
            ("API Key:",    self.inp_kraken),
            ("API Secret:", self.inp_krakens),
            ("Quality:",    self.spn_kraken_q),
        ]))

        self.inp_imagekit  = QLineEdit(); self.inp_imagekit.setPlaceholderText("Public Key")
        self.inp_imagekits = QLineEdit(); self.inp_imagekits.setPlaceholderText("Private Key")
        self.inp_imagekits.setEchoMode(QLineEdit.Password)
        self.inp_imagekitp = QLineEdit(); self.inp_imagekitp.setPlaceholderText("https://ik.imagekit.io/yourname")
        self.inp_imagekitq = QSpinBox(); self.inp_imagekitq.setRange(1, 100); self.inp_imagekitq.setValue(90)
        self._api_stack.addWidget(make_panel([
            ("Public Key:",   self.inp_imagekit),
            ("Private Key:",  self.inp_imagekits),
            ("URL Endpoint:", self.inp_imagekitp),
            ("Quality:",      self.inp_imagekitq),
        ]))

        self.inp_cloudinary  = QLineEdit(); self.inp_cloudinary.setPlaceholderText("Cloud Name")
        self.inp_cloudinaryk = QLineEdit(); self.inp_cloudinaryk.setPlaceholderText("API Key")
        self.inp_cloudinaryk.setEchoMode(QLineEdit.Password)
        self.inp_cloudinarys = QLineEdit(); self.inp_cloudinarys.setPlaceholderText("API Secret")
        self.inp_cloudinarys.setEchoMode(QLineEdit.Password)
        self.cmb_cloudinaryq = QComboBox()
        self.cmb_cloudinaryq.addItems(["auto", "auto:best", "auto:good", "auto:eco", "auto:low"])
        self.cmb_cloudinaryq.setCurrentText("auto:best")
        self._api_stack.addWidget(make_panel([
            ("Cloud Name:",  self.inp_cloudinary),
            ("API Key:",     self.inp_cloudinaryk),
            ("API Secret:",  self.inp_cloudinarys),
            ("Quality:",     self.cmb_cloudinaryq),
        ]))

        _iw = QWidget(); _il = QLabel("Uses headless Chrome – no API key required.")
        _il.setStyleSheet("color:grey;font-style:italic;"); _il.setWordWrap(True)
        QVBoxLayout(_iw).addWidget(_il); self._api_stack.addWidget(_iw)

        _cw = QWidget(); _cl = QLabel("Uses headless Chrome – no API key required.")
        _cl.setStyleSheet("color:grey;font-style:italic;"); _cl.setWordWrap(True)
        QVBoxLayout(_cw).addWidget(_cl); self._api_stack.addWidget(_cw)

        def _on_method(text):
            idx = self._compress_methods.index(text) if text in self._compress_methods else 0
            self._api_stack.setCurrentIndex(idx)
            api_grp.setVisible(text != "None")

        api_grp = QGroupBox("Compression Settings")
        _ag = QVBoxLayout(api_grp); _ag.setContentsMargins(4, 4, 4, 4)
        _ag.addWidget(self._api_stack)
        g.addWidget(api_grp, r, 0, 1, 3); r += 1

        self.cmb_compress.currentTextChanged.connect(_on_method)
        _on_method(self.cmb_compress.currentText())

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(14)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(
            "QProgressBar{border:1px solid #555;border-radius:3px;background:#2a2a2a;}"
            "QProgressBar::chunk{background:#27ae60;border-radius:2px;}"
        )
        left_vbox.addWidget(self.progress_bar)

        splitter.addWidget(left_outer)

        right_widget = QWidget()
        self._right_widget = right_widget
        right_widget.setMinimumWidth(180)
        right_vbox = QVBoxLayout(right_widget)
        right_vbox.setContentsMargins(0, 0, 0, 0)
        right_vbox.setSpacing(4)

        log_hdr = QLabel("Build Log")
        log_hdr.setStyleSheet("font-weight:bold;font-size:12px;padding:2px 0;")
        right_vbox.addWidget(log_hdr)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setStyleSheet(
            "QTextEdit{background:#1e1e1e;color:#d4d4d4;"
            "font-family:'Courier New',Monospace;font-size:10px;"
            "border:1px solid #444;border-radius:4px;padding:4px;}"
        )
        right_vbox.addWidget(self.log_box, stretch=1)

        self.lbl_status = QLabel()
        self.lbl_status.setText(
            "<span style='color:#888;font-size:10px;'>"
            "ⓘ This script is licensed under GNU v3 License."
            "</span><br>"
            "<span style='color:#666;font-size:10px;'>"
            "Made with ♥ for Hans Community!"
            "</span>"
        )
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet(
            "border-top:1px solid #333; padding:4px 4px 2px 4px;"
        )
        right_vbox.addWidget(self.lbl_status)

        splitter.addWidget(right_widget)
        self._splitter_default_sizes = [520, 360]
        splitter.setSizes(self._splitter_default_sizes)
        # Apply initial "Show build logs" setting.
        _s = _load_settings()
        self._apply_build_logs(_s.get("show_build_logs", True), persist=False)

    def _current_edition(self) -> str:
        """Returns 'bedrock' or 'java'."""
        return "java" if self._outer_tab_widget.currentIndex() == 1 else "bedrock"

    def _current_ui_mode(self) -> str:
        """Returns 'horizon' or 'neko'. Java Edition always returns 'horizon' (shared structure)."""
        if self._current_edition() == "java":
            return "horizon"
        return "neko" if self._bedrock_tab_widget.currentIndex() == 1 else "horizon"

    def _toggle_java_fields(self):
        """Hide BGM, Loading BG, ASSETS section, and Container BG when Java Edition is active."""
        if not hasattr(self, "_sep_assets"):
            return
        is_java = (self._current_edition() == "java")
        for w in (self._sep_assets, self._lbl_sec_assets,
                  self._lbl_container_bg, self._container_bg_row, self._btn_container_bg_edit,
                  self._lbl_bgm, self.inp_bgm, self._btn_bgm,
                  self._lbl_loading_bg, self.inp_loading_bg, self._lbg_btn_group):
            w.setVisible(not is_java)

    def _open_container_bg_dialog(self):
        dlg = ContainerBgDialog(self._container_bg_images, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            # slot_data is mutated in-place by dlg._apply()
            n = sum(1 for v in self._container_bg_images.values()
                    if v and v.get("pil") is not None)
            self._container_bg_count_lbl.setText(f"{n} custom" if n else "0 custom")
            self._container_bg_count_lbl.setStyleSheet(
                ("color:#7ec8e3;" if n else "color:#888;") + " font-size:10px;"
            )
            if _IS_DEBUG:
                self.append_log(f"[DEBUG] Container background(s) updated: {n} custom")

    def _on_outer_tab_changed(self, _index: int):
        if not hasattr(self, "btn_run"):
            return
        if _IS_DEBUG and hasattr(self, "log_box"):
            self.append_log(f"[DEBUG] Edition changed → {self._current_edition()}")
        self._toggle_java_fields()
        self._update_build_button()

    def _on_tab_changed(self, _index: int):
        """Called when either inner tab widget changes."""
        if not hasattr(self, "btn_run"):
            return
        if _IS_DEBUG and hasattr(self, "log_box"):
            self.append_log(
                f"[DEBUG] UI tab changed → {self._current_edition()} / {self._current_ui_mode()}"
            )
        self._update_build_button()

    def _update_build_button(self):
        edition = self._current_edition()
        ui_mode = self._current_ui_mode()
        if edition == "java":
            line1 = "Build zip"
            line2 = f"Java / both UI"
        else:
            line1 = "Build mcpack"
            line2 = f"Bedrock / {'NekoUI' if ui_mode == 'neko' else 'HorizonUI'}"
        self.btn_run.setText(f"{line1}\n({line2})")

    def _open_format_dialog(self, target_field: "QLineEdit"):
        before = target_field.text()
        dlg = McFormatDialog(target_field, parent=self)
        dlg.exec_()
        after = target_field.text()
        if _IS_DEBUG and after != before:
            field_name = "pack name" if target_field is getattr(self, "inp_packname", None) else \
                ("creator" if target_field is getattr(self, "inp_creator", None) else "field")
            self.append_log(f"[DEBUG] Format dialog changed {field_name}: {before!r} → {after!r}")
            if field_name == "pack name" and hasattr(self, "_dbg_last_packname"):
                self._dbg_last_packname = after
            elif field_name == "creator" and hasattr(self, "_dbg_last_creator"):
                self._dbg_last_creator = after

    def _update_anim_frames_label(self, *_):
        """Recompute Anim Frames = (End - Start) * FPS and update the label."""
        if not hasattr(self, "_anim_frames_lbl"):
            return
        try:
            start = Worker.parse_time(self.inp_start.text().strip()) or 0
            end   = Worker.parse_time(self.inp_end.text().strip())   or 30
            fps   = self.spn_fps.value()
            n = max(1, int((end - start) * fps))
            self._anim_frames_lbl.setText(str(n))
            self._anim_frames_lbl.setStyleSheet("color:#7ec8e3; font-size:10px;")
        except Exception:
            self._anim_frames_lbl.setText("?")
            self._anim_frames_lbl.setStyleSheet("color:#e07070; font-size:10px;")

    def _dummy_load_frames_compat(self, *_):
        pass

    def _toggle_load_frames_row(self, *_):
        """No-op — Loading Frames row removed."""
        pass

    def _browse_yt_cookiefile(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Select cookies.txt",
            filter="Cookies file (*.txt);;All Files (*)"
        )
        if f:
            before = self.inp_yt_cookiefile.text().strip()
            self.inp_yt_cookiefile.setText(f)
            if _IS_DEBUG and f != before:
                self.append_log(f"[DEBUG] cookies.txt changed: {before!r} → {f!r}")

    def browse_video(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select Video", filter="Video (*.mp4 *.mov *.mkv *.avi *.webm *.m4v)")
        if f:
            before = self.inp_video.text().strip()
            self.inp_video.setText(f)
            if _IS_DEBUG and f != before:
                self.append_log(f"[DEBUG] Source video changed: {before!r} → {f!r}")

    def browse_image_source(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Select Background Image",
            filter="Images (*.png *.jpg *.jpeg *.webp *.bmp *.tga);;All Files (*)"
        )
        if f:
            before = self.inp_image_src.text().strip()
            self.inp_image_src.setText(f)
            if _IS_DEBUG and f != before:
                self.append_log(f"[DEBUG] Source background image changed: {before!r} → {f!r}")

    def _toggle_source_type(self, _checked=None):
        """Show/hide rows depending on source type (Video / YouTube / Image)."""
        is_video   = self.rdo_src_video.isChecked()
        is_youtube = self.rdo_src_youtube.isChecked()
        is_image   = self.rdo_src_image.isChecked()
        mode = "Video" if is_video else ("YouTube" if is_youtube else "Image")
        if _IS_DEBUG and hasattr(self, "_lbl_video") and hasattr(self, "log_box"):
            self.append_log(f"[DEBUG] Source type changed → {mode}")
        is_video_like = is_video or is_youtube  # both show time/fps/frames

        for w in (self._lbl_video, self.inp_video, self._btn_browse_video):
            w.setVisible(is_video)
        for w in (self._lbl_yt_url, self.inp_yt_url,
                  self._lbl_yt_cookies, self._yt_cookies_row):
            w.setVisible(is_youtube)
        for w in (self._lbl_image_src, self.inp_image_src, self._btn_browse_image):
            w.setVisible(is_image)
        for w in (self._lbl_start, self.inp_start,
                  self._lbl_end, self.inp_end,
                  self._lbl_fps, self.spn_fps,
                  self._lbl_anim_frames, self._anim_frames_lbl):
            w.setVisible(is_video_like)
        if hasattr(self, "rdo_static"):
            self.rdo_dynamic.setEnabled(is_video_like)
            self.rdo_both.setEnabled(is_video_like)
            if is_image:
                self.rdo_static.setChecked(True)

    def _load_pack_from_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Pack File",
            filter="Pack Files (*.mcpack *.zip);;All Files (*)"
        )
        if not path:
            return
        if _IS_DEBUG:
            self.append_log(f"[DEBUG] Load pack selected: {path}")

        try:
            self._do_load_pack(Path(path))
        except Exception as e:
            QMessageBox.warning(self, "Load Failed", f"Could not load pack:\n{e}")

    def _do_load_pack(self, pack_path: Path):
        import zipfile as _zf
        import json as _json

        if not _zf.is_zipfile(str(pack_path)):
            raise ValueError("File is not a valid ZIP/mcpack archive.")

        with _zf.ZipFile(str(pack_path), "r") as zf:
            names = zf.namelist()

            # ── Detect edition & UI type ───────────────────────────────────────
            has_manifest   = any(n.endswith("manifest.json") and n.count("/") == 0 for n in names)
            has_mcmeta     = any(n.endswith("pack.mcmeta")   and n.count("/") == 0 for n in names)
            has_horizon    = any("hrzn_animated_background" in n for n in names)
            has_neko_anim  = any("neko_ui_public_animated_background" in n for n in names)
            has_java_bg    = any("assets/nekoui/background" in n for n in names)

            is_java        = has_mcmeta or has_java_bg
            is_neko        = has_neko_anim or (has_java_bg)

            # ── Read metadata ─────────────────────────────────────────────────
            name    = ""
            creator = ""
            ver     = [1, 0, 0]

            if has_manifest and not is_java:
                raw = zf.read("manifest.json").decode("utf-8", errors="replace")
                data = _json.loads(raw)
                hdr  = data.get("header", {})
                raw_name = hdr.get("name", "")
                # Strip Minecraft formatting codes §x
                name = re.sub(r"§.", "", raw_name)
                # Strip known UI prefixes
                for prefix in ("HorizonUI: ", "NekoUI: ", "Horizon UI: ", "Neko UI: "):
                    if name.startswith(prefix):
                        name = name[len(prefix):]
                        break
                ver_list = hdr.get("version", [1, 0, 0])
                ver = [int(v) for v in ver_list[:3]]
                # Try to get creator from module description
                desc = hdr.get("description", "")
                m = re.search(r"Extension Creator\s*:\s*(.+)", desc)
                if m:
                    creator = m.group(1).strip()

            elif has_mcmeta and is_java:
                raw  = zf.read("pack.mcmeta").decode("utf-8", errors="replace")
                data = _json.loads(raw)
                desc = data.get("pack", {}).get("description", "")
                # Format: "§fNekoUI AB - {name} (v{x}.{y}.{z}) - by {creator}"
                m = re.search(r"NekoUI AB\s*-\s*(.+?)\s*\(v(\d+)\.(\d+)\.(\d+)\)\s*-\s*by\s*(.+)", desc)
                if m:
                    name    = m.group(1).strip()
                    ver     = [int(m.group(2)), int(m.group(3)), int(m.group(4))]
                    creator = m.group(5).strip()
                else:
                    # Fallback: strip formatting and use as name
                    name = re.sub(r"§.", "", desc).strip()

            # ── Count frames ──────────────────────────────────────────────────
            _IMG = {".png", ".jpg", ".jpeg", ".webp"}
            if is_java:
                anim_frames = sum(1 for n in names
                    if "assets/nekoui/background" in n
                    and Path(n).suffix.lower() in _IMG)
            elif is_neko:
                anim_frames = sum(1 for n in names
                    if "neko_ui_public_animated_background/" in n
                    and Path(n).suffix.lower() in _IMG
                    and "blur" not in Path(n).name)
            else:
                anim_frames = sum(1 for n in names
                    if "hrzn_animated_background/" in n
                    and Path(n).suffix.lower() in _IMG
                    and "blur" not in Path(n).name)

        # ── Apply to form ─────────────────────────────────────────────────────
        if name:
            self.inp_packname.setText(name)
        if creator:
            self.inp_creator.setText(creator)
        self.spn_ver_x.setValue(ver[0])
        self.spn_ver_y.setValue(ver[1])
        self.spn_ver_z.setValue(ver[2])

        # Switch to correct edition tab
        if is_java:
            self._outer_tab_widget.setCurrentIndex(1)
        else:
            self._outer_tab_widget.setCurrentIndex(0)

        # Switch to correct UI tab
        inner = self._java_tab_widget if is_java else self._bedrock_tab_widget
        inner.setCurrentIndex(1 if is_neko else 0)

        # Build summary
        edition_str = "Java Edition" if is_java else "Bedrock Edition"
        ui_str      = "NekoUI" if is_neko else "HorizonUI"
        frames_str  = f"{anim_frames} anim frame(s) detected" if anim_frames else "no frames detected"
        if _IS_DEBUG:
            self.append_log(
                "[DEBUG] Pack metadata loaded: "
                f"{edition_str} / {ui_str}, name={name or '(unknown)'}, creator={creator or '(unknown)'}, "
                f"ver={ver[0]}.{ver[1]}.{ver[2]}, frames={frames_str}, file={pack_path.name}"
            )
        QMessageBox.information(
            self, "Pack Loaded",
            f"Loaded: {pack_path.name}\n\n"
            f"Edition : {edition_str}\n"
            f"UI Type : {ui_str}\n"
            f"Name    : {name or '(unknown)'}\n"
            f"Creator : {creator or '(unknown)'}\n"
            f"Version : {ver[0]}.{ver[1]}.{ver[2]}\n"
            f"Frames  : {frames_str}\n\n"
            "Note: source video/image is not restored.\n"
            "You can edit metadata and rebuild."
        )

    def browse_output(self):
        d = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if d:
            before = self.inp_output.text().strip()
            self.inp_output.setText(d)
            if _IS_DEBUG and d != before:
                self.append_log(f"[DEBUG] Output folder changed: {before!r} → {d!r}")

    def browse_loading_bg(self):
        d = QFileDialog.getExistingDirectory(self, "Select Folder Containing Loading Background Images")
        if d:
            before = self.inp_loading_bg.text().strip()
            self.inp_loading_bg.setText(d)
            if _IS_DEBUG and d != before:
                self.append_log(f"[DEBUG] Loading BG folder changed: {before!r} → {d!r}")

    def browse_bgm(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Select Background Music File",
            filter="Audio Files (*.ogg *.mp3 *.wav *.flac *.m4a *.aac *.opus *.wma *.aiff);;All Files (*)"
        )
        if f:
            before = self.inp_bgm.text().strip()
            self.inp_bgm.setText(f)
            if _IS_DEBUG and f != before:
                self.append_log(f"[DEBUG] BGM file changed: {before!r} → {f!r}")

    def browse_pack_icon(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Select Pack Icon (PNG)",
            filter="PNG Images (*.png);;All Files (*)"
        )
        if not f:
            return
        if _IS_DEBUG:
            self.append_log(f"[DEBUG] Pack icon selection: {f}")

        src = Path(f)

        if src.stem.lower() == "pack_icon":
            self._pack_icon_pil  = None
            self._pack_icon_path = f
            self.inp_pack_icon.setText(f"[pack_icon] {src.name}")
            self._update_icon_thumb_from_path(f)
            if _IS_DEBUG:
                self.append_log(f"[DEBUG] Pack icon set from existing 'pack_icon': {src.name}")
            return

        dlg = PackIconCropDialog(f, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            result_img = dlg.get_result()
            if result_img is not None:
                self._pack_icon_pil  = result_img
                self._pack_icon_path = f
                self.inp_pack_icon.setText(f"[cropped] {src.name}")
                self._update_icon_thumb_from_pil(result_img)
                if _IS_DEBUG:
                    self.append_log(f"[DEBUG] Pack icon set (cropped): {src.name}")

    def clear_pack_icon(self):
        self._pack_icon_pil  = None
        self._pack_icon_path = ""
        if _IS_DEBUG:
            self.append_log("[DEBUG] Pack icon cleared")
        self.inp_pack_icon.clear()
        self._icon_thumb.clear()
        self._icon_thumb.setPixmap(QPixmap())

    def _update_icon_thumb_from_path(self, path: str):
        px = QPixmap(path).scaled(
            34, 34, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self._icon_thumb.setPixmap(px)

    def _update_icon_thumb_from_pil(self, img: "Image.Image"):
        thumb = img.resize((34, 34), Image.LANCZOS)
        data  = thumb.tobytes("raw", "RGBA")
        qimg  = QtGui.QImage(data, 34, 34, QtGui.QImage.Format_RGBA8888)
        self._icon_thumb.setPixmap(QPixmap.fromImage(qimg))

    def append_log(self, s: str):
        self.log_box.append(s)
        self.log_box.moveCursor(QtGui.QTextCursor.End)

    def run_process(self):
        is_image_mode   = self.rdo_src_image.isChecked()
        is_youtube_mode = self.rdo_src_youtube.isChecked()

        if is_image_mode:
            video = self.inp_image_src.text().strip()
        elif is_youtube_mode:
            video = self.inp_yt_url.text().strip()
        else:
            video = self.inp_video.text().strip()

        output = self.inp_output.text().strip()
        name   = self.inp_packname.text().strip()

        if not video or not output or not name:
            QMessageBox.warning(self, "Missing Fields",
                "Please fill in Source, Output Folder, and Extension Name.")
            return

        if is_youtube_mode and not self.inp_yt_cookiefile.text().strip():
            QMessageBox.warning(self, "Missing Fields",
                "A cookies.txt file is required for YouTube sources.\n"
                "Please browse to your cookies.txt file.")
            return

        if is_image_mode and not self.inp_bgm.text().strip() and self._current_edition() != "java":
            QMessageBox.warning(self, "Missing Fields",
                "Background Music File is required when using an image source.\n"
                "Please select a BGM file.")
            return

        if not is_image_mode:
            try:
                start = Worker.parse_time(self.inp_start.text().strip())
                end   = Worker.parse_time(self.inp_end.text().strip())
            except ValueError as e:
                QMessageBox.warning(self, "Time Error", str(e)); return
            if end is not None and start is not None and end <= start:
                QMessageBox.warning(self, "Time Error", "End Time must be greater than Start Time."); return
        else:
            start = None
            end   = None

        cfg = {
            "video_path":           video,
            "source_is_image":      is_image_mode,
            "source_is_youtube":    is_youtube_mode,
            "yt_cookies_browser":   "",
            "yt_cookies_file":      self.inp_yt_cookiefile.text().strip() if is_youtube_mode else "",
            "output_folder":    output,
            "new_pack_name":    name,
            "creator":          self.inp_creator.text().strip(),
            "bgm_file":         self.inp_bgm.text().strip(),
            "bgm_name":         Path(self.inp_bgm.text().strip()).stem if self.inp_bgm.text().strip() else "background_music",
            "start_seconds":    start,
            "end_seconds":      end,
            "fps":              self.spn_fps.value(),
            "anim_frames":      max(1, int(self._anim_frames_lbl.text()) if self._anim_frames_lbl.text().isdigit() else 100),
            "load_frames":      1,
            "use_black_loading": not self.inp_loading_bg.text().strip(),
            "compress_method":  self.cmb_compress.currentText(),
            "tinify_key":       self.inp_tinify.text().strip(),
            "kraken_key":       self.inp_kraken.text().strip(),
            "kraken_secret":    self.inp_krakens.text().strip(),
            "kraken_quality":   self.spn_kraken_q.value(),
            "imagekit_key":     self.inp_imagekit.text().strip(),
            "imagekit_secret":  self.inp_imagekits.text().strip(),
            "imagekit_urlendpoint": self.inp_imagekitp.text().strip(),
            "imagekit_quality": self.inp_imagekitq.value(),
            "cloudinary_name":  self.inp_cloudinary.text().strip(),
            "cloudinary_key":   self.inp_cloudinaryk.text().strip(),
            "cloudinary_secret":self.inp_cloudinarys.text().strip(),
            "cloudinary_quality":"auto:best",
            "ffmpeg_qv":        self.spn_ff_qv.value(),
            "pillow_quality":   self.cmb_pillow_q.currentText().lower(),
            "loading_bg_folder": self.inp_loading_bg.text().strip(),
            "container_bg_images": self._container_bg_images,
            "pack_icon_pil":    self._pack_icon_pil,
            "pack_icon_path":   self._pack_icon_path,
            "ext_ver_x":        self.spn_ver_x.value(),
            "ext_ver_y":        self.spn_ver_y.value(),
            "ext_ver_z":        self.spn_ver_z.value(),
            "bg_mode":          ("static" if self.rdo_static.isChecked()
                                 else "both" if self.rdo_both.isChecked()
                                 else "dynamic"),
        }

        self.btn_run.setVisible(False)
        self.btn_cancel.setVisible(True)
        self.btn_cancel.setEnabled(True)
        self._btn_open_pack.setEnabled(False)
        if hasattr(self, "_btn_about"):
            self._btn_about.setEnabled(False)
        self._form_widget.setEnabled(False)
        self.progress_bar.setValue(0)
        edition = self._current_edition()
        ui_mode = self._current_ui_mode()
        if edition == "java":
            self.worker = JavaWorker(cfg)
            mode_label  = f"Java / {'NekoUI' if ui_mode == 'neko' else 'HorizonUI'}"
        elif ui_mode == "neko":
            self.worker = NekoWorker(cfg)
            mode_label  = "Bedrock / NekoUI"
        else:
            self.worker = Worker(cfg)
            mode_label  = "Bedrock / HorizonUI"
        if _IS_DEBUG:
            pack_icon_src = (
                cfg.get("pack_icon_path", "") if cfg.get("pack_icon_path", "").strip()
                else ("in-memory PIL" if cfg.get("pack_icon_pil") is not None else "")
            )
            self.append_log(
                "[DEBUG] Build prepared: "
                f"{mode_label}; source={{image:{is_image_mode}, youtube:{is_youtube_mode}}}; "
                f"video_or_img={cfg.get('video_path','')!r}; output={cfg.get('output_folder','')!r}; "
                f"name={cfg.get('new_pack_name','')!r}; creator={cfg.get('creator','')!r}; "
                f"bgm={cfg.get('bgm_file','')!r}; pack_icon={pack_icon_src!r}"
            )
        self.worker.log_signal.connect(self.append_log)
        self.worker.done_signal.connect(self.on_done)
        self.worker.progress_signal.connect(self.progress_bar.setValue)
        self.worker.show_order_dialog.connect(self._on_show_order_dialog)
        self.append_log(f"=== Starting [{mode_label}] ===")
        self.worker.start()

    def _on_show_order_dialog(self, path_strings: list):
        images = [Path(p) for p in path_strings]
        dlg = ImageOrderDialog(images, parent=self)
        if dlg.exec_() == dlg.Accepted:
            ordered = dlg.ordered_paths()
        else:
            ordered = []
        if self.worker:
            self.worker._deliver_order(ordered)

    def cancel_process(self):
        if self.worker and self.worker.isRunning():
            if QMessageBox.question(self, "Cancel?", "Cancel the running process?",
                                    QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                self.worker.stop()
                self.worker.wait()
                self.append_log("=== Cancelled ===")
                self._form_widget.setEnabled(True)
                self.btn_run.setVisible(True)
                self.btn_cancel.setVisible(False)
                self.btn_cancel.setEnabled(False)
                self._btn_open_pack.setEnabled(True)
                if hasattr(self, "_btn_about"):
                    self._btn_about.setEnabled(True)

    def on_done(self, ok: bool, msg: str):
        self.append_log(f"=== {'Done' if ok else 'Error'} ===")
        self._form_widget.setEnabled(True)
        self.btn_run.setVisible(True)
        self.btn_cancel.setVisible(False)
        self.btn_cancel.setEnabled(False)
        self._btn_open_pack.setEnabled(True)
        if hasattr(self, "_btn_about"):
            self._btn_about.setEnabled(True)
        self.progress_bar.setValue(100 if ok else 0)
        self._update_build_button()
        (QMessageBox.information if ok else QMessageBox.critical)(self, "Result", msg)

    def _show_settings_menu(self):
        from PyQt5.QtWidgets import QMenu, QWidgetAction
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { padding: 4px; }"
            "QMenu::item { padding: 4px 16px; }"
            "QMenu::item:selected { background: #2a2a3e; }"
        )

        # ── Options section ───────────────────────────────────────────────────
        options_title = QLabel("  Options")
        options_title.setStyleSheet("font-weight:bold; color:#888; font-size:10px; padding: 2px 8px;")
        title_action = QWidgetAction(menu)
        title_action.setDefaultWidget(options_title)
        menu.addAction(title_action)

        self._chk_transparent = QCheckBox("  Enable Window Transparent")
        _s = _load_settings()
        self._chk_transparent.setChecked(_s.get("transparent", self.windowOpacity() < 1.0))
        self._chk_transparent.toggled.connect(self._apply_transparency)
        act_transparent = QWidgetAction(menu)
        act_transparent.setDefaultWidget(self._chk_transparent)
        menu.addAction(act_transparent)

        self._chk_debug = QCheckBox("  Show more DEBUG logs")
        self._chk_debug.setChecked(_s.get("debug", _IS_DEBUG))
        self._chk_debug.toggled.connect(self._apply_debug)
        act_debug = QWidgetAction(menu)
        act_debug.setDefaultWidget(self._chk_debug)
        menu.addAction(act_debug)

        self._chk_show_build_logs = QCheckBox("  Show build logs")
        self._chk_show_build_logs.setChecked(_s.get("show_build_logs", True))
        self._chk_show_build_logs.toggled.connect(
            lambda checked: self._apply_build_logs(checked, persist=True)
        )
        act_logs = QWidgetAction(menu)
        act_logs.setDefaultWidget(self._chk_show_build_logs)
        menu.addAction(act_logs)

        menu.exec_(self._btn_settings.mapToGlobal(
            self._btn_settings.rect().bottomLeft()
        ))

    def _apply_transparency(self, checked: bool):
        self.setWindowOpacity(0.85 if checked else 1.0)
        s = _load_settings()
        s["transparent"] = checked
        _save_settings(s)

    def _apply_debug(self, checked: bool):
        global _IS_DEBUG
        _IS_DEBUG = checked
        s = _load_settings()
        s["debug"] = checked
        _save_settings(s)
        # Log the toggle itself so users see the effect immediately.
        if checked:
            try:
                self.append_log("[DEBUG] Show more DEBUG logs enabled")
            except Exception:
                pass

    def _apply_build_logs(self, checked: bool, persist: bool = True):
        """Show/hide the Build Log panel (right side)."""
        if persist:
            s = _load_settings()
            s["show_build_logs"] = checked
            _save_settings(s)

        if not hasattr(self, "_right_widget") or not hasattr(self, "_splitter"):
            return

        if checked:
            self._right_widget.setVisible(True)
            self._right_widget.setMinimumWidth(180)
            self.setMinimumWidth(860)
            self._splitter.setSizes(self._splitter_default_sizes)
        else:
            self._right_widget.setVisible(False)
            self._right_widget.setMinimumWidth(0)
            # Keep the window smaller when logs are hidden.
            self.setMinimumWidth(700)
            left_sz = self._splitter_default_sizes[0] if hasattr(self, "_splitter_default_sizes") else 520
            self._splitter.setSizes([left_sz, 0])
        self.adjustSize()

    def _show_about(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("About")
        dlg.setMinimumSize(480, 360)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        outer = QVBoxLayout(dlg)
        outer.setContentsMargins(0, 0, 0, 14)
        outer.setSpacing(10)

        # ── Banner image ──────────────────────────────────────────────────────
        self._about_banner_lbl = QLabel()
        self._about_banner_lbl.setFixedHeight(200)
        self._about_banner_lbl.setAlignment(Qt.AlignCenter)
        self._about_banner_lbl.setStyleSheet("background:#d7d7d7;")
        outer.addWidget(self._about_banner_lbl)

        # Use pre-fetched data (loaded at startup)
        if self._about_banner_data:
            px = QPixmap()
            px.loadFromData(self._about_banner_data)
            self._about_banner_lbl.setPixmap(
                px.scaled(480, 200, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            )

        # ── Info text ─────────────────────────────────────────────────────────
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(20, 0, 20, 0)

        ver = f"{config.get('VERSION', '?')}_{config.get('COMMIT', '?')}"
        info = QLabel(
            f"<b>TuBeo5866's HorizonUI/NekoUI Extension Studio</b><br>"
            f"<span style='color:#888;'>Version {ver}</span><br><br>"
            f"A GUI tool for building HorizonUI and NekoUI resource pack extensions<br>"
            f"for Minecraft Bedrock and Java editions.<br><br>"
            f"<span style='color:#888;'>Made with ♥ by TuBeo5866</span>"
        )
        info.setWordWrap(True)
        info.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        info_layout.addWidget(info, stretch=1)
        outer.addWidget(info_widget, stretch=1)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#444; margin: 0 20px;")
        outer.addWidget(sep)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(20, 0, 20, 0)

        def _link_btn(label, url):
            b = QPushButton(label)
            b.clicked.connect(lambda: __import__('webbrowser').open(url))
            return b

        btn_row.addWidget(_link_btn("Website",          "https://tubeo5866.com"))
        btn_row.addWidget(_link_btn("GitHub",            "https://github.com/usira-or-arisu/horizonui-and-nekoui-extension-studio"))
        btn_row.addWidget(_link_btn("Discord Support",   "https://discord.gg/3fe3ySCJZf"))
        btn_row.addWidget(_link_btn("Email Support",     "mailto:support@tubeo5866.com"))
        btn_row.addWidget(_link_btn("Request a Feature", "https://forms.gle/KTJQCq8EdseQhFKp9"))
        btn_row.addStretch()

        btn_ok = QPushButton("OK")
        btn_ok.setFixedWidth(70)
        btn_ok.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_ok)

        outer.addLayout(btn_row)
        dlg.exec_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_announcement_banner"):
            self._announcement_banner._reposition()
            self._announcement_banner.raise_()
    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            if QMessageBox.question(self, "Exit?", "A process is running. Exit anyway?",
                                    QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                self.worker.stop(); self.worker.wait(); event.accept()
            else:
                event.ignore()
        else:
            event.accept()

LICENSE_TEXT = """\
╔══════════════════════════════════════════════════════════════════════════════╗
║    TuBeo5866's HorizonUI/NekoUI Extension Studio — TERMS OF USE & LICENSE    ║
╚══════════════════════════════════════════════════════════════════════════════╝

Last updated: March 20, 2026

PLEASE READ THESE TERMS CAREFULLY BEFORE USING THIS SOFTWARE.
By clicking "I Agree" you confirm that you have read, understood, and accept
all terms listed below. If you do not agree, click "Decline" to exit.

───────────────────────────────────────────────────────────────────────────────
1. DEFINITIONS
───────────────────────────────────────────────────────────────────────────────
  • "Software"    — TuBeo5866's HorizonUI/NekoUI Extension Studio.
  • "Extension"   — Any .mcpack or .zip file produced by the Software.
  • "Original UI" — HorizonUI/NekoUI by Han's404 (YouTube: @zxyn404).
  • "You / User"  — Any individual or entity running the Software.

───────────────────────────────────────────────────────────────────────────────
2. GRANT OF LICENSE
───────────────────────────────────────────────────────────────────────────────
  The Software is provided free of charge for personal, non-commercial use,
  and it's licensed under the GNU General Public License version 3.0.
  You are permitted to:
    (a) Create Extensions for personal use and private distribution.
    (b) Share Extensions freely, PROVIDED the original credit is preserved
        (see Section 4).
    (c) Modify the Software's source code for your own non-commercial builds
        without permission.

───────────────────────────────────────────────────────────────────────────────
3. RESTRICTIONS
───────────────────────────────────────────────────────────────────────────────
  You may NOT:
    (a) Sell, sublicense, or commercially exploit the Software or Extensions
        generated by it without explicit written consent from the Original
        UI author (Han's404).
    (b) Remove, alter, or obscure any credits to Han's404 or the original
        HorizonUI project from the generated Extension files.
    (c) Use the Software to process video or audio content that you do not
        own or do not have the legal right to use (copyright law applies).
    (d) Distribute the Software itself under a different name or branding
        without permission.
    (e) Use the Software for any unlawful purpose.

───────────────────────────────────────────────────────────────────────────────
4. ATTRIBUTION REQUIREMENTS
───────────────────────────────────────────────────────────────────────────────
  Every Extension generated by this Software automatically embeds the
  following credit in its configuration and module description:

      "Original Creator : Han's404 | Youtube: @zxyn404 ( Han's )"

  You MUST NOT remove or modify this attribution line in any distributed
  Extension. Failure to comply constitutes a breach of this agreement.

───────────────────────────────────────────────────────────────────────────────
5. THIRD-PARTY TOOLS & CONTENT
───────────────────────────────────────────────────────────────────────────────
  The Software can download and invoke ffmpeg (LGPL/GPL), yt-dlp (Unlicense),
  and various Python packages. Each tool is subject to its own license.
  You are solely responsible for ensuring your use of those tools complies
  with their respective licenses and with applicable copyright law.

  In particular: downloading copyrighted YouTube videos for use in
  Minecraft resource packs may infringe on the rights of the content
  creator. Always obtain permission before using third-party content.

───────────────────────────────────────────────────────────────────────────────
6. DISCLAIMER OF WARRANTIES
───────────────────────────────────────────────────────────────────────────────
  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
  OR IMPLIED, INCLUDING BUT NOT LIMITED TO WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE, AND NON-INFRINGEMENT.
  THE AUTHORS SHALL NOT BE LIABLE FOR ANY CLAIM, DAMAGES, OR OTHER
  LIABILITY ARISING FROM THE USE OF THIS SOFTWARE.

───────────────────────────────────────────────────────────────────────────────
7. TERMINATION
───────────────────────────────────────────────────────────────────────────────
  This license is effective until terminated. It terminates automatically
  if you breach any of its terms. Upon termination you must cease all use
  and destroy all copies of the Software in your possession.

───────────────────────────────────────────────────────────────────────────────
8. GOVERNING LAW
───────────────────────────────────────────────────────────────────────────────
  These terms are governed by general principles of international software
  licensing. Any disputes shall be resolved in good faith between the parties.

───────────────────────────────────────────────────────────────────────────────
"""

_AGREED_FLAG   = Path.home() / ".tb5866_ext_studio_agreed_license"
_SETTINGS_FILE = Path.home() / ".tb5866_ext_studio_settings"


def _load_settings() -> dict:
    try:
        return json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_settings(data: dict):
    try:
        _SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[settings] Failed to save: {e}")

def _check_license(app: "QApplication") -> bool:
    if _AGREED_FLAG.exists():
        return True

    dlg = QDialog()
    dlg.setWindowTitle("TuBeo5866's HorizonUI/NekoUI Extension Studio — Terms of Use")
    dlg.setMinimumSize(780, 560)
    dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
    dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowCloseButtonHint)
    dlg._accepted = False

    layout = QVBoxLayout(dlg)
    layout.setSpacing(10)
    layout.setContentsMargins(18, 18, 18, 14)

    header = QLabel("Terms of Use & License Agreement")
    header_font = QFont()
    header_font.setPointSize(13)
    header_font.setBold(True)
    header.setFont(header_font)
    layout.addWidget(header)

    sub = QLabel(
        "Please read the following agreement carefully before using this software."
    )
    sub.setStyleSheet("color: #666; margin-bottom: 4px;")
    layout.addWidget(sub)

    line = QFrame(); line.setFrameShape(QFrame.HLine); line.setFrameShadow(QFrame.Sunken)
    layout.addWidget(line)

    txt = QTextEdit()
    txt.setReadOnly(True)
    txt.setPlainText(LICENSE_TEXT)
    mono = QFont("Courier New" if sys.platform.startswith("win") else "Monospace")
    mono.setPointSize(9)
    txt.setFont(mono)
    txt.setStyleSheet(
        "background:#1e1e1e; color:#d4d4d4; border:1px solid #444;"
        "border-radius:4px; padding:8px;"
    )
    layout.addWidget(txt, stretch=1)

    hint = QLabel("⬇  Scroll down to read the full agreement before accepting.")
    hint.setStyleSheet("color: #e07b00; font-size: 11px;")
    hint.setAlignment(Qt.AlignCenter)
    layout.addWidget(hint)

    def _on_scroll():
        sb = txt.verticalScrollBar()
        if sb.value() >= sb.maximum() - 10:
            hint.hide()
            chk.setEnabled(True)
    txt.verticalScrollBar().valueChanged.connect(_on_scroll)

    chk = QCheckBox(
        "I have read the Terms of Use and License Agreement above."
    )
    chk.setEnabled(False)
    chk.setStyleSheet("font-weight: bold; margin-top: 4px;")

    def _on_check(state):
        btn_agree.setEnabled(state == Qt.Checked)
    chk.stateChanged.connect(_on_check)
    layout.addWidget(chk)
    sub = QLabel(
        "By clicking 'I Agree' you acknowledge that:\n"
        "✔ You have read and understood all terms above.\n"
        "✔ You will respect the attribution requirements (Section 4).\n"
        "✔ You take full responsibility for the content you process.\n"
        "✔ You will not use this Software for commercial gain without permission."
    )
    sub.setStyleSheet("color: #666; margin-bottom: 4px;")
    layout.addWidget(sub)

    btn_layout = QHBoxLayout()
    btn_layout.addStretch()

    btn_decline = QPushButton("✖  I Decline")

    btn_agree = QPushButton("✔  I Agree")
    btn_agree.setEnabled(False)

    btn_layout.addWidget(btn_decline)
    btn_layout.addSpacing(8)
    btn_layout.addWidget(btn_agree)
    layout.addLayout(btn_layout)

    def _agree():
        dlg._accepted = True
        try:
            import datetime
            _AGREED_FLAG.write_text(
                f"agreed={datetime.datetime.now().isoformat()}\n"
                f"version=1\n",
                encoding="utf-8"
            )
        except Exception:
            pass
        dlg.accept()

    def _decline():
        dlg._accepted = False
        dlg.reject()

    btn_agree.clicked.connect(_agree)
    btn_decline.clicked.connect(_decline)

    def _close_event(event):
        dlg._accepted = False
        event.accept()
    dlg.closeEvent = _close_event

    dlg.exec_()
    return dlg._accepted

def main():
    global _IS_DEBUG
    app = QApplication(sys.argv)

    if not _check_license(app):
        sys.exit(0)

    settings = _load_settings()
    _IS_DEBUG = bool(settings.get("debug", False))
    w = MainWindow()
    if settings.get("transparent", True):
        w.setWindowOpacity(0.85)
    w.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
