#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Horizon UI Extension Studio — CLI Version
Tạo mcpack cho Minecraft: Bedrock Edition - Horizon UI Extension
Chạy hoàn toàn trong terminal, không cần GUI.
"""

import os, sys, json, shutil, subprocess, uuid, re, time, tempfile, zipfile, stat
import urllib.request
import argparse
import threading
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

    print("[ffmpeg] Downloading from GitHub (BtbN release)...")
    try:
        import urllib.request, zipfile as zf
        api_url = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest"
        with urllib.request.urlopen(api_url, timeout=30) as resp:
            data = json.loads(resp.read())
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
        ffmpeg_exe = next(tmp_dir.rglob("ffmpeg.exe"), None)
        if ffmpeg_exe:
            install_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ffmpeg_bin"
            install_dir.mkdir(parents=True, exist_ok=True)
            for exe in ("ffmpeg.exe", "ffprobe.exe", "ffplay.exe"):
                src = next(tmp_dir.rglob(exe), None)
                if src:
                    shutil.copy2(src, install_dir / exe)
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
        if _tool_in_path("yt-dlp"):
            print("[yt-dlp] Installed via pip ✓"); return True
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

    print("[ffmpeg] Trying snap...")
    try:
        subprocess.run(["sudo", "snap", "install", "ffmpeg"],
                       timeout=300, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if _tool_in_path("ffmpeg"):
            print("[ffmpeg] Installed via snap ✓"); return True
    except Exception: pass

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
    is_win = sys.platform.startswith("win")
    is_mac = sys.platform.startswith("darwin")

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

    if not ok:
        print(f"[INSTALL] ❌ Could not install {name} automatically.")
        print(f"          → https://ffmpeg.org/download.html" if name == "ffmpeg"
              else f"          → https://github.com/yt-dlp/yt-dlp/releases")
    return ok


# ─────────────────────────────────────────────────────────────
#  AUTO-INSTALL BOOTSTRAP
# ─────────────────────────────────────────────────────────────

def _bootstrap_install():
    pip_pkgs = [
        ("PIL",      "Pillow"),
        ("psutil",   "psutil"),
        ("requests", "requests"),
    ]
    optional_pkgs = [
        ("cv2",        "opencv-python"),
        ("tinify",     "tinify"),
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

import requests
import psutil
from PIL import Image, ImageFilter


# ─────────────────────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────────────────────

MAX_FRAMES       = 100
DEFAULT_FPS      = 20
MEMORY_THRESHOLD = 80

ANIM_BG_DIR      = "hrzn_animated_background"
LOADING_BG_DIR   = "hrzn_loading_background"
CONTAINER_BG_DIR = "hrzn_container_background"
SOUNDS_DIR       = "sounds/music/bgm"
UI_DIR           = "ui"

CONTAINER_BG_URL  = "https://tubeo5866.github.io/files/hrzn_container_background.zip"
FRAME_PREFIX_ANIM = "hans_common_"


# ─────────────────────────────────────────────────────────────
#  Compressors
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
        self.log("Lossless mode: no compression applied.")

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
        self.log("FFmpeg compression done.")

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
            result = client.upload(str(f), {"wait": True, "lossy": True,
                                            "quality": self.cfg.get("kraken_quality", 90)})
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
                transformation=[{"quality": self.cfg.get("imagekit_quality", 90)},
                                 {"fetch_format": "jpg"}]
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
            url, _ = cloudinary.utils.cloudinary_url(result["public_id"],
                                                      fetch_format="jpg", quality=q)
            f.with_suffix(".jpg").write_bytes(requests.get(url).content)
            f.unlink()
        self.log("Cloudinary compression done.")

class CompressorIoCompressor(Compressor):
    def compress(self, frame_dir: Path):
        self.log("CompressorIo: using Pillow as fallback.")
        PillowCompressor(self.cfg, self.log).compress(frame_dir)


COMPRESSOR_MAP = {
    "tinypng":    TinyPNGCompressor,
    "pillow":     PillowCompressor,
    "ffmpeg":     FFmpegCompressor,
    "kraken":     KrakenCompressor,
    "imagekit":   ImageKitCompressor,
    "cloudinary": CloudinaryCompressor,
    "compressor": CompressorIoCompressor,
    "lossless":   LosslessCompressor,
    "none":       LosslessCompressor,
}


# ─────────────────────────────────────────────────────────────
#  CLI Progress bar helper
# ─────────────────────────────────────────────────────────────

def _print_progress(pct: int, label: str = "", width: int = 40):
    filled = int(width * pct / 100)
    bar = "█" * filled + "░" * (width - filled)
    print(f"\r[{bar}] {pct:3d}%  {label:<35}", end="", flush=True)
    if pct >= 100:
        print()


# ─────────────────────────────────────────────────────────────
#  Core Processor (no Qt dependency)
# ─────────────────────────────────────────────────────────────

class HorizonProcessor:
    def __init__(self, cfg: dict, verbose: bool = True):
        self.cfg = cfg
        self.verbose = verbose
        self._stop_requested = False
        self._temp_files: list = []

    def stop(self):
        self._stop_requested = True

    def log(self, msg: str):
        if self.verbose:
            print(f"  {msg}")

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
        if len(parts) == 2: return parts[0] * 60 + parts[1]
        if len(parts) == 3: return parts[0] * 3600 + parts[1] * 60 + parts[2]
        raise ValueError(f"Invalid time: {value}")

    def _run_subprocess(self, cmd, **kwargs):
        result = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
        if result.returncode != 0:
            raise RuntimeError(
                f"Command failed: {' '.join(str(c) for c in cmd)}\n{result.stderr}"
            )
        return result

    def _run_ffmpeg(self, args):
        return self._run_subprocess(["ffmpeg"] + args)

    def _monitor_memory(self):
        mem = psutil.virtual_memory()
        if mem.percent > MEMORY_THRESHOLD:
            self.log(f"⚠️  High memory usage: {mem.percent:.0f}%")

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
        self.log(f"Downloading container background...")
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
            self.log(f"⚠️  Failed to download container background: {e}")

    def _extract_frames_anim(self, video: Path, pack_root: Path) -> Path:
        if self._stop_requested: raise RuntimeError("Cancelled.")
        dst = pack_root / ANIM_BG_DIR
        if dst.exists(): shutil.rmtree(dst)
        self._ensure_dir(dst)

        n = min(int(self.cfg.get("anim_frames", MAX_FRAMES)), MAX_FRAMES)
        out_pattern = dst / f"{FRAME_PREFIX_ANIM}%03d.png"
        self.log(f"Extracting {n} animated background frames...")

        args = ["-y"]
        if not self.cfg.get("is_trimmed"):
            ss = self.cfg.get("start_seconds")
            en = self.cfg.get("end_seconds")
            if ss is not None: args += ["-ss", str(ss)]
            if en is not None and ss is not None: args += ["-t", str(en - ss)]

        fps = self.cfg.get("fps", DEFAULT_FPS)
        args += ["-i", str(video), "-vf", f"fps={fps}", "-frames:v", str(n), str(out_pattern)]
        self._run_ffmpeg(args)
        self.log(f"Animated frames extracted → {dst}")
        return dst

    def _extract_frames_loading(self, video: Path, pack_root: Path) -> Path:
        if self._stop_requested: raise RuntimeError("Cancelled.")
        dst = pack_root / LOADING_BG_DIR
        if dst.exists(): shutil.rmtree(dst)
        self._ensure_dir(dst)

        n = min(int(self.cfg.get("load_frames", MAX_FRAMES)), MAX_FRAMES)
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
                self.log(f"blur.png created via OpenCV ✓")
                return
        except Exception as e:
            self.log(f"OpenCV blur failed: {e}, falling back to Pillow...")

        im = Image.open(src)
        im.filter(ImageFilter.GaussianBlur(radius=15)).save(blur_out)
        self.log("blur.png created via Pillow ✓")

    def _download_audio(self, video: Path, pack_root: Path):
        if self._stop_requested: raise RuntimeError("Cancelled.")
        bgm_name = re.sub(r'[\\/:*?"<>|]', "_",
                          self.cfg.get("bgm_name", "bgm").strip()) or "bgm"
        sounds_path = pack_root / SOUNDS_DIR / f"{bgm_name}.ogg"
        self._ensure_dir(sounds_path.parent)
        self.log(f"Extracting audio → {sounds_path.name}")
        self._run_ffmpeg(["-y", "-i", str(video), "-vn", "-acodec", "libvorbis",
                          str(sounds_path)])
        self.log("Audio extracted ✓")

    def _download_youtube_audio(self, url: str, pack_root: Path):
        bgm_name = re.sub(r'[\\/:*?"<>|]', "_",
                          self.cfg.get("bgm_name", "bgm").strip()) or "bgm"
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
        self.cfg["bgm_name"] = bgm_name

        dst_dir = pack_root / SOUNDS_DIR
        self._ensure_dir(dst_dir)
        dst = dst_dir / f"{bgm_name}.ogg"

        if src.suffix.lower() == ".ogg":
            shutil.copy2(src, dst)
            self.log(f"BGM copied: {src.name} → {dst.name}")
        else:
            self.log(f"Converting {src.name} → {dst.name} (Vorbis OGG)...")
            self._run_ffmpeg(["-y", "-i", str(src), "-acodec", "libvorbis",
                              "-q:a", "6", str(dst)])
            self.log("BGM conversion done ✓")

    # ── JSON generators ──────────────────────────────────────

    def _gen_bg_anim_json(self, anim_dir: Path, pack_root: Path):
        frames = sorted(anim_dir.glob(f"{FRAME_PREFIX_ANIM}*.png"))
        n = len(frames)
        if n == 0:
            self.log("⚠️  No anim frames found, skipping .hrzn_public_bg_anim.json")
            return

        lines = []
        lines.append('  "namespace": "hrzn_ui_wextension",')
        lines.append('  "hrzn_ui_settings_bg@core_img": { "texture": "hrzn_animated_background/blur" },')
        lines.append(
            '  "img": { "type": "image", "fill": true, "property_bag": {"#true": "0"}, '
            '"bindings": [ { "binding_name": "#collection_index", "binding_type": "collection_details", '
            '"binding_collection_name": "animated_background" }, { "binding_type": "view", '
            '"source_property_name": "(\'#\' + (#collection_index < 9))", "target_property_name": "#pad00" }, '
            '{ "binding_type": "view", "source_property_name": "(\'#\' + (#collection_index < 99))", '
            '"target_property_name": "#pad0" }, { "binding_type": "view", '
            '"source_property_name": "(\'hrzn_animated_background/hans\' + \'_common_\' + #pad00 + #pad0 + '
            '(#collection_index + 1))", "target_property_name": "#texture" } ] },'
        )
        lines.append(
            f'  "hrzn_ui_main_bg": {{ "size": [ "100%", "100%" ], "type": "stack_panel", '
            f'"anchor_from": "top_left", "anchor_to": "top_left", "offset": "@hrzn_ui_wextension.01", '
            f'"$duration_per_frame|default": 0.03333333, "$frames|default": {n}, '
            f'"collection_name": "animated_background", "factory": {{"name": "test", '
            f'"control_name": "hrzn_ui_wextension.img"}}, "property_bag": {{"#frames": "$frames"}}, '
            f'"bindings": [ {{ "binding_type": "view", "source_property_name": "(#frames*1)", '
            f'"target_property_name": "#collection_length" }} ] }},'
        )
        lines.append(
            '  "hans_anim_base": { "destroy_at_end": "@hrzn_ui_wextension.bg_anim", '
            '"anim_type": "offset", "easing": "linear", "duration": "$duration_per_frame", '
            '"from": "$anm_offset", "to": "$anm_offset" },'
        )
        lines.append('')

        for i in range(1, n + 1):
            y_pct    = "0%" if i == 1 else f"-{(i-1)*100}%"
            next_key = f"{(i % n) + 1:02d}"
            lines.append(
                f'  "{i:02d}@hrzn_ui_wextension.hans_anim_base":'
                f'{{"$anm_offset": [ "0px", "{y_pct}" ],"next": "@hrzn_ui_wextension.{next_key}"}},'
            )

        lines[-1] = lines[-1].rstrip(",")
        content = "{\n" + "\n".join(lines) + "\n}"
        out_path = pack_root / ".hrzn_public_bg_anim.json"
        out_path.write_text(content, encoding="utf-8")
        self.log(f".hrzn_public_bg_anim.json generated ({n} frames) ✓")

    def _gen_bg_load_json(self, load_dir: Path, pack_root: Path):
        IMG_EXT  = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
        all_imgs = [f for f in load_dir.iterdir() if f.suffix.lower() in IMG_EXT]
        frames   = sorted(all_imgs, key=lambda p: int(p.stem) if p.stem.isdigit() else 0)
        n = len(frames)
        if n == 0:
            self.log("⚠️  No loading frames found, skipping .hrzn_public_bg_load.json")
            return

        ctrl_lines = []
        for i in range(1, n + 1):
            trailing = "," if i < n else ""
            ctrl_lines.append(
                f'      {{ "{i}@hrzn_ui_load_wextension.img": {{ "$img": "{i}" }} }}{trailing}'
            )

        anim_lines = []
        for i in range(1, n + 1):
            y_pct    = "0%" if i == 1 else f"-{(i-1)*100}%"
            next_key = f"{(i % n) + 1:02d}"
            trailing = "," if i < n else ""
            anim_lines.append(
                f'  "{i:02d}@hrzn_ui_load_wextension.anim_base":'
                f'{{"$anm_offset": [ 0, "{y_pct}" ],"next": "@hrzn_ui_load_wextension.{next_key}"}}{trailing}'
            )

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
        self.log(f".hrzn_public_bg_load.json generated ({n} frames) ✓")

    def _gen_manifest(self, pack_root: Path):
        creator  = self.cfg.get("creator", "Unknown")
        ext_name = self.cfg.get("new_pack_name", "MyExtension")
        data = {
            "format_version": 2,
            "header": {
                "description": (
                    f"§lFirst use restart the game!\n"
                    f"Original Creator : Han's404 | Youtube: @zxyn404 ( Han's )\n"
                    f"Extension Creator : {creator}"
                ),
                "name": f"§l§dHorizon§bUI: {ext_name}",
                "uuid": str(uuid.uuid4()),
                "version": [201, 1, 0],
                "min_engine_version": [1, 21, 114]
            },
            "modules": [{
                "description": (
                    f"§lFirst use restart the game!\n"
                    f"Original Creator : Han's404 | Youtube: @zxyn404 ( Han's )\n"
                    f"Extension Creator : {creator}"
                ),
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
        bgm_name = re.sub(r'[\\/:*?"<>|]', "_",
                          self.cfg.get("bgm_name", "bgm").strip()) or "bgm"
        content = {
            "format_version": "1.20.20",
            "sound_definitions": {
                "music.menu": {
                    "__use_legacy_max_distance": "true",
                    "category": "music",
                    "max_distance": None,
                    "min_distance": None,
                    "sounds": [{
                        "name": f"sounds/music/bgm/{bgm_name}",
                        "stream": True,
                        "volume": 0.30
                    }]
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
            self.log(f"⚠️  Loading BG folder not found: {src}")
            return

        IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
        images  = sorted([f for f in src.iterdir() if f.suffix.lower() in IMG_EXT])
        if not images:
            self.log(f"⚠️  No images found in {src}")
            return

        dst = pack_root / LOADING_BG_DIR
        if dst.exists():
            shutil.rmtree(dst)
        dst.mkdir(parents=True, exist_ok=True)

        def _all_numeric(files):
            try:
                return [int(f.stem) for f in files]
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
            # CLI: ask user to input the order as a comma-separated list of filenames
            self.log("\nLoading BG images have non-numeric names. Please specify the order.")
            print("\n  Available images:")
            for i, img in enumerate(images):
                print(f"    [{i+1}] {img.name}")
            print()
            while True:
                raw = input("  Enter order as numbers (e.g. 3,1,2) or press Enter for alphabetical: ").strip()
                if not raw:
                    ordered = images
                    break
                try:
                    indices = [int(x.strip()) - 1 for x in raw.split(",")]
                    if all(0 <= i < len(images) for i in indices):
                        ordered = [images[i] for i in indices]
                        break
                    else:
                        print(f"  ⚠️  Invalid indices. Use numbers 1–{len(images)}.")
                except ValueError:
                    print("  ⚠️  Please enter numbers separated by commas.")

            for new_idx, img in enumerate(ordered, start=1):
                dst_name = dst / f"{new_idx}{img.suffix.lower()}"
                shutil.copy2(img, dst_name)
                self.log(f"Copied {img.name} → {dst_name.name}")
            self.log(f"✓ {len(ordered)} loading BG images copied (custom order).")

    def _get_compressor(self, method: str):
        cls = COMPRESSOR_MAP.get(method.lower())
        return cls(self.cfg, self.log) if cls else None

    # ── MAIN PROCESS ─────────────────────────────────────────

    def process(self) -> bool:
        self._monitor_memory()
        total_steps = 14
        step = [0]

        def tick(label=""):
            step[0] += 1
            pct = int(step[0] / total_steps * 100)
            _print_progress(pct, label)

        output_folder = Path(self.cfg["output_folder"]).resolve()
        self._ensure_dir(output_folder)
        ext_name  = self.cfg["new_pack_name"].strip()
        pack_root = output_folder / ext_name
        if pack_root.exists(): shutil.rmtree(pack_root)
        self._ensure_dir(pack_root)
        self._temp_files.append(pack_root)
        tick("Pack folder created")

        for d in [ANIM_BG_DIR, LOADING_BG_DIR, CONTAINER_BG_DIR, SOUNDS_DIR, UI_DIR]:
            self._ensure_dir(pack_root / d)
        tick("Folder structure created")

        video_input  = self.cfg["video_path"]
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

        anim_dir = self._extract_frames_anim(video, pack_root)
        tick("Animated background frames extracted")

        if self.cfg.get("loading_bg_folder", "").strip():
            self._copy_loading_bg_folder(pack_root)
            load_dir = pack_root / LOADING_BG_DIR
            tick("Loading background images copied from folder")
        else:
            load_dir = self._extract_frames_loading(video, pack_root)
            tick("Loading background frames extracted")

        self._make_blur_png(anim_dir)
        tick("blur.png created")

        method     = self.cfg.get("compress_method", "lossless").lower()
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

        self._gen_bg_anim_json(anim_dir, pack_root)
        self._gen_bg_load_json(load_dir, pack_root)
        self._gen_manifest(pack_root)
        self._gen_global_variables(pack_root)
        self._gen_music_definitions(pack_root)
        self._gen_sound_definitions(pack_root)
        tick("JSON files generated")

        zip_base = output_folder / (ext_name + ".mcpack")
        if zip_base.exists(): zip_base.unlink()
        self.log(f"Packing → {zip_base.name}")
        shutil.make_archive(str(zip_base.with_suffix("")), "zip", pack_root)
        zip_tmp = zip_base.with_suffix(".zip")
        if zip_tmp.exists(): zip_tmp.rename(zip_base)
        tick("mcpack created")

        shutil.rmtree(pack_root, ignore_errors=True)
        self._temp_files.remove(pack_root)
        if delete_after:
            shutil.rmtree(video.parent, ignore_errors=True)
        tick("Cleanup done")

        print(f"\n✅  Done! Output: {zip_base}")
        return True

    def cleanup(self):
        for p in self._temp_files:
            p = Path(p)
            try:
                if p.is_dir():   shutil.rmtree(p, ignore_errors=True)
                elif p.exists(): p.unlink()
            except Exception: pass


# ─────────────────────────────────────────────────────────────
#  LICENSE CHECK (CLI — flag file)
# ─────────────────────────────────────────────────────────────

_AGREED_FLAG = Path.home() / ".hrzn_studio_agreed"

LICENSE_TEXT = """\
╔══════════════════════════════════════════════════════════════════════════════╗
║           HORIZON UI EXTENSION STUDIO — TERMS OF USE & LICENSE             ║
╚══════════════════════════════════════════════════════════════════════════════╝

  Original Creator : Han's404 | Youtube: @zxyn404 ( Han's )

  1. This software is provided for personal, non-commercial use only.
  2. You MUST NOT remove or modify the attribution line in any distributed
     Extension (manifest.json and module description).
  3. Downloading copyrighted YouTube videos may infringe on content creator
     rights. Always obtain permission before using third-party content.
  4. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.
