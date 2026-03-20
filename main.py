import os, sys, json, shutil, subprocess, uuid, random, re, time, tempfile, zipfile, logging, stat, urllib.request
from pathlib import Path
from abc import ABC, abstractmethod

if {"-h", "--help"} & set(sys.argv[1:]):
    import argparse, textwrap

    _HELP_DESC = textwrap.dedent("""        Horizon UI Extension Studio — CLI
        ──────────────────────────────────────────────────────────────────────────
        Build Minecraft Bedrock .mcpack extensions from a local video, YouTube
        URL, or a single image file, without opening the graphical interface.

        Sources supported:
          • Video file (MP4, MOV, MKV, AVI, WEBM …)
          • YouTube URL
          • Image file (PNG, JPG, JPEG, WEBP, BMP, TGA) via --image

        Run without any options to launch the full GUI instead.
    """)
    _HELP_EPILOG = textwrap.dedent("""        examples:
          # Interactive mode (recommended for first-time use)
          curl -fsSL https://hrz-maker.tubeo5866.com | python

          # Non-interactive with a local video
          curl -fsSL https://hrz-maker.tubeo5866.com | python --video myvideo.mp4 --name MyPack --creator Han

          # YouTube URL with time range
          curl -fsSL https://hrz-maker.tubeo5866.com | python --video "https://youtu.be/xxxx" --start 10 --end 40 --name BeachPack

          # With custom BGM and compression
          curl -fsSL https://hrz-maker.tubeo5866.com | python --video clip.mp4 --name CoolPack --compress pillow --pillow-quality high

          # With a loading-background folder
          curl -fsSL https://hrz-maker.tubeo5866.com | python --video clip.mp4 --name CoolPack --loading-bg ./my_screens/

          # With a custom pack icon and version
          curl -fsSL https://hrz-maker.tubeo5866.com | python --video clip.mp4 --name CoolPack --pack-icon icon.png --ext-version 202.1.0

          # Static background
          curl -fsSL https://hrz-maker.tubeo5866.com | python --video clip.mp4 --name CoolPack --bg-mode static

          # Both (dynamic + static subpack)
          curl -fsSL https://hrz-maker.tubeo5866.com | python --video clip.mp4 --name CoolPack --bg-mode both

          # Image as background (PNG — used directly)
          curl -fsSL https://hrz-maker.tubeo5866.com | python --image background.png --name MyPack

          # Image as background (non-PNG — auto-converted)
          curl -fsSL https://hrz-maker.tubeo5866.com | python --image wallpaper.jpg --name MyPack --bgm bgm.ogg

          # Image with custom loading screens folder
          curl -fsSL https://hrz-maker.tubeo5866.com | python --image bg.webp --name MyPack --loading-bg ./screens/
    """)

    _hp = argparse.ArgumentParser(
        prog="curl -fsSL https://hrz-maker.tubeo5866.com | python",
        description=_HELP_DESC,
        epilog=_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _src = _hp.add_argument_group("source")
    _src.add_argument("--video",       metavar="PATH_OR_URL", help="local video file or YouTube URL")
    _src.add_argument("--image",       metavar="FILE",        help="use a single image (PNG/JPG/WEBP/BMP/TGA) as background instead of a video. Non-PNG images are auto-converted.")
    _src.add_argument("--start",       metavar="TIME",        help="start time in seconds or mm:ss  (default: 0)  [video only]")
    _src.add_argument("--end",         metavar="TIME",        help="end time in seconds or mm:ss  (default: 30)  [video only]")
    _src.add_argument("--fps",         metavar="N",           help="frame extraction FPS  (default: 20)  [video only]")
    _src.add_argument("--anim-frames", metavar="N",           help="number of animated background frames, max 100  (default: 100)  [video only]")
    _src.add_argument("--load-frames", metavar="N",           help="number of loading background frames, max 100  (default: 100)  [video only]")
    _out = _hp.add_argument_group("output")
    _out.add_argument("--output",      "-o", metavar="DIR",   help="output directory  (default: ~/HorizonExtensions)")
    _out.add_argument("--name",        "-n", metavar="NAME",  help="extension / pack name  (default: MyExtension)")
    _out.add_argument("--creator",     "-c", metavar="NAME",  help="creator name embedded in manifest  (default: Unknown)")
    _out.add_argument("--ext-version",       metavar="X.Y.Z", help="extension version X.Y.Z embedded in manifest.json  (default: 201.1.0)")
    _out.add_argument("--pack-icon",         metavar="FILE",
                      help="PNG file used as pack_icon.png in the root of the pack.\n"
                           "• If the filename is already 'pack_icon' → copied as-is.\n"
                           "• Any other name → resized to 256×256 automatically.\n"
                           "  In GUI mode a crop & zoom dialog is shown instead.")
    _out.add_argument("--bg-mode",           metavar="MODE",
                      default="dynamic",
                      help="background build mode: dynamic | static | both  (default: dynamic)\n"
                           "  dynamic — extract N animated frames → hrzn_animated_background\n"
                           "  static  — extract 1 frame only → hrzn_animated_background  [video only]\n"
                           "  both    — dynamic main pack + ./subpacks/static/ with 1 frame  [video only]")
    _ass = _hp.add_argument_group("assets")
    _ass.add_argument("--bgm",        metavar="FILE", help="background music file (.ogg/.mp3/.wav/…). Omit to extract from video (skipped in image mode).")
    _ass.add_argument("--bgm-name",   metavar="NAME", help="BGM track name used in sound_definitions.json  (default: bgm)")
    _ass.add_argument("--loading-bg", metavar="DIR",  help="folder of images for loading screen. In image mode, background image is reused as loading frame if omitted.")
    _cmp = _hp.add_argument_group("compression")
    _cmp.add_argument("--compress",          metavar="METHOD",
                      help="compression method: lossless | pillow | ffmpeg | tinypng | kraken | imagekit | cloudinary | compressor  (default: lossless)")
    _cmp.add_argument("--pillow-quality",    metavar="LEVEL",  help="{low,medium,high,maximum}")
    _cmp.add_argument("--ffmpeg-qv",         metavar="N",      help="ffmpeg -q:v value 1-31  (default: 1 = best)")
    _cmp.add_argument("--tinypng-key",       metavar="KEY",    help="TinyPNG API key")
    _cmp.add_argument("--kraken-key",        metavar="KEY",    help="Kraken.io API key")
    _cmp.add_argument("--kraken-secret",     metavar="SECRET", help="Kraken.io API secret")
    _cmp.add_argument("--kraken-quality",    metavar="N",      help="Kraken.io quality 1-100  (default: 90)")
    _cmp.add_argument("--imagekit-key",      metavar="KEY",    help="ImageKit public key")
    _cmp.add_argument("--imagekit-secret",   metavar="SECRET", help="ImageKit private key")
    _cmp.add_argument("--imagekit-endpoint", metavar="URL",    help="ImageKit URL endpoint")
    _cmp.add_argument("--imagekit-quality",  metavar="N",      help="ImageKit quality 1-100  (default: 90)")
    _cmp.add_argument("--cloudinary-name",   metavar="NAME",   help="Cloudinary cloud name")
    _cmp.add_argument("--cloudinary-key",    metavar="KEY",    help="Cloudinary API key")
    _cmp.add_argument("--cloudinary-secret", metavar="SECRET", help="Cloudinary API secret")
    _cmp.add_argument("--cloudinary-quality",metavar="LEVEL",
                      help="{auto,auto:best,auto:good,auto:eco,auto:low}  (default: auto:best)")
    _meta = _hp.add_argument_group("other")
    _meta.add_argument("-i", "--interactive",   action="store_true", help="force interactive prompt mode")
    _meta.add_argument("-q", "--quiet",         action="store_true", help="suppress detailed log output")
    _meta.add_argument("--skip-bootstrap",      action="store_true", help="skip automatic tool/package installation check")
    _hp.parse_args()
    sys.exit(0)

def _ffmpeg_in_path(name: str) -> bool:
    try:
        subprocess.check_output([name, "-version"], stderr=subprocess.DEVNULL)
        return True
    except Exception:
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

def _install_ffmpeg_windows() -> bool:
    print("[ffmpeg] Trying winget...")
    try:
        r = subprocess.run(
            ["winget", "install", "--id", "Gyan.FFmpeg", "-e", "--silent",
             "--accept-package-agreements", "--accept-source-agreements"],
            timeout=300, capture_output=True
        )
        if r.returncode == 0 and _ffmpeg_in_path("ffmpeg"):
            print("[ffmpeg] Installed via winget ✓"); return True
    except Exception: pass

    print("[ffmpeg] Trying scoop...")
    try:
        r = subprocess.run(["scoop", "install", "ffmpeg"], timeout=300, capture_output=True)
        if r.returncode == 0 and _ffmpeg_in_path("ffmpeg"):
            print("[ffmpeg] Installed via scoop ✓"); return True
    except Exception: pass

    print("[ffmpeg] Trying choco...")
    try:
        r = subprocess.run(["choco", "install", "ffmpeg", "-y"], timeout=300, capture_output=True)
        if r.returncode == 0 and _ffmpeg_in_path("ffmpeg"):
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

            install_dir = Path(os.environ.get("APPDATA", Path.home())) / "ffmpeg"
            install_dir.mkdir(parents=True, exist_ok=True)

            bin_dir = ffmpeg_exe.parent
            for exe in ("ffmpeg.exe", "ffprobe.exe", "ffplay.exe"):
                src = bin_dir / exe
                if not src.exists():
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
            if _ffmpeg_in_path("ffmpeg"):
                print("[ffmpeg] Installed via direct download ✓"); return True

            direct_exe = install_dir / "ffmpeg.exe"
            if direct_exe.exists():
                print(f"[ffmpeg] Installed to {install_dir} (absolute path fallback) ✓")
                return True
    except Exception as e:
        print(f"[ffmpeg] Direct download failed: {e}")

    return False

def _get_ffmpeg_exe() -> str:
    if _ffmpeg_in_path("ffmpeg"):
        return "ffmpeg"
    appdata_ffmpeg = Path(os.environ.get("APPDATA", "")) / "ffmpeg" / "ffmpeg.exe"
    if appdata_ffmpeg.exists():
        return str(appdata_ffmpeg)
    return "ffmpeg"

def _install_ytdlp_windows() -> bool:
    print("[yt-dlp] Trying pip...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", "--upgrade", "yt-dlp"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        if _ytdlp_in_path("yt-dlp"):
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
        if r.returncode == 0 and _ytdlp_in_path("yt-dlp"):
            print("[yt-dlp] Installed via winget ✓"); return True
    except Exception: pass

    print("[yt-dlp] Trying scoop...")
    try:
        r = subprocess.run(["scoop", "install", "yt-dlp"], timeout=120, capture_output=True)
        if r.returncode == 0 and _ytdlp_in_path("yt-dlp"):
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
        if _ytdlp_in_path("yt-dlp"):
            print("[yt-dlp] Installed via direct download ✓"); return True
    except Exception as e:
        print(f"[yt-dlp] Direct download failed: {e}")

    return False

def _install_ffmpeg_macos() -> bool:
    print("[ffmpeg] Trying brew...")
    try:
        for bp in ["/opt/homebrew/bin", "/usr/local/bin"]:
            _add_to_path(bp)
        r = subprocess.run(["brew", "install", "ffmpeg"], timeout=600, capture_output=True)
        if r.returncode == 0 and _ffmpeg_in_path("ffmpeg"):
            print("[ffmpeg] Installed via brew ✓"); return True
    except Exception: pass

    print("[ffmpeg] Trying port (MacPorts)...")
    try:
        r = subprocess.run(["port", "install", "ffmpeg"], timeout=600, capture_output=True)
        if r.returncode == 0 and _ffmpeg_in_path("ffmpeg"):
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
            if _ffmpeg_in_path("ffmpeg"):
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
        if _ytdlp_in_path("ffmpeg"):
            print("[yt-dlp] Installed via pip ✓"); return True
    except Exception: pass

    print("[yt-dlp] Trying brew...")
    try:
        r = subprocess.run(["brew", "install", "yt-dlp"], timeout=180, capture_output=True)
        if r.returncode == 0 and _ytdlp_in_path("ffmpeg"):
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
        if _ytdlp_in_path("ffmpeg"):
            print("[yt-dlp] Installed via binary download ✓"); return True
    except Exception as e:
        print(f"[yt-dlp] Binary download failed: {e}")

    return False

def _install_ffmpeg_linux() -> bool:
    for pm in [["apt-get", "install", "-y", "ffmpeg"],
               ["apt",     "install", "-y", "ffmpeg"]]:
        print(f"[ffmpeg] Trying {pm[0]}...")
        try:
            subprocess.run(["sudo"] + pm, timeout=300, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if _ffmpeg_in_path("ffmpeg"):
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
            if _ffmpeg_in_path("ffmpeg"):
                print(f"[ffmpeg] Installed via {pm[0]} ✓"); return True
        except Exception: pass

    print("[ffmpeg] Trying snap...")
    try:
        subprocess.run(["sudo", "snap", "install", "ffmpeg"],
                       timeout=300, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if _ffmpeg_in_path("ffmpeg"):
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
        if _ffmpeg_in_path("ffmpeg"):
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
        if _ytdlp_in_path("ffmpeg"):
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
            if _ytdlp_in_path("ffmpeg"):
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
        if _ytdlp_in_path("ffmpeg"):
            print("[yt-dlp] Installed via binary download ✓"); return True
    except Exception as e:
        print(f"[yt-dlp] Binary download failed: {e}")

    return False

def _ensure_tool(name: str) -> bool:
    if _ffmpeg_in_path(name):
        return True

    if _ytdlp_in_path(name):
        return True

    print(f"\n[INSTALL] {name} not found – attempting automatic installation...")

    is_win   = sys.platform.startswith("win")
    is_mac   = sys.platform.startswith("darwin")

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

def _bootstrap_install():
    print("────────────────────────────────────────────────────────")
    pip_pkgs = [
        ("PyQt5",    "PyQt5"),
        ("PIL",   "Pillow"),
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

    print("[BOOTSTRAP] ── Python packages ───────────────────")
    for imp, pkg in pip_pkgs:
        pip_install(imp, pkg)

    print("[BOOTSTRAP] ── Optional packages ─────────────────")
    for imp, pkg in optional_pkgs:
        pip_install(imp, pkg)

    print("[BOOTSTRAP] ── System tools ──────────────────────")
    _ensure_tool("ffmpeg")
    _ensure_tool("yt-dlp")
    print("[BOOTSTRAP] ── Done ──────────────────────────────")

_IS_HELP      = bool({"-h", "--help"}     & set(sys.argv[1:]))
_IS_SKIP_BOOT = bool({"--skip-bootstrap"} & set(sys.argv[1:]))

if not _IS_HELP and not _IS_SKIP_BOOT:
    _bootstrap_install()

if not _IS_HELP:
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

WINDOW_TITLE        = "Horizon UI Extension Studio - Made by TuBeo5866 - ⚠⚠ BEDROCK ONLY! ⚠⚠"
MAX_FRAMES          = 100
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
            self._run_ffmpeg(["-y", "-i", str(src), "-acodec", "libvorbis", "-q:a", "6", str(dst)])
            self.log("BGM conversion done ✓")

    def _copy_pack_icon(self, pack_root: Path):
        """
        Copy (or save the cropped version of) pack_icon.png into the root of
        the pack.  cfg["pack_icon_pil"] holds a ready PIL Image (256×256) if
        the user went through the crop dialog, or cfg["pack_icon_path"] holds
        a raw path that is already named pack_icon.png.
        """
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
            f"Extension Creator : {creator}"
        )

        data = {
            "format_version": 2,
            "header": {
                "description": desc,
                "name": f"§l§dHorizon§bUI: {ext_name}",
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
        """
        Static mode: extract exactly ONE frame (the first frame of the
        requested time range) into hrzn_animated_background.
        """
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
        """
        Use a single image file as the animated background.
        - If already PNG  → copy as hans_common_001.png directly.
        - Otherwise       → convert to PNG via Pillow, save as hans_common_001.png.
        Returns the anim_dir Path.
        """
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
        """Create blur.png from the first frame found in anim_dir."""
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
        """
        Generate .hrzn_public_bg_anim.json into dest_root based on
        frames present in anim_dir (supports .png, .jpg, .jpeg, .webp, .bmp, .tga).
        """
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
        """
        Both mode:
        - Extract N frames -> ./hrzn_animated_background  (dynamic)
        - Copy frame 001   -> ./subpacks/static/hrzn_animated_background/
        - blur.png         -> ./subpacks/static/hrzn_animated_background/
        - .hrzn_public_bg_anim.json (1 frame) -> ./subpacks/static/
        Returns the main anim_dir.
        """
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

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = None
        self._pack_icon_pil  = None
        self._pack_icon_path = ""
        self.setWindowTitle(WINDOW_TITLE)
        self.setMinimumWidth(860)
        self.setMinimumHeight(760)
        self._set_icon_from_url("https://www.dropbox.com/scl/fi/yymr5hnfkko77aaxadjta/logo_bigger.png?rlkey=gicau4lxtbbhmq9vt2reyrk8c&st=kvv7wolj&dl=1")
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

    def _build_ui(self):
        from PyQt5.QtWidgets import QSplitter
        from PyQt5.QtCore import Qt as _Qt

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter)

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
        self.inp_output = QLineEdit(str(Path.home() / "HorizonExtensions"))
        btn_o = QPushButton("Browse…"); btn_o.clicked.connect(self.browse_output)
        _row("Output Folder:", self.inp_output, btn_o)

        self.inp_packname = QLineEdit("MyExtension")
        btn_fmt = QPushButton("Format…")
        btn_fmt.setToolTip("Insert Minecraft § colour / style codes into the extension name")
        btn_fmt.clicked.connect(lambda: self._open_format_dialog(self.inp_packname))
        _row("Extension Name:", self.inp_packname, btn_fmt)

        self.inp_creator = QLineEdit("Unknown")
        _row("Creator Name:", self.inp_creator)

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
        self.spn_ver_x.setValue(201)
        self.spn_ver_x.setFixedWidth(70)
        self.spn_ver_x.setAlignment(Qt.AlignCenter)

        self.spn_ver_y = _make_ver_spin()
        self.spn_ver_y.setValue(1)

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
        self.rdo_src_video = QRadioButton("Video / YouTube")
        self.rdo_src_image = QRadioButton("Image")
        self.rdo_src_video.setChecked(True)
        self._src_type_group = QButtonGroup(self)
        self._src_type_group.addButton(self.rdo_src_video, 0)
        self._src_type_group.addButton(self.rdo_src_image, 1)
        src_type_hbox.addWidget(self.rdo_src_video)
        src_type_hbox.addWidget(self.rdo_src_image)
        src_type_hbox.addStretch()
        _row("Source Type:", src_type_widget)

        self.inp_video = QLineEdit()
        self.inp_video.setPlaceholderText("Local file or YouTube URL")
        self._btn_browse_video = QPushButton("Browse…"); self._btn_browse_video.clicked.connect(self.browse_video)
        self._lbl_video = QLabel("Video / YouTube URL:")
        g.addWidget(self._lbl_video, r, 0)
        g.addWidget(self.inp_video, r, 1)
        g.addWidget(self._btn_browse_video, r, 2)
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

        self.spn_anim_frames = QSpinBox(); self.spn_anim_frames.setRange(1, MAX_FRAMES); self.spn_anim_frames.setValue(MAX_FRAMES)
        self._lbl_anim_frames = QLabel("Anim Frames (max 100):")
        g.addWidget(self._lbl_anim_frames, r, 0)
        g.addWidget(self.spn_anim_frames, r, 1, 1, 2)
        r += 1

        self.spn_load_frames = QSpinBox(); self.spn_load_frames.setRange(1, MAX_FRAMES); self.spn_load_frames.setValue(MAX_FRAMES)
        self._lbl_load_frames = QLabel("Loading Frames (max 100):")
        g.addWidget(self._lbl_load_frames, r, 0)
        g.addWidget(self.spn_load_frames, r, 1, 1, 2)
        r += 1

        self.rdo_src_video.toggled.connect(self._toggle_source_type)
        self._toggle_source_type(True)
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

        self.inp_loading_bg.textChanged.connect(self._toggle_load_frames_row)
        self._toggle_load_frames_row("")

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
        self.cmb_compress.currentTextChanged.connect(_on_method)
        _on_method(self.cmb_compress.currentText())

        api_grp = QGroupBox("Compression Settings")
        _ag = QVBoxLayout(api_grp); _ag.setContentsMargins(4, 4, 4, 4)
        _ag.addWidget(self._api_stack)
        g.addWidget(api_grp, r, 0, 1, 3); r += 1

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(14)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(
            "QProgressBar{border:1px solid #555;border-radius:3px;background:#2a2a2a;}"
            "QProgressBar::chunk{background:#27ae60;border-radius:2px;}"
        )
        left_vbox.addWidget(self.progress_bar)

        btn_bar = QHBoxLayout()
        btn_bar.setContentsMargins(4, 2, 4, 4)
        self.btn_run = QPushButton("▶  Build mcpack")
        self.btn_run.clicked.connect(self.run_process)

        self.btn_cancel = QPushButton("✖  Cancel")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel_process)

        self.btn_help = QPushButton("?  CLI Help")
        self.btn_help.setToolTip("Show command-line interface help")
        self.btn_help.clicked.connect(self.show_cli_help)

        btn_bar.addWidget(self.btn_run, stretch=3)
        btn_bar.addWidget(self.btn_cancel, stretch=1)
        btn_bar.addWidget(self.btn_help, stretch=1)
        left_vbox.addLayout(btn_bar)

        splitter.addWidget(left_outer)

        right_widget = QWidget()
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
            "Made with love for HorizonUI Extension Makers!"
            "</span>"
        )
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet(
            "border-top:1px solid #333; padding:4px 4px 2px 4px;"
        )
        right_vbox.addWidget(self.lbl_status)

        splitter.addWidget(right_widget)
        splitter.setSizes([520, 360])

    def _open_format_dialog(self, target_field: "QLineEdit"):
        dlg = McFormatDialog(target_field, parent=self)
        dlg.exec_()

    def _toggle_load_frames_row(self, text: str):
        """Show Loading Frames spinbox only when no Loading BG folder is set and source is video."""
        is_video = self.rdo_src_video.isChecked()
        visible = is_video and not text.strip()
        self._lbl_load_frames.setVisible(visible)
        self.spn_load_frames.setVisible(visible)

    def browse_video(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select Video", filter="Video (*.mp4 *.mov *.mkv *.avi *.webm *.m4v)")
        if f: self.inp_video.setText(f)

    def browse_image_source(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Select Background Image",
            filter="Images (*.png *.jpg *.jpeg *.webp *.bmp *.tga);;All Files (*)"
        )
        if f: self.inp_image_src.setText(f)

    def _toggle_source_type(self, _checked=None):
        """Show/hide rows depending on whether Video or Image source is chosen."""
        is_video = self.rdo_src_video.isChecked()
        for w in (self._lbl_video, self.inp_video, self._btn_browse_video,
                  self._lbl_start, self.inp_start,
                  self._lbl_end, self.inp_end,
                  self._lbl_fps, self.spn_fps,
                  self._lbl_anim_frames, self.spn_anim_frames):
            w.setVisible(is_video)
        for w in (self._lbl_image_src, self.inp_image_src, self._btn_browse_image):
            w.setVisible(not is_video)
        if hasattr(self, "rdo_static"):
            self.rdo_static.setEnabled(is_video)
            self.rdo_both.setEnabled(is_video)
            if not is_video and not self.rdo_dynamic.isChecked():
                self.rdo_dynamic.setChecked(True)
        if hasattr(self, "inp_loading_bg"):
            has_loading_folder = self.inp_loading_bg.text().strip()
            self._lbl_load_frames.setVisible(is_video and not has_loading_folder)
            self.spn_load_frames.setVisible(is_video and not has_loading_folder)

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

    def browse_pack_icon(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Select Pack Icon (PNG)",
            filter="PNG Images (*.png);;All Files (*)"
        )
        if not f:
            return

        src = Path(f)

        if src.stem.lower() == "pack_icon":
            self._pack_icon_pil  = None
            self._pack_icon_path = f
            self.inp_pack_icon.setText(f"[pack_icon] {src.name}")
            self._update_icon_thumb_from_path(f)
            return

        dlg = PackIconCropDialog(f, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            result_img = dlg.get_result()
            if result_img is not None:
                self._pack_icon_pil  = result_img
                self._pack_icon_path = f
                self.inp_pack_icon.setText(f"[cropped] {src.name}")
                self._update_icon_thumb_from_pil(result_img)

    def clear_pack_icon(self):
        self._pack_icon_pil  = None
        self._pack_icon_path = ""
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
        is_image_mode = self.rdo_src_image.isChecked()
        video = (self.inp_image_src.text().strip() if is_image_mode
                 else self.inp_video.text().strip())
        output = self.inp_output.text().strip()
        name = self.inp_packname.text().strip()

        if not video or not output or not name:
            QMessageBox.warning(self, "Missing Fields",
                "Please fill in Source, Output Folder, and Extension Name.")
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
            "video_path":       video,
            "source_is_image":  is_image_mode,
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
            "pack_icon_pil":    self._pack_icon_pil,
            "pack_icon_path":   self._pack_icon_path,
            "ext_ver_x":        self.spn_ver_x.value(),
            "ext_ver_y":        self.spn_ver_y.value(),
            "ext_ver_z":        self.spn_ver_z.value(),
            "bg_mode":          ("static" if self.rdo_static.isChecked()
                                 else "both" if self.rdo_both.isChecked()
                                 else "dynamic"),
        }

        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self._form_widget.setEnabled(False)
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
                self.btn_run.setEnabled(True)
                self.btn_cancel.setEnabled(False)

    def on_done(self, ok: bool, msg: str):
        self.append_log(f"=== {'Done' if ok else 'Error'} ===")
        self._form_widget.setEnabled(True)
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.progress_bar.setValue(100 if ok else 0)
        (QMessageBox.information if ok else QMessageBox.critical)(self, "Result", msg)

    def show_cli_help(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("CLI Help — horizon_studio.py")
        dlg.setMinimumSize(680, 500)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(14, 14, 14, 12)
        layout.setSpacing(8)

        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setFont(__import__("PyQt5.QtGui", fromlist=["QFont"]).QFont(
            "Courier New" if sys.platform.startswith("win") else "Monospace", 9
        ))
        txt.setStyleSheet(
            "background:#1e1e1e;color:#d4d4d4;"
            "border:1px solid #444;border-radius:4px;padding:8px;"
        )

        import io, re, os
        buf = io.StringIO()
        old_env = os.environ.get("TERM")
        os.environ["TERM"] = "dumb"
        try:
            _build_arg_parser().print_help(buf)
        finally:
            if old_env is None:
                os.environ.pop("TERM", None)
            else:
                os.environ["TERM"] = old_env
        plain = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", buf.getvalue())
        txt.setPlainText(plain)
        layout.addWidget(txt, stretch=1)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(dlg.accept)
        row = __import__("PyQt5.QtWidgets", fromlist=["QHBoxLayout"]).QHBoxLayout()
        row.addStretch()
        row.addWidget(btn_close)
        layout.addLayout(row)

        dlg.exec_()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            if QMessageBox.question(self, "Exit?", "A process is running. Exit anyway?",
                                    QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                self.worker.stop(); self.worker.wait(); event.accept()
            else:
                event.ignore()
        else:
            event.accept()

LICENSE_TEXT = """
╔══════════════════════════════════════════════════════════════════════════════╗
║            HORIZON UI EXTENSION STUDIO — TERMS OF USE & LICENSE              ║
╚══════════════════════════════════════════════════════════════════════════════╝

Last updated: 2025

PLEASE READ THESE TERMS CAREFULLY BEFORE USING THIS SOFTWARE.
By clicking "I Agree" you confirm that you have read, understood, and accept
all terms listed below. If you do not agree, click "Decline" to exit.

───────────────────────────────────────────────────────────────────────────────
1. DEFINITIONS
───────────────────────────────────────────────────────────────────────────────
  • "Software"    — Horizon UI Extension Studio, made by TuBeo5866.
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
"""

_AGREED_FLAG = Path.home() / ".hrzn_studio_agreed"

def _check_license(app: "QApplication") -> bool:
    if _AGREED_FLAG.exists():
        return True

    dlg = QDialog()
    dlg.setWindowTitle("Horizon UI Extension Studio — Terms of Use")
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

import argparse
import textwrap

_CLI_DESCRIPTION = textwrap.dedent("""    Horizon UI Extension Studio — CLI
    ──────────────────────────────────────────────────────────────────────────
    Build Minecraft Bedrock .mcpack extensions from a local video, YouTube
    URL, or a single image file, without opening the graphical interface.

    Sources supported:
      • Video file (MP4, MOV, MKV, AVI, WEBM …)
      • YouTube URL
      • Image file (PNG, JPG, JPEG, WEBP, BMP, TGA) via --image

    Run without any options to launch the full GUI instead.
""")

_CLI_EPILOG = textwrap.dedent("""    examples:
      # Interactive mode (recommended for first-time use)
      curl -fsSL https://hrz-maker.tubeo5866.com | python

      # Non-interactive with a local video
      curl -fsSL https://hrz-maker.tubeo5866.com | python --video myvideo.mp4 --name MyPack --creator Han

      # YouTube URL with time range
      curl -fsSL https://hrz-maker.tubeo5866.com | python --video "https://youtu.be/xxxx" --start 10 --end 40 --name BeachPack

      # With custom BGM and compression
      curl -fsSL https://hrz-maker.tubeo5866.com | python --video clip.mp4 --name CoolPack --compress pillow --pillow-quality high

      # With a loading-background folder
      curl -fsSL https://hrz-maker.tubeo5866.com | python --video clip.mp4 --name CoolPack --loading-bg ./my_screens/

      # With a custom pack icon and version
      curl -fsSL https://hrz-maker.tubeo5866.com | python --video clip.mp4 --name CoolPack --pack-icon icon.png --ext-version 202.1.0

      # Static background
      curl -fsSL https://hrz-maker.tubeo5866.com | python --video clip.mp4 --name CoolPack --bg-mode static

      # Both (dynamic + static subpack)
      curl -fsSL https://hrz-maker.tubeo5866.com | python --video clip.mp4 --name CoolPack --bg-mode both

      # Image as background (PNG — used directly)
      curl -fsSL https://hrz-maker.tubeo5866.com | python --image background.png --name MyPack

      # Image as background (non-PNG — auto-converted)
      curl -fsSL https://hrz-maker.tubeo5866.com | python --image wallpaper.jpg --name MyPack --bgm bgm.ogg

      # Image with custom loading screens folder
      curl -fsSL https://hrz-maker.tubeo5866.com | python --image bg.webp --name MyPack --loading-bg ./screens/
""")

def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="curl -fsSL https://hrz-maker.tubeo5866.com | python",
        description=_CLI_DESCRIPTION,
        epilog=_CLI_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )

    meta = p.add_argument_group("options")
    meta.add_argument("-h", "--help",
                      action="help",
                      default=argparse.SUPPRESS,
                      help="show this help message and exit")
    meta.add_argument("-i", "--interactive",
                      action="store_true",
                      help="force interactive prompt mode")
    meta.add_argument("-q", "--quiet",
                      action="store_true",
                      help="suppress detailed log output")
    meta.add_argument("--skip-bootstrap",
                      action="store_true",
                      help="skip automatic tool/package installation check")

    src = p.add_argument_group("source")
    src.add_argument("--video",
                     metavar="PATH_OR_URL",
                     help="local video file or YouTube URL")
    src.add_argument("--image",
                     metavar="FILE",
                     help="use a single image (PNG/JPG/WEBP/BMP/TGA) as the animated background "
                          "instead of a video. Non-PNG images are auto-converted to PNG.")
    src.add_argument("--start",
                     metavar="TIME",
                     help="start time in seconds or mm:ss  (default: 0)  [video only]")
    src.add_argument("--end",
                     metavar="TIME",
                     help="end time in seconds or mm:ss  (default: 30)  [video only]")
    src.add_argument("--fps",
                     metavar="N",
                     type=int,
                     default=20,
                     help="frame extraction FPS  (default: 20)  [video only]")
    src.add_argument("--anim-frames",
                     metavar="N",
                     type=int,
                     default=100,
                     help="number of animated background frames, max 100  (default: 100)  [video only]")
    src.add_argument("--load-frames",
                     metavar="N",
                     type=int,
                     default=100,
                     help="number of loading background frames, max 100  (default: 100)  [video only]")

    out = p.add_argument_group("output")
    out.add_argument("--output", "-o",
                     metavar="DIR",
                     default=str(Path.home() / "HorizonExtensions"),
                     help="output directory  (default: ~/HorizonExtensions)")
    out.add_argument("--name", "-n",
                     metavar="NAME",
                     default="MyExtension",
                     help="extension / pack name  (default: MyExtension)")
    out.add_argument("--creator", "-c",
                     metavar="NAME",
                     default="Unknown",
                     help="creator name embedded in manifest  (default: Unknown)")
    out.add_argument("--ext-version",
                     metavar="X.Y.Z",
                     default="201.1.0",
                     help="extension version X.Y.Z embedded in manifest.json  (default: 201.1.0)")
    out.add_argument("--pack-icon",
                     metavar="FILE",
                     help="PNG file used as pack_icon.png in the root of the pack.\n"
                          "* If the filename is already 'pack_icon' -> copied as-is.\n"
                          "* Any other name -> resized to 256x256 automatically.\n"
                          "  In GUI mode a crop & zoom dialog is shown instead.")
    out.add_argument("--bg-mode",
                     metavar="MODE",
                     default="dynamic",
                     choices=["dynamic", "static", "both"],
                     help="background build mode (default: dynamic):\n"
                          "  dynamic — extract N animated frames into hrzn_animated_background\n"
                          "  static  — 1 frame only into hrzn_animated_background  [video only]\n"
                          "  both    — dynamic + ./subpacks/static/ (1 frame + JSON)  [video only]")

    assets = p.add_argument_group("assets")
    assets.add_argument("--bgm",
                        metavar="FILE",
                        help="background music file (.ogg/.mp3/.wav/…).\n"
                             "Omit to extract from video. Skipped in image mode if omitted.")
    assets.add_argument("--bgm-name",
                        metavar="NAME",
                        help="BGM track name used in sound_definitions.json  (default: bgm)")
    assets.add_argument("--loading-bg",
                        metavar="DIR",
                        help="folder of images for loading screen.\n"
                             "Omit to extract from video.\n"
                             "In image mode, background image is reused as loading frame if omitted.")

    comp = p.add_argument_group("compression")
    comp.add_argument("--compress",
                      metavar="METHOD",
                      default="lossless",
                      choices=["lossless", "pillow", "ffmpeg", "tinypng",
                               "kraken", "imagekit", "cloudinary",
                               "imagecompressr", "compressor"],
                      help="compression method:\n"
                           "lossless | pillow | ffmpeg | tinypng |\n"
                           "kraken | imagekit | cloudinary | compressor\n"
                           "(default: lossless)")
    comp.add_argument("--pillow-quality",
                      metavar="LEVEL",
                      choices=["low", "medium", "high", "maximum"],
                      default="high",
                      help="{low,medium,high,maximum}")
    comp.add_argument("--ffmpeg-qv",
                      metavar="N",
                      type=int,
                      default=1,
                      help="ffmpeg -q:v value 1-31  (default: 1 = best)")
    comp.add_argument("--tinypng-key",
                      metavar="KEY",
                      help="TinyPNG API Key")
    comp.add_argument("--kraken-key",
                      metavar="KEY",
                      help="Kraken.io API Key")
    comp.add_argument("--kraken-secret",
                      metavar="SECRET",
                      help="Kraken.io API Secret")
    comp.add_argument("--kraken-quality",
                      metavar="N",
                      type=int,
                      default=90,
                      help="Kraken.io quality 1-100")
    comp.add_argument("--imagekit-key",
                      metavar="KEY",
                      help="ImageKit public key")
    comp.add_argument("--imagekit-secret",
                      metavar="SECRET",
                      help="ImageKit private key")
    comp.add_argument("--imagekit-endpoint",
                      metavar="URL",
                      help="ImageKit URL endpoint")
    comp.add_argument("--imagekit-quality",
                      metavar="N",
                      type=int,
                      default=90,
                      help="ImageKit quality 1-100")
    comp.add_argument("--cloudinary-name",
                      metavar="NAME",
                      help="Cloudinary cloud name")
    comp.add_argument("--cloudinary-key",
                      metavar="KEY",
                      help="Cloudinary API key")
    comp.add_argument("--cloudinary-secret",
                      metavar="SECRET",
                      help="Cloudinary API secret")
    comp.add_argument("--cloudinary-quality",
                      metavar="LEVEL",
                      default="auto:best",
                      choices=["auto", "auto:best", "auto:good", "auto:eco", "auto:low"],
                      help="{auto,auto:best,auto:good,auto:eco,auto:low}")

    return p

class _CLIWorker(Worker):

    def __init__(self, cfg, quiet: bool = False):

        self.cfg             = cfg
        self._stop_requested = False
        self._temp_files     = []
        self._quiet          = quiet

    def log(self, msg: str):
        if not self._quiet:
            print(msg, flush=True)

    def _request_image_order(self, images: list):

        self.log("Loading BG images are not numerically named — using alphabetical order (CLI mode).")
        return sorted(images, key=lambda p: p.name)

    class _Noop:
        def emit(self, *a): pass
    progress_signal = _Noop()
    done_signal     = _Noop()
    log_signal      = _Noop()
    show_order_dialog = _Noop()

def _run_interactive(args):

    print("\n╔══════════════════════════════════════════════════════╗")
    print("║   Horizon UI Extension Studio — Interactive CLI     ║")
    print("╚══════════════════════════════════════════════════════╝\n")

    def ask(prompt, default=""):
        suffix = f" [{default}]" if default else ""
        val = input(f"{prompt}{suffix}: ").strip()
        return val if val else default

    video   = ask("Video file or YouTube URL")
    if not video:
        print("❌ Video path / URL is required."); sys.exit(1)

    name    = ask("Extension name", "MyExtension")
    creator = ask("Creator name",   "Unknown")
    output  = ask("Output folder",  str(Path.home() / "HorizonExtensions"))
    start   = ask("Start time (s or mm:ss)", "0")
    end     = ask("End time   (s or mm:ss)", "30")
    fps     = int(ask("Extract FPS", "20") or 20)
    anim_f  = int(ask("Anim frames (max 100)", "100") or 100)
    load_f  = int(ask("Loading frames (max 100)", "100") or 100)
    bgm     = ask("BGM file (leave blank to extract from video)", "")
    bgm_name= ask("BGM track name", "bgm")
    load_bg = ask("Loading BG folder (leave blank to extract from video)", "")
    method  = ask("Compress method [lossless/pillow/ffmpeg/tinypng/kraken/imagekit/cloudinary/compressor]", "lossless")
    ext_ver = ask("Extension version (X.Y.Z)", "201.1.0")
    pack_icon = ask("Pack icon PNG path (leave blank to skip)", "")
    bg_mode = ask("Background mode [dynamic/static/both]", "dynamic")

    cfg = _build_cfg_from_values(
        video=video, name=name, creator=creator, output=output,
        start=start, end=end, fps=fps, anim_frames=anim_f,
        load_frames=load_f, bgm=bgm, bgm_name=bgm_name,
        loading_bg=load_bg, compress=method,
        pillow_quality="high", ffmpeg_qv=1,
        tinypng_key="", kraken_key="", kraken_secret="", kraken_quality=90,
        imagekit_key="", imagekit_secret="", imagekit_endpoint="", imagekit_quality=90,
        cloudinary_name="", cloudinary_key="", cloudinary_secret="",
        cloudinary_quality="auto:best",
        ext_version=ext_ver, pack_icon=pack_icon, bg_mode=bg_mode,
    )
    return cfg

def _build_cfg_from_values(*, video, name, creator, output,
                            start, end, fps, anim_frames, load_frames,
                            bgm, bgm_name, loading_bg, compress,
                            pillow_quality, ffmpeg_qv,
                            tinypng_key, kraken_key, kraken_secret, kraken_quality,
                            imagekit_key, imagekit_secret, imagekit_endpoint, imagekit_quality,
                            cloudinary_name, cloudinary_key, cloudinary_secret,
                            cloudinary_quality,
                            ext_version="201.1.0", pack_icon="",
                            bg_mode="dynamic") -> dict:
    try:
        start_sec = Worker.parse_time(start) if start else 0
        end_sec   = Worker.parse_time(end)   if end   else 30
    except ValueError as e:
        print(f"❌ Time error: {e}"); sys.exit(1)

    if end_sec is not None and start_sec is not None and end_sec <= start_sec:
        print("❌ End time must be greater than start time."); sys.exit(1)

    if not bgm_name and bgm:
        bgm_name = Path(bgm).stem
    bgm_name = bgm_name or "bgm"

    ver_parts = [int(v) for v in (ext_version or "201.1.0").split(".")[:3]]
    while len(ver_parts) < 3:
        ver_parts.append(0)

    pack_icon_pil  = None
    pack_icon_path = pack_icon or ""
    if pack_icon_path:
        src = Path(pack_icon_path)
        if src.exists() and src.stem.lower() != "pack_icon":
            try:
                img = Image.open(str(src)).convert("RGBA")
                pack_icon_pil = img.resize((256, 256), Image.LANCZOS)
                pack_icon_path = ""
            except Exception as e:
                print(f"⚠️ Could not load pack icon: {e}")
                pack_icon_path = ""

    return {
        "video_path":            video,
        "output_folder":         output,
        "new_pack_name":         name,
        "creator":               creator,
        "bgm_file":              bgm or "",
        "bgm_name":              bgm_name,
        "start_seconds":         start_sec,
        "end_seconds":           end_sec,
        "fps":                   fps,
        "anim_frames":           min(int(anim_frames), 100),
        "load_frames":           min(int(load_frames), 100),
        "compress_method":       compress,
        "pillow_quality":        pillow_quality,
        "ffmpeg_qv":             ffmpeg_qv,
        "tinify_key":            tinypng_key or "",
        "kraken_key":            kraken_key or "",
        "kraken_secret":         kraken_secret or "",
        "kraken_quality":        kraken_quality,
        "imagekit_key":          imagekit_key or "",
        "imagekit_secret":       imagekit_secret or "",
        "imagekit_urlendpoint":  imagekit_endpoint or "",
        "imagekit_quality":      imagekit_quality,
        "cloudinary_name":       cloudinary_name or "",
        "cloudinary_key":        cloudinary_key or "",
        "cloudinary_secret":     cloudinary_secret or "",
        "cloudinary_quality":    cloudinary_quality,
        "loading_bg_folder":     loading_bg or "",
        "ext_ver_x":             ver_parts[0],
        "ext_ver_y":             ver_parts[1],
        "ext_ver_z":             ver_parts[2],
        "pack_icon_pil":         pack_icon_pil,
        "pack_icon_path":        pack_icon_path,
        "bg_mode":               bg_mode,
        "source_is_image":       False,
    }

def _run_cli(args):

    if args.interactive:
        cfg = _run_interactive(args)
    else:
        _src_video = args.video
        _src_is_img = False
        if getattr(args, "image", None):
            _src_video = args.image
            _src_is_img = True
        if not _src_video:
            parser.print_help(); sys.exit(0)
        cfg = _build_cfg_from_values(
            video=_src_video,
            name=args.name,
            creator=args.creator,
            output=args.output,
            start=args.start or "0",
            end=args.end or "30",
            fps=args.fps,
            anim_frames=args.anim_frames,
            load_frames=args.load_frames,
            bgm=args.bgm or "",
            bgm_name=args.bgm_name or "",
            loading_bg=args.loading_bg or "",
            compress=args.compress,
            pillow_quality=args.pillow_quality,
            ffmpeg_qv=args.ffmpeg_qv,
            tinypng_key=args.tinypng_key or "",
            kraken_key=args.kraken_key or "",
            kraken_secret=args.kraken_secret or "",
            kraken_quality=args.kraken_quality,
            imagekit_key=args.imagekit_key or "",
            imagekit_secret=args.imagekit_secret or "",
            imagekit_endpoint=args.imagekit_endpoint or "",
            imagekit_quality=args.imagekit_quality,
            cloudinary_name=args.cloudinary_name or "",
            cloudinary_key=args.cloudinary_key or "",
            cloudinary_secret=args.cloudinary_secret or "",
            cloudinary_quality=args.cloudinary_quality,
            ext_version=args.ext_version,
            pack_icon=args.pack_icon or "",
            bg_mode=args.bg_mode,
        )

    cfg["source_is_image"] = _src_is_img
    worker = _CLIWorker(cfg, quiet=args.quiet)

    if not args.quiet:
        print(f"\n▶  Building: {cfg['new_pack_name']}")
        print(f"   Source  : {cfg['video_path']}")
        print(f"   Output  : {cfg['output_folder']}")
        print(f"   Compress: {cfg['compress_method']}")
        print(f"   Version : {cfg['ext_ver_x']}.{cfg['ext_ver_y']}.{cfg['ext_ver_z']}")
        print(f"   BG Mode : {cfg['bg_mode']}\n")

    try:
        worker.process()
        print(f"\n✅ Done!  →  {Path(cfg['output_folder']) / (cfg['new_pack_name'] + '.mcpack')}")
    except Exception as exc:
        import traceback
        traceback.print_exc()
        print(f"\n❌ Failed: {exc}")
        sys.exit(1)

_CLI_FLAGS = {
    "--video", "--image", "--name", "-n", "--output", "-o", "--creator", "-c",
    "--start", "--end", "--fps", "--anim-frames", "--load-frames",
    "--bgm", "--bgm-name", "--loading-bg",
    "--compress", "--pillow-quality", "--ffmpeg-qv",
    "--tinypng-key", "--kraken-key", "--kraken-secret", "--kraken-quality",
    "--imagekit-key", "--imagekit-secret", "--imagekit-endpoint", "--imagekit-quality",
    "--cloudinary-name", "--cloudinary-key", "--cloudinary-secret", "--cloudinary-quality",
    "--interactive", "-i", "--quiet", "-q", "--skip-bootstrap",
    "--help", "-h",
    "--ext-version", "--pack-icon", "--bg-mode",
}

def _wants_cli(argv) -> bool:

    for tok in argv:
        if tok in _CLI_FLAGS or tok.startswith("--") or (tok.startswith("-") and len(tok) == 2):
            return True
    return False

def main():
    raw_args = sys.argv[1:]

    if _wants_cli(raw_args):

        parser = _build_arg_parser()
        args   = parser.parse_args(raw_args)

        if not args.video and not args.interactive:

            parser.print_help()
            sys.exit(0)

        _run_cli(args)

    else:

        app = QApplication(sys.argv)

        if not _check_license(app):
            sys.exit(0)

        w = MainWindow()
        w.setWindowOpacity(0.85)
        w.show()
        sys.exit(app.exec_())

if __name__ == "__main__":
    main()
