#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, sys, json, shutil, subprocess, uuid, random, re, time, tempfile, zipfile, logging, stat
import urllib.request
from pathlib import Path
from abc import ABC, abstractmethod

# ─────────────────────────────────────────────────────────────
#  TOOL INSTALLER HELPERS
# ─────────────────────────────────────────────────────────────

def _tool_in_path(name: str) -> bool:
    try:
        subprocess.check_output([name, "--version"], stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False

def _add_to_path(directory: str):
    d = str(directory)
    if d not in os.environ.get("PATH", ""):
        os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")

# ── Windows ──────────────────────────────────────────────────

def _install_ffmpeg_windows() -> bool:
    print("[ffmpeg] Trying winget...")
    try:
        r = subprocess.run(
            ["winget", "install", "--id", "Gyan.FFmpeg", "-e", "--silent",
             "--accept-package-agreements", "--accept-source-agreements"],
            timeout=300, capture_output=True
        )
        if r.returncode == 0 and _tool_in_path("ffmpeg"):
            print("[ffmpeg] Installed via winget ✓"); return True
    except Exception: pass

    print("[ffmpeg] Trying scoop...")
    try:
        r = subprocess.run(["scoop", "install", "ffmpeg"], timeout=300, capture_output=True)
        if r.returncode == 0 and _tool_in_path("ffmpeg"):
            print("[ffmpeg] Installed via scoop ✓"); return True
    except Exception: pass

    print("[ffmpeg] Trying choco...")
    try:
        r = subprocess.run(["choco", "install", "ffmpeg", "-y"], timeout=300, capture_output=True)
        if r.returncode == 0 and _tool_in_path("ffmpeg"):
            print("[ffmpeg] Installed via choco ✓"); return True
    except Exception: pass

    # Direct ZIP download (ffmpeg-release-essentials from GitHub/BtbN)
    print("[ffmpeg] Downloading from GitHub (BtbN release)...")
    try:
        import urllib.request, zipfile as zf
        api_url = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest"
        with urllib.request.urlopen(api_url, timeout=30) as resp:
            data = json.loads(resp.read())
        # pick win64-gpl-shared essentials
        asset_url = next(
            a["browser_download_url"] for a in data["assets"]
            if "win64" in a["name"] and "gpl" in a["name"] and a["name"].endswith(".zip")
               and "shared" not in a["name"]
        )
        tmp_dir  = Path(tempfile.mkdtemp())
        zip_path = tmp_dir / "ffmpeg.zip"
        print(f"[ffmpeg] Downloading {asset_url} ...")
        urllib.request.urlretrieve(asset_url, zip_path)

        with zf.ZipFile(zip_path) as z:
            z.extractall(tmp_dir)

        # find ffmpeg.exe inside extracted folder
        ffmpeg_exe = next(tmp_dir.rglob("ffmpeg.exe"), None)
        if ffmpeg_exe:
            install_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ffmpeg_bin"
            install_dir.mkdir(parents=True, exist_ok=True)
            for exe in ("ffmpeg.exe", "ffprobe.exe", "ffplay.exe"):
                src = next(tmp_dir.rglob(exe), None)
                if src:
                    shutil.copy2(src, install_dir / exe)
            _add_to_path(str(install_dir))

            # Persist to user PATH via reg
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                    r"Environment", 0, winreg.KEY_ALL_ACCESS) as key:
                    cur, _ = winreg.QueryValueEx(key, "PATH")
                    if str(install_dir) not in cur:
                        winreg.SetValueEx(key, "PATH", 0, winreg.REG_EXPAND_SZ,
                                          cur + ";" + str(install_dir))
            except Exception: pass

            shutil.rmtree(tmp_dir, ignore_errors=True)
            if _tool_in_path("ffmpeg"):
                print("[ffmpeg] Installed via direct download ✓"); return True
    except Exception as e:
        print(f"[ffmpeg] Direct download failed: {e}")

    return False