"""

def _check_license_cli() -> bool:
    if _AGREED_FLAG.exists():
        return True
    print("=" * 70)
    print(LICENSE_TEXT)
    print("=" * 70)
    ans = input("\nDo you agree to the Terms of Use? [yes/no]: ").strip().lower()
    if ans in ("yes", "y"):
        try:
            import datetime
            _AGREED_FLAG.write_text(
                f"agreed={datetime.datetime.now().isoformat()}\nversion=1\n",
                encoding="utf-8"
            )
        except Exception:
            pass
        return True
    print("Declined. Exiting.")
    return False


# ─────────────────────────────────────────────────────────────
#  INTERACTIVE MODE
# ─────────────────────────────────────────────────────────────

def _prompt(question: str, default: str = "") -> str:
    if default:
        answer = input(f"  {question} [{default}]: ").strip()
        return answer if answer else default
    else:
        while True:
            answer = input(f"  {question}: ").strip()
            if answer:
                return answer
            print("  ⚠️  This field is required.")

def _prompt_optional(question: str, default: str = "") -> str:
    hint = f" [{default}]" if default else " (optional, press Enter to skip)"
    answer = input(f"  {question}{hint}: ").strip()
    return answer if answer else default

def _prompt_int(question: str, default: int, min_val: int, max_val: int) -> int:
    while True:
        raw = input(f"  {question} [{default}] ({min_val}-{max_val}): ").strip()
        if not raw:
            return default
        try:
            val = int(raw)
            if min_val <= val <= max_val:
                return val
            print(f"  ⚠️  Please enter a number between {min_val} and {max_val}.")
        except ValueError:
            print("  ⚠️  Please enter a valid integer.")

def _prompt_choice(question: str, choices: list, default: str) -> str:
    choices_str = " / ".join(choices)
    print(f"  {question}")
    print(f"  Options: {choices_str}")
    while True:
        raw = input(f"  Choice [{default}]: ").strip().lower()
        if not raw:
            return default
        matches = [c for c in choices if c.lower() == raw]
        if matches:
            return matches[0]
        # partial match
        partial = [c for c in choices if c.lower().startswith(raw)]
        if len(partial) == 1:
            return partial[0]
        print(f"  ⚠️  Invalid choice. Options: {choices_str}")

def _run_interactive():
    print("\n" + "═" * 60)
    print("  Horizon UI Extension Studio — CLI Interactive Mode")
    print("═" * 60 + "\n")

    cfg = {}

    # ── Output ────────────────────────────────────────────────
    print("── OUTPUT ──────────────────────────────────────────────")
    cfg["output_folder"] = _prompt("Output folder",
                                   str(Path.home() / "HorizonExtensions"))
    cfg["new_pack_name"] = _prompt("Extension name", "MyExtension")
    cfg["creator"]       = _prompt("Creator name", "Unknown")

    # ── Video source ──────────────────────────────────────────
    print("\n── VIDEO SOURCE ────────────────────────────────────────")
    cfg["video_path"]    = _prompt("Video file path or YouTube URL")
    cfg["start_seconds"] = HorizonProcessor.parse_time(
        _prompt_optional("Start time (s or mm:ss)", "0"))
    cfg["end_seconds"]   = HorizonProcessor.parse_time(
        _prompt_optional("End time (s or mm:ss)", "30"))
    cfg["fps"]           = _prompt_int("Extract FPS", DEFAULT_FPS, 1, 120)
    cfg["anim_frames"]   = _prompt_int("Animated background frames (max 100)",
                                       MAX_FRAMES, 1, MAX_FRAMES)
    cfg["load_frames"]   = _prompt_int("Loading background frames (max 100)",
                                       MAX_FRAMES, 1, MAX_FRAMES)

    # ── Assets ────────────────────────────────────────────────
    print("\n── ASSETS ──────────────────────────────────────────────")
    cfg["bgm_file"]          = _prompt_optional("BGM file path (.ogg/.mp3/.wav, leave blank = extract from video)")
    cfg["loading_bg_folder"] = _prompt_optional("Loading background folder (leave blank = extract from video)")

    # ── Compression ───────────────────────────────────────────
    print("\n── COMPRESSION ─────────────────────────────────────────")
    compress_choices = ["lossless", "pillow", "ffmpeg", "tinypng",
                        "kraken", "imagekit", "cloudinary", "compressor"]
    cfg["compress_method"] = _prompt_choice(
        "Compression method:", compress_choices, "lossless"
    )

    method = cfg["compress_method"].lower()
    if method == "pillow":
        cfg["pillow_quality"] = _prompt_choice(
            "Pillow quality:", ["low", "medium", "high", "maximum"], "high"
        )
    elif method == "ffmpeg":
        cfg["ffmpeg_qv"] = _prompt_int("FFmpeg QV (1=best, 31=worst)", 1, 1, 31)
    elif method == "tinypng":
        cfg["tinify_key"] = _prompt("TinyPNG API Key")
    elif method == "kraken":
        cfg["kraken_key"]     = _prompt("Kraken API Key")
        cfg["kraken_secret"]  = _prompt("Kraken API Secret")
        cfg["kraken_quality"] = _prompt_int("Kraken quality", 90, 1, 100)
    elif method == "imagekit":
        cfg["imagekit_key"]         = _prompt("ImageKit Public Key")
        cfg["imagekit_secret"]      = _prompt("ImageKit Private Key")
        cfg["imagekit_urlendpoint"] = _prompt("ImageKit URL Endpoint")
        cfg["imagekit_quality"]     = _prompt_int("ImageKit quality", 90, 1, 100)
    elif method == "cloudinary":
        cfg["cloudinary_name"]    = _prompt("Cloudinary Cloud Name")
        cfg["cloudinary_key"]     = _prompt("Cloudinary API Key")
        cfg["cloudinary_secret"]  = _prompt("Cloudinary API Secret")
        cfg["cloudinary_quality"] = _prompt_choice(
            "Cloudinary quality:",
            ["auto", "auto:best", "auto:good", "auto:eco", "auto:low"], "auto:best"
        )

    # ── Confirm ───────────────────────────────────────────────
    print("\n── SUMMARY ─────────────────────────────────────────────")
    print(f"  Output folder : {cfg['output_folder']}")
    print(f"  Extension name: {cfg['new_pack_name']}")
    print(f"  Creator       : {cfg['creator']}")
    print(f"  Video/URL     : {cfg['video_path']}")
    print(f"  Time range    : {cfg.get('start_seconds', 0)}s – {cfg.get('end_seconds', 30)}s")
    print(f"  FPS           : {cfg['fps']}")
    print(f"  Anim frames   : {cfg['anim_frames']}")
    print(f"  Load frames   : {cfg['load_frames']}")
    print(f"  Compression   : {cfg['compress_method']}")
    if cfg.get("bgm_file"):
        print(f"  BGM file      : {cfg['bgm_file']}")
    if cfg.get("loading_bg_folder"):
        print(f"  Loading BG    : {cfg['loading_bg_folder']}")
    print()

    confirm = input("  Proceed? [Y/n]: ").strip().lower()
    if confirm in ("n", "no"):
        print("Aborted.")
        sys.exit(0)

    return cfg


# ─────────────────────────────────────────────────────────────
#  ARGUMENT PARSER
# ─────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="horizon_cli",
        description="Horizon UI Extension Studio — CLI\n"
                    "Tạo mcpack cho Minecraft: Bedrock Edition - Horizon UI Extension",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  # Interactive mode (recommended for first-time use)
  python horizon_cli.py

  # Non-interactive with a local video
  python horizon_cli.py --video myvideo.mp4 --name MyPack --creator Han

  # YouTube URL with time range
  python horizon_cli.py --video "https://youtu.be/xxxx" --start 10 --end 40 --name BeachPack

  # With custom BGM and compression
  python horizon_cli.py --video clip.mp4 --name CoolPack --compress pillow --pillow-quality high

  # With a loading-background folder
  python horizon_cli.py --video clip.mp4 --name CoolPack --loading-bg ./my_screens/
        """
    )

    # ── Required (when not interactive) ──────────────────────
    src = p.add_argument_group("source")
    src.add_argument("--video",   metavar="PATH_OR_URL",
                     help="Local video file or YouTube URL")
    src.add_argument("--start",   metavar="TIME", default="0",
                     help="Start time in seconds or mm:ss (default: 0)")
    src.add_argument("--end",     metavar="TIME", default="30",
                     help="End time in seconds or mm:ss (default: 30)")
    src.add_argument("--fps",     type=int, default=DEFAULT_FPS, metavar="N",
                     help=f"Frame extraction FPS (default: {DEFAULT_FPS})")
    src.add_argument("--anim-frames", type=int, default=MAX_FRAMES, metavar="N",
                     dest="anim_frames",
                     help=f"Number of animated background frames, max {MAX_FRAMES}")
    src.add_argument("--load-frames", type=int, default=MAX_FRAMES, metavar="N",
                     dest="load_frames",
                     help=f"Number of loading background frames, max {MAX_FRAMES}")

    # ── Output ────────────────────────────────────────────────
    out = p.add_argument_group("output")
    out.add_argument("--output", "-o",
                     metavar="DIR",
                     default=str(Path.home() / "HorizonExtensions"),
                     help="Output directory (default: ~/HorizonExtensions)")
    out.add_argument("--name", "-n",
                     metavar="NAME", default="MyExtension",
                     help="Extension / pack name (default: MyExtension)")
    out.add_argument("--creator", "-c",
                     metavar="NAME", default="Unknown",
                     help="Creator name embedded in manifest (default: Unknown)")

    # ── Assets ────────────────────────────────────────────────
    assets = p.add_argument_group("assets")
    assets.add_argument("--bgm",
                        metavar="FILE",
                        help="Background music file (.ogg/.mp3/.wav/…). "
                             "Omit to extract from video.")
    assets.add_argument("--loading-bg",
                        metavar="DIR", dest="loading_bg",
                        help="Folder with images for loading screen. "
                             "Omit to extract from video.")
    assets.add_argument("--bgm-name",
                        metavar="NAME", dest="bgm_name", default="bgm",
                        help="BGM track name used in sound_definitions.json "
                             "(default: bgm)")

    # ── Compression ───────────────────────────────────────────
    comp = p.add_argument_group("compression")
    comp.add_argument("--compress",
                      choices=["lossless", "pillow", "ffmpeg", "tinypng",
                               "kraken", "imagekit", "cloudinary", "compressor"],
                      default="lossless", metavar="METHOD",
                      help="Compression method: lossless|pillow|ffmpeg|tinypng|"
                           "kraken|imagekit|cloudinary|compressor (default: lossless)")
    comp.add_argument("--pillow-quality",
                      choices=["low", "medium", "high", "maximum"],
                      default="high", dest="pillow_quality",
                      help="Pillow quality level (default: high)")
    comp.add_argument("--ffmpeg-qv",
                      type=int, default=1, metavar="N", dest="ffmpeg_qv",
                      help="FFmpeg -q:v value 1–31 (default: 1 = best)")
    comp.add_argument("--tinypng-key",
                      metavar="KEY", dest="tinify_key",
                      help="TinyPNG API key")
    comp.add_argument("--kraken-key",
                      metavar="KEY", dest="kraken_key")
    comp.add_argument("--kraken-secret",
                      metavar="SECRET", dest="kraken_secret")
    comp.add_argument("--kraken-quality",
                      type=int, default=90, metavar="N", dest="kraken_quality")
    comp.add_argument("--imagekit-key",
                      metavar="KEY", dest="imagekit_key")
    comp.add_argument("--imagekit-secret",
                      metavar="SECRET", dest="imagekit_secret")
    comp.add_argument("--imagekit-endpoint",
                      metavar="URL", dest="imagekit_urlendpoint")
    comp.add_argument("--imagekit-quality",
                      type=int, default=90, metavar="N", dest="imagekit_quality")
    comp.add_argument("--cloudinary-name",
                      metavar="NAME", dest="cloudinary_name")
    comp.add_argument("--cloudinary-key",
                      metavar="KEY", dest="cloudinary_key")
    comp.add_argument("--cloudinary-secret",
                      metavar="SECRET", dest="cloudinary_secret")
    comp.add_argument("--cloudinary-quality",
                      choices=["auto", "auto:best", "auto:good", "auto:eco", "auto:low"],
                      default="auto:best", dest="cloudinary_quality")

    # ── Misc ─────────────────────────────────────────────────
    p.add_argument("--interactive", "-i", action="store_true",
                   help="Force interactive prompt mode")
    p.add_argument("--quiet", "-q", action="store_true",
                   help="Suppress detailed log output")
    p.add_argument("--skip-bootstrap", action="store_true", dest="skip_bootstrap",
                   help="Skip automatic tool/package installation check")

    return p