def _install_ytdlp_windows() -> bool:
    print("[yt-dlp] Trying pip...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", "--upgrade", "yt-dlp"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        # pip installs yt-dlp script into Scripts folder – should already be in PATH
        if _tool_in_path("yt-dlp"):
            print("[yt-dlp] Installed via pip ✓"); return True
        # Fallback: locate & add Scripts dir
        scripts = Path(sys.executable).parent / "Scripts"
        if (scripts / "yt-dlp.exe").exists():
            _add_to_path(str(scripts))
            print("[yt-dlp] Installed via pip (Scripts added to PATH) ✓"); return True
    except Exception: pass

    print("[yt-dlp] Trying winget...")
    try:
        r = subprocess.run(
            ["winget", "install", "--id", "yt-dlp.yt-dlp", "-e", "--silent",
             "--accept-package-agreements", "--accept-source-agreements"],
            timeout=120, capture_output=True
        )
        if r.returncode == 0 and _tool_in_path("yt-dlp"):
            print("[yt-dlp] Installed via winget ✓"); return True
    except Exception: pass

    print("[yt-dlp] Trying scoop...")
    try:
        r = subprocess.run(["scoop", "install", "yt-dlp"], timeout=120, capture_output=True)
        if r.returncode == 0 and _tool_in_path("yt-dlp"):
            print("[yt-dlp] Installed via scoop ✓"); return True
    except Exception: pass

    # Direct .exe download
    print("[yt-dlp] Downloading .exe from GitHub...")
    try:
        exe_url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
        install_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ytdlp_bin"
        install_dir.mkdir(parents=True, exist_ok=True)
        exe_path = install_dir / "yt-dlp.exe"
        urllib.request.urlretrieve(exe_url, exe_path)
        _add_to_path(str(install_dir))
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Environment", 0, winreg.KEY_ALL_ACCESS) as key:
                cur, _ = winreg.QueryValueEx(key, "PATH")
                if str(install_dir) not in cur:
                    winreg.SetValueEx(key, "PATH", 0, winreg.REG_EXPAND_SZ,
                                      cur + ";" + str(install_dir))
        except Exception: pass
        if _tool_in_path("yt-dlp"):
            print("[yt-dlp] Installed via direct download ✓"); return True
    except Exception as e:
        print(f"[yt-dlp] Direct download failed: {e}")

    return False


# ── macOS ─────────────────────────────────────────────────────

def _install_ffmpeg_macos() -> bool:
    print("[ffmpeg] Trying brew...")
    try:
        # Ensure brew is on PATH
        for bp in ["/opt/homebrew/bin", "/usr/local/bin"]:
            _add_to_path(bp)
        r = subprocess.run(["brew", "install", "ffmpeg"], timeout=600, capture_output=True)
        if r.returncode == 0 and _tool_in_path("ffmpeg"):
            print("[ffmpeg] Installed via brew ✓"); return True
    except Exception: pass

    print("[ffmpeg] Trying port (MacPorts)...")
    try:
        r = subprocess.run(["port", "install", "ffmpeg"], timeout=600, capture_output=True)
        if r.returncode == 0 and _tool_in_path("ffmpeg"):
            print("[ffmpeg] Installed via MacPorts ✓"); return True
    except Exception: pass

    # Static build from evermeet.cx
    print("[ffmpeg] Downloading static build from evermeet.cx...")
    try:
        url = "https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip"
        tmp = Path(tempfile.mkdtemp())
        zip_path = tmp / "ffmpeg.zip"
        urllib.request.urlretrieve(url, zip_path)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(tmp)
        install_dir = Path.home() / ".local" / "bin"
        install_dir.mkdir(parents=True, exist_ok=True)
        ff = tmp / "ffmpeg"
        if ff.exists():
            dst = install_dir / "ffmpeg"
            shutil.copy2(ff, dst)
            dst.chmod(dst.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
            _add_to_path(str(install_dir))
            if _tool_in_path("ffmpeg"):
                print("[ffmpeg] Installed via static download ✓"); return True
    except Exception as e:
        print(f"[ffmpeg] Static download failed: {e}")

    return False


def _install_ytdlp_macos() -> bool:
    print("[yt-dlp] Trying pip...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", "--upgrade", "yt-dlp"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        _add_to_path(str(Path.home() / ".local" / "bin"))
        _add_to_path("/opt/homebrew/bin")
        if _tool_in_path("yt-dlp"):
            print("[yt-dlp] Installed via pip ✓"); return True
    except Exception: pass

    print("[yt-dlp] Trying brew...")
    try:
        r = subprocess.run(["brew", "install", "yt-dlp"], timeout=180, capture_output=True)
        if r.returncode == 0 and _tool_in_path("yt-dlp"):
            print("[yt-dlp] Installed via brew ✓"); return True
    except Exception: pass

    # Binary download
    print("[yt-dlp] Downloading binary from GitHub...")
    try:
        url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos"
        install_dir = Path.home() / ".local" / "bin"
        install_dir.mkdir(parents=True, exist_ok=True)
        dst = install_dir / "yt-dlp"
        urllib.request.urlretrieve(url, dst)
        dst.chmod(dst.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        _add_to_path(str(install_dir))
        if _tool_in_path("yt-dlp"):
            print("[yt-dlp] Installed via binary download ✓"); return True
    except Exception as e:
        print(f"[yt-dlp] Binary download failed: {e}")

    return False


# ── Linux ─────────────────────────────────────────────────────

def _install_ffmpeg_linux() -> bool:
    # apt / apt-get
    for pm in [["apt-get", "install", "-y", "ffmpeg"],
               ["apt",     "install", "-y", "ffmpeg"]]:
        print(f"[ffmpeg] Trying {pm[0]}...")
        try:
            subprocess.run(["sudo"] + pm, timeout=300, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if _tool_in_path("ffmpeg"):
                print(f"[ffmpeg] Installed via {pm[0]} ✓"); return True
        except Exception: pass

    for pm in [["dnf",    "install", "-y", "ffmpeg"],
               ["yum",    "install", "-y", "ffmpeg"],
               ["pacman", "-S",  "--noconfirm", "ffmpeg"],
               ["zypper", "install", "-y", "ffmpeg"],
               ["apk",    "add", "ffmpeg"]]:
        print(f"[ffmpeg] Trying {pm[0]}...")
        try:
            subprocess.run(["sudo"] + pm, timeout=300, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if _tool_in_path("ffmpeg"):
                print(f"[ffmpeg] Installed via {pm[0]} ✓"); return True
        except Exception: pass

    # snap
    print("[ffmpeg] Trying snap...")
    try:
        subprocess.run(["sudo", "snap", "install", "ffmpeg"],
                       timeout=300, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if _tool_in_path("ffmpeg"):
            print("[ffmpeg] Installed via snap ✓"); return True
    except Exception: pass

    # Static binary (John Van Sickle)
    print("[ffmpeg] Downloading static build (John Van Sickle)...")
    try:
        import platform
        arch = "amd64" if platform.machine() in ("x86_64", "AMD64") else "arm64"
        url  = f"https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-{arch}-static.tar.xz"
        tmp  = Path(tempfile.mkdtemp())
        tar  = tmp / "ffmpeg.tar.xz"
        urllib.request.urlretrieve(url, tar)
        subprocess.run(["tar", "-xf", str(tar), "-C", str(tmp)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        install_dir = Path.home() / ".local" / "bin"
        install_dir.mkdir(parents=True, exist_ok=True)
        for exe in ("ffmpeg", "ffprobe"):
            found = next(tmp.rglob(exe), None)
            if found:
                dst = install_dir / exe
                shutil.copy2(found, dst)
                dst.chmod(dst.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        _add_to_path(str(install_dir))
        shutil.rmtree(tmp, ignore_errors=True)
        if _tool_in_path("ffmpeg"):
            print("[ffmpeg] Installed via static build ✓"); return True
    except Exception as e:
        print(f"[ffmpeg] Static build failed: {e}")

    return False


def _install_ytdlp_linux() -> bool:
    print("[yt-dlp] Trying pip...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", "--upgrade", "yt-dlp"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        _add_to_path(str(Path.home() / ".local" / "bin"))
        if _tool_in_path("yt-dlp"):
            print("[yt-dlp] Installed via pip ✓"); return True
    except Exception: pass

    for pm in [["apt-get", "install", "-y", "yt-dlp"],
               ["apt",     "install", "-y", "yt-dlp"],
               ["dnf",     "install", "-y", "yt-dlp"],
               ["pacman",  "-S", "--noconfirm", "yt-dlp"],
               ["apk",     "add", "yt-dlp"]]:
        print(f"[yt-dlp] Trying {pm[0]}...")
        try:
            subprocess.run(["sudo"] + pm, timeout=120, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if _tool_in_path("yt-dlp"):
                print(f"[yt-dlp] Installed via {pm[0]} ✓"); return True
        except Exception: pass

    # Binary download
    print("[yt-dlp] Downloading binary from GitHub...")
    try:
        url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"
        install_dir = Path.home() / ".local" / "bin"
        install_dir.mkdir(parents=True, exist_ok=True)
        dst = install_dir / "yt-dlp"
        urllib.request.urlretrieve(url, dst)
        dst.chmod(dst.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        _add_to_path(str(install_dir))
        if _tool_in_path("yt-dlp"):
            print("[yt-dlp] Installed via binary download ✓"); return True
    except Exception as e:
        print(f"[yt-dlp] Binary download failed: {e}")

    return False


# ── Dispatcher ────────────────────────────────────────────────

def _ensure_tool(name: str) -> bool:
    if _tool_in_path(name):
        print(f"[CHECK] {name} ✓ already in PATH")
        return True

    print(f"\n[INSTALL] {name} not found – attempting automatic installation...")

    is_win   = sys.platform.startswith("win")
    is_mac   = sys.platform.startswith("darwin")
    # Linux / other

    if name == "ffmpeg":
        if   is_win: ok = _install_ffmpeg_windows()
        elif is_mac: ok = _install_ffmpeg_macos()
        else:        ok = _install_ffmpeg_linux()
    elif name == "yt-dlp":
        if   is_win: ok = _install_ytdlp_windows()
        elif is_mac: ok = _install_ytdlp_macos()
        else:        ok = _install_ytdlp_linux()
    else:
        ok = False

    if ok:
        print(f"[INSTALL] {name} ready ✓")
    else:
        print(f"[ERROR] Could not install {name} automatically.")
        print(f"        Please install manually:")
        if sys.platform.startswith("win"):
            urls = {"ffmpeg": "https://ffmpeg.org/download.html",
                    "yt-dlp": "https://github.com/yt-dlp/yt-dlp/releases"}
        elif sys.platform.startswith("darwin"):
            urls = {"ffmpeg": "https://ffmpeg.org/download.html",
                    "yt-dlp": "https://github.com/yt-dlp/yt-dlp/releases"}
        else:
            urls = {"ffmpeg": "https://ffmpeg.org/download.html",
                    "yt-dlp": "https://github.com/yt-dlp/yt-dlp/releases"}
        print(f"        → {urls.get(name, 'https://github.com/yt-dlp/yt-dlp')}")
    return ok


# ─────────────────────────────────────────────────────────────
#  AUTO-INSTALL BOOTSTRAP
# ─────────────────────────────────────────────────────────────
def _bootstrap_install():
    pip_pkgs = [
        ("PyQt5",    "PyQt5"),
        ("Pillow",   "Pillow"),
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
        try:
            __import__(import_name)
        except ImportError:
            print(f"[PIP] Installing {pkg_name}...")
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "--quiet", pkg_name],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                print(f"[PIP] {pkg_name} ✓")
            except Exception as e:
                print(f"[PIP] {pkg_name} failed: {e}")

    print("[BOOTSTRAP] ── Python packages ──────────────────")
    for imp, pkg in pip_pkgs:
        pip_install(imp, pkg)

    print("[BOOTSTRAP] ── Optional packages ─────────────────")
    for imp, pkg in optional_pkgs:
        pip_install(imp, pkg)

    print("[BOOTSTRAP] ── System tools ──────────────────────")
    _ensure_tool("ffmpeg")
    _ensure_tool("yt-dlp")
    print("[BOOTSTRAP] ── Done ──────────────────────────────\n")

_bootstrap_install()

# ─────────────────────────────────────────────────────────────
#  Imports sau bootstrap
# ─────────────────────────────────────────────────────────────
import requests
import psutil
from PIL import Image, ImageFilter
from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import Qt, QSize, QTimer
from PyQt5.QtGui import QIcon, QPixmap, QFont, QColor, QPalette
from PyQt5.QtWidgets import (
    QApplication, QWidget, QDialog, QGridLayout, QFormLayout, QLabel,
    QLineEdit, QPushButton, QFileDialog, QComboBox, QSpinBox,
    QDoubleSpinBox, QTextEdit, QMessageBox, QProgressBar, QGroupBox,
    QVBoxLayout, QHBoxLayout, QScrollArea, QSizePolicy, QFrame,
    QStackedWidget, QListWidget, QListWidgetItem, QAbstractItemView,
    QCheckBox,
)

# ─────────────────────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────────────────────
WINDOW_TITLE        = "Horizon UI Extension Studio"
MAX_FRAMES          = 100
DEFAULT_FPS         = 20
MEMORY_THRESHOLD    = 80

ANIM_BG_DIR         = "hrzn_animated_background"
LOADING_BG_DIR      = "hrzn_loading_background"
CONTAINER_BG_DIR    = "hrzn_container_background"
SOUNDS_DIR          = "sounds/music/bgm"
UI_DIR              = "ui"

CONTAINER_BG_URL    = "https://tubeo5866.github.io/files/hrzn_container_background.zip"

FRAME_PREFIX_ANIM   = "hans_common_"   # hrzn_animated_background/hans_common_xxx.png
# hrzn_loading_background/xxx.png  (plain number)


# ─────────────────────────────────────────────────────────────
#  Compressors (giữ nguyên từ bản gốc, thêm Lossless)
# ─────────────────────────────────────────────────────────────
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
        # Simplified – reuses original logic
        self.log("CompressorIo: using Pillow as fallback (Selenium optional).")
        PillowCompressor(self.cfg, self.log).compress(frame_dir)


# ─────────────────────────────────────────────────────────────
#  IMAGE ORDER DIALOG
# ─────────────────────────────────────────────────────────────
class ImageOrderDialog(QDialog):
    def __init__(self, images: list, parent=None):
        super().__init__(parent)
        self._images = list(images)   # list[Path]
        self.setWindowTitle("Set Loading Background Image Order")
        self.setMinimumSize(520, 560)
        self._build()

    def _build(self):

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(14, 14, 14, 12)

        # ── Header ──
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

        # ── List widget ──
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
            # Thumbnail
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

        # ── Row number column hint ──
        note = QLabel("💡 Tip: select an item then use ↑ / ↓ buttons to move it.")
        note.setStyleSheet("color:#888; font-size:10px;")
        layout.addWidget(note)

        # ── Up / Down buttons ──
        ud_row = QHBoxLayout()
        btn_up = QPushButton("▲  Move Up")
        btn_dn = QPushButton("▼  Move Down")
        btn_up.setFixedHeight(28)
        btn_dn.setFixedHeight(28)
        btn_up.clicked.connect(self._move_up)
        btn_dn.clicked.connect(self._move_down)
        ud_row.addWidget(btn_up); ud_row.addWidget(btn_dn); ud_row.addStretch()
        layout.addLayout(ud_row)

        # ── Separator ──
        line = QFrame(); line.setFrameShape(QFrame.HLine); line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        # ── OK / Cancel ──
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("✖  Cancel")
        btn_cancel.setFixedHeight(32)
        btn_cancel.setStyleSheet(
            "QPushButton{background:#c0392b;color:white;border-radius:4px;padding:0 16px;font-weight:bold;}"
            "QPushButton:hover{background:#e74c3c;}"
        )
        btn_ok = QPushButton("✔  OK — Use This Order")
        btn_ok.setFixedHeight(32)
        btn_ok.setStyleSheet(
            "QPushButton{background:#27ae60;color:white;border-radius:4px;padding:0 16px;font-weight:bold;}"
            "QPushButton:hover{background:#2ecc71;}"
        )
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


# ─────────────────────────────────────────────────────────────
#  Worker
# ─────────────────────────────────────────────────────────────
class Worker(QtCore.QThread):
    log_signal         = QtCore.pyqtSignal(str)
    done_signal        = QtCore.pyqtSignal(bool, str)
    progress_signal    = QtCore.pyqtSignal(int)
    # Phát lên main thread để hiện ImageOrderDialog; main thread trả kết quả qua _deliver_order
    show_order_dialog  = QtCore.pyqtSignal(list)   # list[str] paths

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self._stop_requested = False
        self._temp_files = []

    def stop(self):
        self._stop_requested = True

    def log(self, msg: str):
        self.log_signal.emit(str(msg))

    def run(self):
        try:
            ok = self.process()
            self.done_signal.emit(True, "✅ mcpack created successfully!")
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

    # ── helpers ──────────────────────────────────────────────
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
        return self._run_subprocess(["ffmpeg"] + args)

    def _monitor_memory(self):
        mem = psutil.virtual_memory()
        if mem.percent > MEMORY_THRESHOLD:
            self.log(f"⚠️ High memory: {mem.percent:.0f}%")

    # ── download & extract ───────────────────────────────────
    def _download_youtube(self, url: str, output_dir: Path) -> Path:
        if self._stop_requested: raise RuntimeError("Cancelled.")
        self._ensure_dir(output_dir)
        out_path = output_dir / "input_video.%(ext)s"
        start = self.cfg.get("start_seconds")
        end   = self.cfg.get("end_seconds")
        cmd = [
            "yt-dlp", "-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
            "--merge-output-format", "mp4", "-o", str(out_path), url
        ]
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

    def _extract_frames_anim(self, video: Path, pack_root: Path) -> Path:
        if self._stop_requested: raise RuntimeError("Cancelled.")
        dst = pack_root / ANIM_BG_DIR
        if dst.exists(): shutil.rmtree(dst)
        self._ensure_dir(dst)

        n = min(int(self.cfg.get("anim_frames", MAX_FRAMES)), MAX_FRAMES)
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

    def _extract_frames_loading(self, video: Path, pack_root: Path) -> Path:
        if self._stop_requested: raise RuntimeError("Cancelled.")
        dst = pack_root / LOADING_BG_DIR
        if dst.exists(): shutil.rmtree(dst)
        self._ensure_dir(dst)

        n = min(int(self.cfg.get("load_frames", MAX_FRAMES)), MAX_FRAMES)
        # extract first, then rename to plain numbers
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

        # rename load_001.png → 1.png, load_002.png → 2.png …
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

        # Try OpenCV first
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

        # Fallback: Pillow
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
        cmd = ["yt-dlp", "-x", "--audio-format", "vorbis", "-o", str(out_tmpl), url]
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
        # Update cfg so sound_definitions.json uses the correct name
        self.cfg["bgm_name"] = bgm_name

        dst_dir = pack_root / SOUNDS_DIR
        self._ensure_dir(dst_dir)
        dst = dst_dir / f"{bgm_name}.ogg"

        if src.suffix.lower() == ".ogg":
            shutil.copy2(src, dst)
            self.log(f"BGM copied: {src.name} \u2192 {dst.name}")
        else:
            self.log(f"Converting {src.name} \u2192 {dst.name} (Vorbis OGG)...")
            self._run_ffmpeg(["-y", "-i", str(src), "-acodec", "libvorbis", "-q:a", "6", str(dst)])
            self.log("BGM conversion done \u2713")

    # ── JSON generators ──────────────────────────────────────
    def _gen_bg_anim_json(self, anim_dir: Path, pack_root: Path):
        frames = sorted(anim_dir.glob(f"{FRAME_PREFIX_ANIM}*.png"))
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
            trailing  = "" if i < n else ""
            lines.append(f'  "{key}@hrzn_ui_wextension.hans_anim_base":{{"$anm_offset": [ "0px", "{y_pct}" ],"next": "@hrzn_ui_wextension.{next_key}"}},')

        # remove trailing comma from last line
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

        # controls list
        ctrl_lines = []
        for i in range(1, n + 1):
            trailing = "," if i < n else ""
            ctrl_lines.append(f'      {{ "{i}@hrzn_ui_load_wextension.img": {{ "$img": "{i}" }} }}{trailing}')

        # animation frames
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

    def _gen_manifest(self, pack_root: Path):
        creator = self.cfg.get("creator", "Unknown")
        ext_name = self.cfg.get("new_pack_name", "MyExtension")
        data = {
            "format_version": 2,
            "header": {
                "description": f"§lFirst use restart the game!\nOriginal Creator : Han's404 | Youtube: @zxyn404 ( Han's )\nExtension Creator : {creator}",
                "name": f"§l§dHorizon§bUI: {ext_name}",
                "uuid": str(uuid.uuid4()),
                "version": [201, 1, 0],
                "min_engine_version": [1, 21, 114]
            },
            "modules": [{
                "description": f"§lFirst use restart the game!\nOriginal Creator : Han's404 | Youtube: @zxyn404 ( Han's )\nExtension Creator : {creator}",
                "type": "resources",
                "uuid": str(uuid.uuid4()),
                "version": [201, 1, 0]
            }]
        }
        out = pack_root / "manifest.json"
        out.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")
        self.log("manifest.json generated ✓")

    def _gen_global_variables(self, pack_root: Path):
        creator = self.cfg.get("creator", "Unknown")
        content = f"""{{
  /* -------------------------- EXTENSION -------------------------- */
  // To display Extension Version and Extension Creator Name in NekoUI About Settings
  // Default = True

  "$hrzn.ui.use_extension": true,
  "$hrzn.ui.creator_name": "{creator}",
  "$hrzn.ui.extension_version": "201.1.0", // Numbers only!
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
        # Xóa sạch folder cũ trước khi copy để tránh lẫn ảnh từ nguồn khác
        if dst.exists():
            shutil.rmtree(dst)
        dst.mkdir(parents=True, exist_ok=True)

        # Check nếu tất cả stem là số nguyên liên tục
        def _all_numeric(files):
            try:
                nums = [int(f.stem) for f in files]
                return nums
            except ValueError:
                return None

        nums = _all_numeric(images)
        if nums is not None:
            # Đã đúng thứ tự số → copy thẳng, đổi tên về 1, 2, 3 ... (chuẩn hóa)
            for new_idx, img in enumerate(
                sorted(images, key=lambda f: int(f.stem)), start=1
            ):
                dst_name = dst / f"{new_idx}{img.suffix.lower()}"
                shutil.copy2(img, dst_name)
                self.log(f"Copied {img.name} → {dst_name.name}")
            self.log(f"✓ {len(images)} loading BG images copied (numeric order).")
        else:
            # Tên không phải số → yêu cầu user sắp xếp
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

    # Signal để giao tiếp với UI thread khi cần dialog
    _order_request_signal  = QtCore.pyqtSignal(list)        # gửi list Path → UI
    _order_response_signal = QtCore.pyqtSignal(list)        # UI trả về list Path đã sắp xếp

    def _deliver_order(self, ordered: list):
        self._order_result = ordered   # list[Path] hoặc []
        self._order_event.set()

    def _request_image_order(self, images: list):
        import threading
        self._order_result = None
        self._order_event  = threading.Event()

        # Phát signal — main thread nhận, hiện dialog, gọi _deliver_order
        self.show_order_dialog.emit([str(p) for p in images])

        # Block worker thread đến khi main thread báo xong
        self._order_event.wait()

        result = self._order_result
        return result if result else None

    # ── compress helper ──────────────────────────────────────
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

    # ── MAIN PROCESS ─────────────────────────────────────────
    def process(self):
        self._monitor_memory()
        total_steps = 14
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

        # ── 1. Folder skeleton ─────────────────────────────
        for d in [ANIM_BG_DIR, LOADING_BG_DIR, CONTAINER_BG_DIR,
                  SOUNDS_DIR, UI_DIR]:
            self._ensure_dir(pack_root / d)
        tick("Folder structure created")

        # ── 2. Resolve video ───────────────────────────────
        video_input = self.cfg["video_path"]
        delete_after = False
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

        # ── 3. Extract animated background frames ──────────
        anim_dir = self._extract_frames_anim(video, pack_root)
        tick("Animated background frames extracted")

        # ── 4. Extract / copy loading background ──────────
        if self.cfg.get("loading_bg_folder", "").strip():
            self._copy_loading_bg_folder(pack_root)
            load_dir = pack_root / LOADING_BG_DIR
            tick("Loading background images copied from folder")
        else:
            load_dir = self._extract_frames_loading(video, pack_root)
            tick("Loading background frames extracted")

        # ── 5. blur.png ────────────────────────────────────
        self._make_blur_png(anim_dir)
        tick("blur.png created")

        # ── 6. Compress anim frames ────────────────────────
        method = self.cfg.get("compress_method", "lossless").lower()
        compressor = self._get_compressor(method)
        if compressor:
            self.log(f"Compressing anim frames via {method}...")
            compressor.compress(anim_dir)
        tick("Anim frames compressed")

        # ── 7. Compress loading frames ─────────────────────
        if compressor:
            self.log(f"Compressing loading frames via {method}...")
            compressor.compress(load_dir)
        tick("Loading frames compressed")

        # ── 8. Download container background ───────────────
        self._download_container_bg(pack_root)
        tick("Container background downloaded")

        # ── 9. Audio ───────────────────────────────────────
        if self.cfg.get("bgm_file", "").strip():
            self._copy_bgm_file(pack_root)
        elif re.match(r"^https?://(www\.)?(youtube\.com|youtu\.be)/", video_input):
            self._download_youtube_audio(video_input, pack_root)
        else:
            self._download_audio(video, pack_root)
        tick("Audio prepared")

        # ── 10. Generate JSONs ─────────────────────────────
        self._gen_bg_anim_json(anim_dir, pack_root)
        self._gen_bg_load_json(load_dir, pack_root)
        self._gen_manifest(pack_root)
        self._gen_global_variables(pack_root)
        self._gen_music_definitions(pack_root)
        self._gen_sound_definitions(pack_root)
        tick("JSON files generated")

        # ── 11. Pack to .mcpack (ZIP) ──────────────────────
        zip_base = output_folder / (ext_name + ".mcpack")
        if zip_base.exists(): zip_base.unlink()
        self.log(f"Packing → {zip_base}")
        shutil.make_archive(str(zip_base.with_suffix("")), "zip", pack_root)
        zip_tmp = zip_base.with_suffix(".zip")
        if zip_tmp.exists(): zip_tmp.rename(zip_base)
        tick("mcpack created")

        # ── 12. Cleanup ────────────────────────────────────
        shutil.rmtree(pack_root, ignore_errors=True)
        self._temp_files.remove(pack_root)
        if delete_after:
            shutil.rmtree(video.parent, ignore_errors=True)
        tick("Cleanup done")

        self.log(f"\n✅ Done! Output: {zip_base}")
        self.progress_signal.emit(100)
        return True


# ─────────────────────────────────────────────────────────────
#  Main Window
# ─────────────────────────────────────────────────────────────
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.setWindowTitle(WINDOW_TITLE)
        self.setMinimumWidth(720)
        self.setMinimumHeight(720)
        self._build_ui()
        self._check_tools()

    def _check_tools(self):
        for tool in ["ffmpeg", "yt-dlp"]:
            try:
                subprocess.check_output([tool, "--version"], stderr=subprocess.DEVNULL)
                self.append_log(f"✅ {tool} found")
            except Exception:
                self.append_log(f"⚠️ {tool} NOT found in PATH – some features may fail.")

    def _build_ui(self):
        # ═══════════════════════════════════════════════════════
        #  Root: LEFT settings panel  |  RIGHT log panel
        # ═══════════════════════════════════════════════════════
        from PyQt5.QtWidgets import QSplitter
        from PyQt5.QtCore import Qt as _Qt

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter)

        # ───────────────────────────────────────────────────────
        #  LEFT: scrollable settings + progress + buttons
        # ───────────────────────────────────────────────────────
        left_outer = QWidget()
        left_outer.setMinimumWidth(360)
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

        # ── OUTPUT ──────────────────────────────────────────
        _sec("OUTPUT")
        self.inp_output = QLineEdit(str(Path.home() / "HorizonExtensions"))
        btn_o = QPushButton("Browse…"); btn_o.clicked.connect(self.browse_output)
        _row("Output Folder:", self.inp_output, btn_o)

        self.inp_packname = QLineEdit("MyExtension")
        _row("Extension Name:", self.inp_packname)

        self.inp_creator = QLineEdit("Unknown")
        _row("Creator Name:", self.inp_creator)

        # ── VIDEO SOURCE ─────────────────────────────────────
        _sec("VIDEO SOURCE")
        self.inp_video = QLineEdit()
        self.inp_video.setPlaceholderText("Local file or YouTube URL")
        btn_v = QPushButton("Browse…"); btn_v.clicked.connect(self.browse_video)
        _row("Video / YouTube URL:", self.inp_video, btn_v)

        self.inp_start = QLineEdit("0")
        _row("Start Time (s or mm:ss):", self.inp_start)

        self.inp_end = QLineEdit("30")
        _row("End Time (s or mm:ss):", self.inp_end)

        self.spn_fps = QSpinBox(); self.spn_fps.setRange(1, 120); self.spn_fps.setValue(DEFAULT_FPS)
        _row("Extract FPS:", self.spn_fps)

        self.spn_anim_frames = QSpinBox(); self.spn_anim_frames.setRange(1, MAX_FRAMES); self.spn_anim_frames.setValue(MAX_FRAMES)
        _row("Anim Frames (max 100):", self.spn_anim_frames)

        self.spn_load_frames = QSpinBox(); self.spn_load_frames.setRange(1, MAX_FRAMES); self.spn_load_frames.setValue(MAX_FRAMES)
        _row("Loading Frames (max 100):", self.spn_load_frames)

        # ── ASSETS ───────────────────────────────────────────
        _sec("ASSETS")
        self.inp_bgm = QLineEdit()
        self.inp_bgm.setPlaceholderText("(optional — leave blank to extract from video)")
        self.inp_bgm.setToolTip(
            "Pick an audio file (.ogg, .mp3, .wav, .flac, .m4a, .aac…).\nIf not .ogg, auto-converted to Vorbis OGG.\nLeave blank to extract audio from video."
        )
        btn_bgm = QPushButton("Browse…"); btn_bgm.clicked.connect(self.browse_bgm)
        _row("Background Music File:", self.inp_bgm, btn_bgm)

        self.inp_loading_bg = QLineEdit()
        self.inp_loading_bg.setPlaceholderText("(optional — leave blank to use video frames)")
        self.inp_loading_bg.setToolTip(
            "Optional: folder with images for loading screen.\nNumeric filenames → copied as-is.\nOther names → reorder dialog appears.\nLeave blank to extract frames from video."
        )
        btn_lbg = QPushButton("Browse…"); btn_lbg.clicked.connect(self.browse_loading_bg)
        _row("Loading Background Folder:", self.inp_loading_bg, btn_lbg)

        # ── COMPRESSION ──────────────────────────────────────
        _sec("COMPRESSION")
        self.cmb_compress = QComboBox()
        self._compress_methods = [
            "Lossless", "Pillow", "FFmpeg", "TinyPNG",
            "Kraken", "ImageKit", "Cloudinary",
            "Imagecompressr", "Compressor",
        ]
        self.cmb_compress.addItems(self._compress_methods)
        self.cmb_compress.setCurrentText("Lossless")
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

        # 0 – Lossless
        _lw = QWidget(); _ll = QLabel("No configuration needed.")
        _ll.setStyleSheet("color:grey;font-style:italic;")
        QVBoxLayout(_lw).addWidget(_ll); self._api_stack.addWidget(_lw)

        # 1 – Pillow
        self.cmb_pillow_q = QComboBox()
        self.cmb_pillow_q.addItems(["Low", "Medium", "High", "Maximum"])
        self.cmb_pillow_q.setCurrentText("High")
        self._api_stack.addWidget(make_panel([("Quality:", self.cmb_pillow_q)]))

        # 2 – FFmpeg
        self.spn_ff_qv = QSpinBox(); self.spn_ff_qv.setRange(1, 31); self.spn_ff_qv.setValue(1)
        self._api_stack.addWidget(make_panel([("QV (1=best, 31=worst):", self.spn_ff_qv)]))

        # 3 – TinyPNG
        self.inp_tinify = QLineEdit(); self.inp_tinify.setPlaceholderText("TinyPNG API Key")
        self.inp_tinify.setEchoMode(QLineEdit.Password)
        self._api_stack.addWidget(make_panel([("API Key:", self.inp_tinify)]))

        # 4 – Kraken
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

        # 5 – ImageKit
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

        # 6 – Cloudinary
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

        # 7 – Imagecompressr
        _iw = QWidget(); _il = QLabel("Uses headless Chrome – no API key required.")
        _il.setStyleSheet("color:grey;font-style:italic;"); _il.setWordWrap(True)
        QVBoxLayout(_iw).addWidget(_il); self._api_stack.addWidget(_iw)

        # 8 – Compressor.io
        _cw = QWidget(); _cl = QLabel("Uses headless Chrome – no API key required.")
        _cl.setStyleSheet("color:grey;font-style:italic;"); _cl.setWordWrap(True)
        QVBoxLayout(_cw).addWidget(_cl); self._api_stack.addWidget(_cw)

        def _on_method(text):
            idx = self._compress_methods.index(text) if text in self._compress_methods else 0
            self._api_stack.setCurrentIndex(idx)
        self.cmb_compress.currentTextChanged.connect(_on_method)
        _on_method(self.cmb_compress.currentText())

        api_grp = QGroupBox("Compression Settings")
        _ag = QVBoxLayout(api_grp); _ag.setContentsMargins(4, 4, 4, 4)
        _ag.addWidget(self._api_stack)
        g.addWidget(api_grp, r, 0, 1, 3); r += 1

        # ── Progress bar ─────────────────────────────────────
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(14)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(
            "QProgressBar{border:1px solid #555;border-radius:3px;background:#2a2a2a;}"
            "QProgressBar::chunk{background:#27ae60;border-radius:2px;}"
        )
        left_vbox.addWidget(self.progress_bar)

        # ── Buttons ───────────────────────────────────────────
        btn_bar = QHBoxLayout()
        btn_bar.setContentsMargins(4, 2, 4, 4)
        self.btn_run = QPushButton("▶  Build mcpack")
        self.btn_run.setFixedHeight(36)
        self.btn_run.setStyleSheet(
            "QPushButton{background:#27ae60;color:white;font-weight:bold;"
            "border-radius:5px;font-size:13px;}"
            "QPushButton:hover{background:#2ecc71;}"
            "QPushButton:disabled{background:#555;color:#888;}"
        )
        self.btn_run.clicked.connect(self.run_process)

        self.btn_cancel = QPushButton("✖  Cancel")
        self.btn_cancel.setFixedHeight(36)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setStyleSheet(
            "QPushButton{background:#c0392b;color:white;font-weight:bold;"
            "border-radius:5px;font-size:13px;}"
            "QPushButton:hover{background:#e74c3c;}"
            "QPushButton:disabled{background:#555;color:#888;}"
        )
        self.btn_cancel.clicked.connect(self.cancel_process)
        btn_bar.addWidget(self.btn_run, stretch=3)
        btn_bar.addWidget(self.btn_cancel, stretch=1)
        left_vbox.addLayout(btn_bar)

        splitter.addWidget(left_outer)

        # ───────────────────────────────────────────────────────
        #  RIGHT: log + status line
        # ───────────────────────────────────────────────────────
        right_widget = QWidget()
        right_widget.setMinimumWidth(280)
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
            "ⓘ This script is licensed under GNU v3 License."
            "</span><br>"
            "<span style='color:#666;font-size:10px;'>"
            "Made with love for HorizonUI Extension Makers!"
            "</span>"
        )
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet(
            "border-top:1px solid #333; padding:4px 4px 2px 4px;"
        )
        right_vbox.addWidget(self.lbl_status)

        splitter.addWidget(right_widget)
        splitter.setSizes([420, 580])

    # ── Slots ─────────────────────────────────────────────────
    def browse_video(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select Video", filter="Video (*.mp4 *.mov *.mkv *.avi *.webm *.m4v)")
        if f: self.inp_video.setText(f)

    def browse_output(self):
        d = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if d: self.inp_output.setText(d)

    def browse_loading_bg(self):
        d = QFileDialog.getExistingDirectory(self, "Select Folder Containing Loading Background Images")
        if d:
            self.inp_loading_bg.setText(d)

    def browse_bgm(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Select Background Music File",
            filter="Audio Files (*.ogg *.mp3 *.wav *.flac *.m4a *.aac *.opus *.wma *.aiff);;All Files (*)"
        )
        if f:
            self.inp_bgm.setText(f)

    def append_log(self, s: str):
        self.log_box.append(s)
        self.log_box.moveCursor(QtGui.QTextCursor.End)

    def run_process(self):
        video = self.inp_video.text().strip()
        output = self.inp_output.text().strip()
        name = self.inp_packname.text().strip()

        if not video or not output or not name:
            QMessageBox.warning(self, "Missing Fields", "Please fill in Video, Output Folder, and Extension Name.")
            return

        try:
            start = Worker.parse_time(self.inp_start.text().strip())
            end   = Worker.parse_time(self.inp_end.text().strip())
        except ValueError as e:
            QMessageBox.warning(self, "Time Error", str(e)); return

        if end is not None and start is not None and end <= start:
            QMessageBox.warning(self, "Time Error", "End Time must be greater than Start Time."); return

        cfg = {
            "video_path":       video,
            "output_folder":    output,
            "new_pack_name":    name,
            "creator":          self.inp_creator.text().strip(),
            "bgm_file":         self.inp_bgm.text().strip(),
            "bgm_name":         Path(self.inp_bgm.text().strip()).stem if self.inp_bgm.text().strip() else "background_music",
            "start_seconds":    start,
            "end_seconds":      end,
            "fps":              self.spn_fps.value(),
            "anim_frames":      self.spn_anim_frames.value(),
            "load_frames":      self.spn_load_frames.value(),
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
        }

        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress_bar.setValue(0)
        self.worker = Worker(cfg)
        self.worker.log_signal.connect(self.append_log)
        self.worker.done_signal.connect(self.on_done)
        self.worker.progress_signal.connect(self.progress_bar.setValue)
        self.worker.show_order_dialog.connect(self._on_show_order_dialog)
        self.append_log("=== Starting ===")
        self.worker.start()

    def _on_show_order_dialog(self, path_strings: list):
        images = [Path(p) for p in path_strings]
        dlg = ImageOrderDialog(images, parent=self)
        if dlg.exec_() == dlg.Accepted:
            ordered = dlg.ordered_paths()
        else:
            ordered = []   # empty = user cancelled
        # Trả kết quả về worker (thread-safe vì worker đang block trên Event)
        if self.worker:
            self.worker._deliver_order(ordered)

    def cancel_process(self):
        if self.worker and self.worker.isRunning():
            if QMessageBox.question(self, "Cancel?", "Cancel the running process?",
                                    QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                self.worker.stop()
                self.worker.wait()
                self.append_log("=== Cancelled ===")
                self.btn_run.setEnabled(True)
                self.btn_cancel.setEnabled(False)

    def on_done(self, ok: bool, msg: str):
        self.append_log(f"=== {'Done' if ok else 'Error'} ===")
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.progress_bar.setValue(100 if ok else 0)
        (QMessageBox.information if ok else QMessageBox.critical)(self, "Result", msg)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            if QMessageBox.question(self, "Exit?", "A process is running. Exit anyway?",
                                    QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                self.worker.stop(); self.worker.wait(); event.accept()
            else:
                event.ignore()
        else:
            event.accept()


# ─────────────────────────────────────────────────────────────
#  LICENSE / TERMS OF USE DIALOG
# ─────────────────────────────────────────────────────────────

LICENSE_TEXT = """\
╔══════════════════════════════════════════════════════════════════════════════╗
║           HORIZON UI EXTENSION STUDIO — TERMS OF USE & LICENSE             ║
╚══════════════════════════════════════════════════════════════════════════════╝

Last updated: 2025

PLEASE READ THESE TERMS CAREFULLY BEFORE USING THIS SOFTWARE.
By clicking "I Agree" you confirm that you have read, understood, and accept
all terms listed below. If you do not agree, click "Decline" to exit.

───────────────────────────────────────────────────────────────────────────────
1. DEFINITIONS
───────────────────────────────────────────────────────────────────────────────
  • "Software"    — Horizon UI Extension Studio (this application).
  • "Extension"   — Any .mcpack file produced by the Software.
  • "Original UI" — HorizonUI by Han's404 (YouTube: @zxyn404).
  • "You / User"  — Any individual or entity running the Software.

───────────────────────────────────────────────────────────────────────────────
2. GRANT OF LICENSE
───────────────────────────────────────────────────────────────────────────────
  The Software is provided free of charge for personal, non-commercial use.
  You are permitted to:
    (a) Create Extensions for personal use and private distribution.
    (b) Share Extensions freely, PROVIDED the original credit is preserved
        (see Section 4).
    (c) Modify the Software's source code for your own non-commercial builds.

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
  following credit in its manifest.json and module description:

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

  By clicking "I Agree" you acknowledge that:
    ✔ You have read and understood all terms above.
    ✔ You will respect the attribution requirements (Section 4).
    ✔ You take full responsibility for the content you process.
    ✔ You will not use this Software for commercial gain without permission.

───────────────────────────────────────────────────────────────────────────────
"""

_AGREED_FLAG = Path.home() / ".hrzn_studio_agreed"
def _check_license(app: "QApplication") -> bool:
    if _AGREED_FLAG.exists():
        return True


    dlg = QDialog()
    dlg.setWindowTitle("Horizon UI Extension Studio — Terms of Use")
    dlg.setMinimumSize(780, 560)
    dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
    # Prevent closing via X without choosing
    dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowCloseButtonHint)
    dlg._accepted = False

    layout = QVBoxLayout(dlg)
    layout.setSpacing(10)
    layout.setContentsMargins(18, 18, 18, 14)

    # ── Header ──
    header = QLabel("📜  Terms of Use & License Agreement")
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

    # ── Separator ──
    line = QFrame(); line.setFrameShape(QFrame.HLine); line.setFrameShadow(QFrame.Sunken)
    layout.addWidget(line)

    # ── License text ──
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

    # ── Scroll-to-bottom hint ──
    hint = QLabel("⬇  Scroll down to read the full agreement before accepting.")
    hint.setStyleSheet("color: #e07b00; font-size: 11px;")
    hint.setAlignment(Qt.AlignCenter)
    layout.addWidget(hint)

    # Hide hint once user scrolled near the bottom
    def _on_scroll():
        sb = txt.verticalScrollBar()
        if sb.value() >= sb.maximum() - 10:
            hint.hide()
            chk.setEnabled(True)
    txt.verticalScrollBar().valueChanged.connect(_on_scroll)

    # ── Checkbox ──
    chk = QCheckBox(
        "I have read and agree to the Terms of Use & License Agreement above."
    )
    chk.setEnabled(False)   # enabled only after scrolling to bottom
    chk.setStyleSheet("font-weight: bold; margin-top: 4px;")

    def _on_check(state):
        btn_agree.setEnabled(state == Qt.Checked)
    chk.stateChanged.connect(_on_check)
    layout.addWidget(chk)

    # ── Buttons ──
    btn_layout = QHBoxLayout()
    btn_layout.addStretch()

    btn_decline = QPushButton("✖  Decline & Exit")
    btn_decline.setFixedHeight(34)
    btn_decline.setStyleSheet(
        "QPushButton{background:#c0392b;color:white;border-radius:4px;padding:0 18px;font-weight:bold;}"
        "QPushButton:hover{background:#e74c3c;}"
    )

    btn_agree = QPushButton("✔  I Agree")
    btn_agree.setFixedHeight(34)
    btn_agree.setEnabled(False)
    btn_agree.setStyleSheet(
        "QPushButton{background:#27ae60;color:white;border-radius:4px;padding:0 18px;font-weight:bold;}"
        "QPushButton:hover{background:#2ecc71;}"
        "QPushButton:disabled{background:#555;color:#888;}"
    )

    btn_layout.addWidget(btn_decline)
    btn_layout.addSpacing(8)
    btn_layout.addWidget(btn_agree)
    layout.addLayout(btn_layout)

    # ── Wire buttons ──
    def _agree():
        dlg._accepted = True
        # Write flag file with timestamp
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

    # Closing via X = decline
    def _close_event(event):
        dlg._accepted = False
        event.accept()
    dlg.closeEvent = _close_event

    dlg.exec_()
    return dlg._accepted


# ─────────────────────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)

    if not _check_license(app):
        sys.exit(0)

    w = MainWindow()
    w.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