def args_to_cfg(args) -> dict:
    cfg = {
        "video_path":        args.video,
        "start_seconds":     HorizonProcessor.parse_time(args.start),
        "end_seconds":       HorizonProcessor.parse_time(args.end),
        "fps":               args.fps,
        "anim_frames":       min(args.anim_frames, MAX_FRAMES),
        "load_frames":       min(args.load_frames, MAX_FRAMES),
        "output_folder":     args.output,
        "new_pack_name":     args.name,
        "creator":           args.creator,
        "bgm_file":          args.bgm or "",
        "bgm_name":          args.bgm_name,
        "loading_bg_folder": args.loading_bg or "",
        "compress_method":   args.compress,
        "pillow_quality":    args.pillow_quality,
        "ffmpeg_qv":         args.ffmpeg_qv,
        "tinify_key":        args.tinify_key or "",
        "kraken_key":        args.kraken_key or "",
        "kraken_secret":     args.kraken_secret or "",
        "kraken_quality":    args.kraken_quality,
        "imagekit_key":      args.imagekit_key or "",
        "imagekit_secret":   args.imagekit_secret or "",
        "imagekit_urlendpoint": args.imagekit_urlendpoint or "",
        "imagekit_quality":  args.imagekit_quality,
        "cloudinary_name":   args.cloudinary_name or "",
        "cloudinary_key":    args.cloudinary_key or "",
        "cloudinary_secret": args.cloudinary_secret or "",
        "cloudinary_quality": args.cloudinary_quality,
    }
    return cfg


# ─────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────

def main():
    parser = build_parser()
    args   = parser.parse_args()

    # License agreement
    if not _check_license_cli():
        sys.exit(1)

    # Decide interactive vs non-interactive
    if args.interactive or not args.video:
        cfg = _run_interactive()
    else:
        cfg = args_to_cfg(args)

    verbose = not args.quiet if hasattr(args, "quiet") else True

    print("\n" + "═" * 60)
    print("  Building mcpack…")
    print("═" * 60)

    processor = HorizonProcessor(cfg, verbose=verbose)
    try:
        processor.process()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user.")
        processor.stop()
        processor.cleanup()
        sys.exit(1)
    except Exception as e:
        import traceback
        print(f"\n❌  Error: {e}")
        if verbose:
            traceback.print_exc()
        processor.cleanup()
        sys.exit(1)


if __name__ == "__main__":
    main()
