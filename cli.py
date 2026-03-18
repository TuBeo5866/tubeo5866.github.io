import os
import sys
import re
import json
import shutil
import uuid
import subprocess
import tempfile
import zipfile
import stat
import urllib.request
import logging
import time
from pathlib import Path

                                                                               
                                                                
                                                                               
def _supports_colour():
    if sys.platform.startswith("win"):
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            return True
        except Exception:
            return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

_USE_COLOUR = _supports_colour()

C_RESET  = "\033[0m"    if _USE_COLOUR else ""
C_BOLD   = "\033[1m"    if _USE_COLOUR else ""
C_GREEN  = "\033[32m"   if _USE_COLOUR else ""
C_YELLOW = "\033[33m"   if _USE_COLOUR else ""
C_CYAN   = "\033[36m"   if _USE_COLOUR else ""
C_RED    = "\033[31m"   if _USE_COLOUR else ""
C_BLUE   = "\033[34m"   if _USE_COLOUR else ""
C_MAG    = "\033[35m"   if _USE_COLOUR else ""
C_DIM    = "\033[2m"    if _USE_COLOUR else ""

def _c(text, *codes):
    return "".join(codes) + str(text) + C_RESET if _USE_COLOUR else str(text)

                                                                               
         
                                                                               
_quiet_mode = False

def _log(msg, *, level="info"):
    if _quiet_mode and level == "info":
        return
    if level == "info":
                                       
        print(_c("  " + msg, C_CYAN, C_DIM))
    elif level == "ok":
        print(_c("✓  " + msg, C_GREEN, C_BOLD))
    elif level == "warn":
        print(_c("⚠  " + msg, C_YELLOW))
    elif level == "err":
        print(_c("✗  " + msg, C_RED, C_BOLD), file=sys.stderr)
    elif level == "step":
        print(f"\n{C_BOLD}{C_BLUE}──{C_RESET} {C_BOLD}{msg}{C_RESET}")
    else:
        print(msg)

                                                                               
                                                       
                                                                               

def _ffmpeg_in_path(name="ffmpeg"):
    try:
        subprocess.check_output([name, "-version"], stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False

def _ytdlp_in_path(name="yt-dlp"):
    try:
        subprocess.check_output([name, "--version"], stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False

def _add_to_path(directory):
    d = str(directory)
    if d not in os.environ.get("PATH", ""):
        os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")

def _get_ffmpeg_exe():
    if _ffmpeg_in_path("ffmpeg"):
        return "ffmpeg"
    appdata_ffmpeg = Path(os.environ.get("APPDATA", "")) / "ffmpeg" / "ffmpeg.exe"
    if appdata_ffmpeg.exists():
        return str(appdata_ffmpeg)
    return "ffmpeg"

def _pip_install(import_name, pkg_name):
    try:
        __import__(import_name)
    except ImportError:
        _log(f"Installing {pkg_name}...", level="info")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--quiet", pkg_name],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            _log(f"{pkg_name} installed", level="ok")
        except Exception as e:
            _log(f"Could not install {pkg_name}: {e}", level="warn")

def _bootstrap(skip=False):
    if skip:
        _log("Bootstrap skipped (--skip-bootstrap).", level="warn")
        return

    _log("Bootstrap: checking Python packages...", level="step")
    pkgs = [
        ("requests", "requests"),
        ("psutil",   "psutil"),
        ("PIL",      "Pillow"),
    ]
    for imp, pkg in pkgs:
        _pip_install(imp, pkg)

    _log("Bootstrap: checking system tools...", level="step")
    for tool in ("ffmpeg", "yt-dlp"):
        if _ffmpeg_in_path(tool) or _ytdlp_in_path(tool):
            _log(f"{tool} already available", level="ok")
        else:
            _log(f"{tool} not found – attempting install...", level="warn")
                                                                               
            _try_install_tool(tool)

    _log("Bootstrap done.", level="ok")

def _try_install_tool(name):
    is_win = sys.platform.startswith("win")
    is_mac = sys.platform.startswith("darwin")
    try:
                                
        if name == "yt-dlp":
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--quiet", "--upgrade", "yt-dlp"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            scripts = Path(sys.executable).parent / "Scripts"
            _add_to_path(str(scripts))
            if _ytdlp_in_path("yt-dlp"):
                _log("yt-dlp installed via pip", level="ok")
                return
        if name == "ffmpeg":
            if is_win:
                for mgr in (["winget","install","--id","Gyan.FFmpeg","-e","--silent",
                              "--accept-package-agreements","--accept-source-agreements"],
                             ["choco","install","ffmpeg","-y"],
                             ["scoop","install","ffmpeg"]):
                    try:
                        subprocess.run(mgr, timeout=300, capture_output=True)
                        if _ffmpeg_in_path("ffmpeg"):
                            _log("ffmpeg installed", level="ok"); return
                    except Exception:
                        pass
            elif is_mac:
                subprocess.run(["brew","install","ffmpeg"], timeout=600, capture_output=True)
                if _ffmpeg_in_path("ffmpeg"):
                    _log("ffmpeg installed via brew", level="ok"); return
            else:
                for pm in [["apt-get","install","-y","ffmpeg"],
                            ["dnf","install","-y","ffmpeg"],
                            ["pacman","-S","--noconfirm","ffmpeg"]]:
                    try:
                        subprocess.run(["sudo"]+pm, timeout=300, check=True,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        if _ffmpeg_in_path("ffmpeg"):
                            _log("ffmpeg installed", level="ok"); return
                    except Exception:
                        pass
    except Exception as e:
        pass
    _log(f"Could not install {name} automatically. Please install manually.", level="warn")

                                                                               
                                  
                                                                               

MAX_FRAMES       = 100
DEFAULT_FPS      = 20
ANIM_BG_DIR      = "hrzn_animated_background"
LOADING_BG_DIR   = "hrzn_loading_background"
CONTAINER_BG_DIR = "hrzn_container_background"
SOUNDS_DIR       = "sounds/music/bgm"
UI_DIR           = "ui"
FRAME_PREFIX     = "hans_common_"
CONTAINER_BG_URL = "https://tubeo5866.github.io/files/hrzn_container_background.zip"

class CLIWorker:
    def __init__(self, cfg, quiet=False):
        self.cfg    = cfg
        self.quiet  = quiet

                                                                               
    def log(self, msg):
        _log(msg, level="info")

    def progress(self, pct, label=""):
        if self.quiet:
            return
        bar_len = 30
        filled  = int(bar_len * pct / 100)
        bar     = _c("█" * filled, C_GREEN, C_BOLD) + _c("░" * (bar_len - filled), C_DIM)
        pct_col = _c(f"{pct:3d}%", C_YELLOW, C_BOLD)
        label_s = f"  {_c(label, C_CYAN, C_DIM)}" if label else ""
        print(f"\r  {_c('[', C_DIM)}{bar}{_c(']', C_DIM)} {pct_col}{label_s}   ", end="", flush=True)
        if pct >= 100:
            print()

                                                                               
    @staticmethod
    def _ensure(p):
        Path(p).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _parse_time(value):
        if value is None: return None
        if isinstance(value, (int, float)): return int(value)
        parts = str(value).split(":")
        try:
            parts = [int(p) for p in parts]
        except ValueError:
            raise ValueError(f"Invalid time: '{value}'  (expected seconds or mm:ss)")
        if len(parts) == 1: return parts[0]
        if len(parts) == 2: return parts[0]*60+parts[1]
        if len(parts) == 3: return parts[0]*3600+parts[1]*60+parts[2]
        raise ValueError(f"Invalid time: '{value}'")

    def _run(self, cmd, **kw):
        result = subprocess.run(cmd, capture_output=True, text=True, **kw)
        if result.returncode != 0:
            raise RuntimeError(
                f"Command failed: {' '.join(str(c) for c in cmd)}\n{result.stderr}"
            )
        return result

    def _run_ff(self, args):
        return self._run([_get_ffmpeg_exe()] + args)

                                                                               
    def _download_youtube(self, url, output_dir):
        self._ensure(output_dir)
        out_path = Path(output_dir) / "input_video.%(ext)s"
        start = self.cfg.get("start_seconds")
        end   = self.cfg.get("end_seconds")
        cmd   = [
            "yt-dlp", "-f",
            "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
            "--merge-output-format", "mp4", "-o", str(out_path), url
        ]
        if start is not None and end is not None and end > start:
            cmd += ["--download-sections", f"*{start}-{end}"]
            self.cfg["is_trimmed"] = True
        else:
            self.cfg["is_trimmed"] = False
        self.log("Downloading YouTube video…")
        self._run(cmd)
        mp4s = list(Path(output_dir).glob("input_video*.mp4"))
        if not mp4s:
            raise RuntimeError("YouTube download produced no mp4.")
        self.log(f"Downloaded → {mp4s[0].name}")
        return mp4s[0]

    def _download_container_bg(self, pack_root):
        dst = pack_root / CONTAINER_BG_DIR
        self._ensure(dst)
        self.log(f"Downloading container background…")
        try:
            import requests as _req
            r = _req.get(CONTAINER_BG_URL, timeout=60)
            r.raise_for_status()
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp.write(r.content)
                tmp_path = Path(tmp.name)
            with zipfile.ZipFile(tmp_path) as zf:
                zf.extractall(dst)
            tmp_path.unlink()
            self.log("Container background ready")
        except Exception as e:
            self.log(f"⚠ Container background download failed: {e}")

                                                                               
    def _extract_frames_anim(self, video, pack_root):
        dst = pack_root / ANIM_BG_DIR
        if dst.exists(): shutil.rmtree(dst)
        self._ensure(dst)
        n   = min(int(self.cfg.get("anim_frames", MAX_FRAMES)), MAX_FRAMES)
        pat = dst / f"{FRAME_PREFIX}%03d.png"
        self.log(f"Extracting {n} anim frames…")
        args = ["-y"]
        if not self.cfg.get("is_trimmed"):
            ss = self.cfg.get("start_seconds")
            en = self.cfg.get("end_seconds")
            if ss is not None: args += ["-ss", str(ss)]
            if en is not None and ss is not None: args += ["-t", str(en - ss)]
        fps = self.cfg.get("fps", DEFAULT_FPS)
        args += ["-i", str(video), "-vf", f"fps={fps}", "-frames:v", str(n), str(pat)]
        self._run_ff(args)
        return dst

    def _extract_frames_loading(self, video, pack_root):
        dst = pack_root / LOADING_BG_DIR
        if dst.exists(): shutil.rmtree(dst)
        self._ensure(dst)
        n   = min(int(self.cfg.get("load_frames", MAX_FRAMES)), MAX_FRAMES)
        pat = dst / "load_%03d.png"
        fps = self.cfg.get("fps", DEFAULT_FPS)
        self.log(f"Extracting {n} loading frames…")
        args = ["-y"]
        if not self.cfg.get("is_trimmed"):
            ss = self.cfg.get("start_seconds")
            en = self.cfg.get("end_seconds")
            if ss is not None: args += ["-ss", str(ss)]
            if en is not None and ss is not None: args += ["-t", str(en - ss)]
        args += ["-i", str(video), "-vf", f"fps={fps}", "-frames:v", str(n), str(pat)]
        self._run_ff(args)
        for f in sorted(dst.glob("load_*.png")):
            m = re.match(r"load_(\d+)\.png", f.name)
            if m:
                idx = int(m.group(1))
                f.rename(dst / f"{idx}.png")
        self.log("Loading frames ready")
        return dst

                                                                               
    def _make_blur(self, anim_dir):
        frames = sorted(anim_dir.glob(f"{FRAME_PREFIX}*.png"))
        if not frames:
            raise FileNotFoundError("No anim frames found to create blur.png")
        src      = frames[0]
        blur_out = anim_dir / "blur.png"
        try:
            import cv2
            img = cv2.imread(str(src))
            if img is not None:
                cv2.imwrite(str(blur_out), cv2.GaussianBlur(img, (31, 31), 0))
                self.log("blur.png created (OpenCV)")
                return
        except Exception:
            pass
        from PIL import Image, ImageFilter
        Image.open(src).filter(ImageFilter.GaussianBlur(radius=15)).save(blur_out)
        self.log("blur.png created (Pillow)")

                                                                                
    def _prep_audio(self, video, video_input, pack_root):
        bgm_file = self.cfg.get("bgm_file", "").strip()
        bgm_name = "bgm"
        if bgm_file:
            src = Path(bgm_file)
            if not src.exists():
                raise FileNotFoundError(f"BGM file not found: {src}")
            bgm_name = re.sub(r'[\\/:*?"<>|]', "_", src.stem).strip() or "bgm"
            self.cfg["bgm_name"] = bgm_name
            dst_dir = pack_root / SOUNDS_DIR
            self._ensure(dst_dir)
            dst = dst_dir / f"{bgm_name}.ogg"
            if src.suffix.lower() == ".ogg":
                shutil.copy2(src, dst)
            else:
                self._run_ff(["-y","-i",str(src),"-acodec","libvorbis","-q:a","6",str(dst)])
            self.log(f"BGM ready → {dst.name}")
        elif re.match(r"^https?://(www\.)?(youtube\.com|youtu\.be)/", str(video_input)):
            bgm_n   = self.cfg.get("bgm_name", "bgm")
            dst_dir = pack_root / SOUNDS_DIR
            self._ensure(dst_dir)
            tmpl    = dst_dir / f"{bgm_n}.%(ext)s"
            self._run(["yt-dlp", "-x", "--audio-format", "vorbis",
                        "-o", str(tmpl), str(video_input)])
            self.log("YouTube audio downloaded")
        else:
            bgm_n     = self.cfg.get("bgm_name", "bgm")
            bgm_name  = re.sub(r'[\\/:*?"<>|]', "_", bgm_n).strip() or "bgm"
            sounds_p  = pack_root / SOUNDS_DIR / f"{bgm_name}.ogg"
            self._ensure(sounds_p.parent)
            self._run_ff(["-y","-i",str(video),"-vn","-acodec","libvorbis",str(sounds_p)])
            self.log(f"Audio extracted → {sounds_p.name}")

                                                                              
    def _compress(self, frame_dir, method, cfg):
        method = (method or "lossless").lower()
        if method in ("lossless", "none"):
            self.log("Lossless – keeping original PNGs")
            return
        if method == "pillow":
            from PIL import Image
            qmap = {"low": 50, "medium": 70, "high": 85, "maximum": 95}
            q    = qmap.get(str(cfg.get("pillow_quality","high")).lower(), 85)
            for f in list(Path(frame_dir).glob("*.png")):
                im = Image.open(f)
                if im.mode in ("RGBA","LA"):
                    bg = Image.new("RGB", im.size, (255,255,255))
                    bg.paste(im, mask=im.split()[-1]); im = bg
                else:
                    im = im.convert("RGB")
                out = f.with_suffix(".jpg")
                im.save(out, quality=q); f.unlink()
            self.log(f"Pillow compression done (q={q})")
        elif method == "ffmpeg":
            qv = int(cfg.get("ffmpeg_qv") or 1)
            for p in sorted(Path(frame_dir).glob("*.png")):
                jpg = p.with_suffix(".jpg")
                self._run_ff(["-y","-i",str(p),"-q:v",str(qv),str(jpg)])
                p.unlink()
            self.log("FFmpeg compression done")
        elif method == "tinypng":
            import tinify
            if not cfg.get("tinify_key"):
                raise RuntimeError("--tinypng-key required for TinyPNG compression")
            tinify.key = cfg["tinify_key"]
            for f in Path(frame_dir).glob("*.png"):
                tinify.from_file(str(f)).to_file(str(f))
            self.log("TinyPNG compression done")
        elif method == "kraken":
            from krakenio import Client
            cl = Client(cfg.get("kraken_key"), cfg.get("kraken_secret"))
            import requests as _req
            for f in Path(frame_dir).glob("*.png"):
                res = cl.upload(str(f), {"wait":True,"lossy":True,
                                          "quality":cfg.get("kraken_quality",90)})
                if res.get("success"):
                    f.write_bytes(_req.get(res["kraked_url"]).content)
            self.log("Kraken compression done")
        elif method == "imagekit":
            from imagekitio import ImageKit
            from imagekitio.models.UploadFileRequestOptions import UploadFileRequestOptions
            import requests as _req
            ik = ImageKit(private_key=cfg.get("imagekit_secret"),
                          public_key=cfg.get("imagekit_key"),
                          url_endpoint=cfg.get("imagekit_urlendpoint"))
            for f in Path(frame_dir).glob("*.png"):
                opts = UploadFileRequestOptions(
                    file=f, file_name=f.name, folder="/",
                    transformation=[{"quality":cfg.get("imagekit_quality",90)},
                                    {"fetch_format":"jpg"}])
                res = ik.upload_file(opts)
                if res.url:
                    f.with_suffix(".jpg").write_bytes(_req.get(res.url).content)
                    f.unlink()
            self.log("ImageKit compression done")
        elif method == "cloudinary":
            import cloudinary, cloudinary.uploader, cloudinary.utils
            import requests as _req
            cloudinary.config(cloud_name=cfg.get("cloudinary_name"),
                               api_key=cfg.get("cloudinary_key"),
                               api_secret=cfg.get("cloudinary_secret"))
            q = cfg.get("cloudinary_quality","auto:best")
            for f in Path(frame_dir).glob("*.png"):
                res = cloudinary.uploader.upload(str(f), quality=q, fetch_format="jpg")
                url, _ = cloudinary.utils.cloudinary_url(
                    res["public_id"], fetch_format="jpg", quality=q)
                f.with_suffix(".jpg").write_bytes(_req.get(url).content)
                f.unlink()
            self.log("Cloudinary compression done")
        else:
            self.log(f"Unknown compression method '{method}' – falling back to lossless")

                                                                               
    def _gen_bg_anim_json(self, anim_dir, pack_root):
        frames = sorted(anim_dir.glob(f"{FRAME_PREFIX}*.png"))
        n = len(frames)
        if n == 0:
            self.log("⚠ No anim frames – skipping .hrzn_public_bg_anim.json"); return
        lines = [
            '  "namespace": "hrzn_ui_wextension",',
            '  "hrzn_ui_settings_bg@core_img": { "texture": "hrzn_animated_background/blur" },',
            '  "img": { "type": "image", "fill": true, "property_bag": {"#true": "0"}, "bindings": [ { "binding_name": "#collection_index", "binding_type": "collection_details", "binding_collection_name": "animated_background" }, { "binding_type": "view", "source_property_name": "(\'#\' + (#collection_index < 9))", "target_property_name": "#pad00" }, { "binding_type": "view", "source_property_name": "(\'#\' + (#collection_index < 99))", "target_property_name": "#pad0" }, { "binding_type": "view", "source_property_name": "(\'hrzn_animated_background/hans\' + \'_common_\' + #pad00 + #pad0 + (#collection_index + 1))", "target_property_name": "#texture" } ] },',
            f'  "hrzn_ui_main_bg": {{ "size": [ "100%", "100%" ], "type": "stack_panel", "anchor_from": "top_left", "anchor_to": "top_left", "offset": "@hrzn_ui_wextension.01", "$duration_per_frame|default": 0.03333333, "$frames|default": {n}, "collection_name": "animated_background", "factory": {{"name": "test", "control_name": "hrzn_ui_wextension.img"}}, "property_bag": {{"#frames": "$frames"}}, "bindings": [ {{ "binding_type": "view", "source_property_name": "(#frames*1)", "target_property_name": "#collection_length" }} ] }},',
            '  "hans_anim_base": { "destroy_at_end": "@hrzn_ui_wextension.bg_anim", "anim_type": "offset", "easing": "linear", "duration": "$duration_per_frame", "from": "$anm_offset", "to": "$anm_offset" },',
            ''
        ]
        for i in range(1, n + 1):
            key      = f"{i:02d}"
            y_pct    = "0%" if i == 1 else f"-{(i-1)*100}%"
            next_key = f"{(i % n) + 1:02d}"
            line     = f'  "{key}@hrzn_ui_wextension.hans_anim_base":{{"$anm_offset": [ "0px", "{y_pct}" ],"next": "@hrzn_ui_wextension.{next_key}"}},'
            lines.append(line)
        lines[-1] = lines[-1].rstrip(",")
        (pack_root / ".hrzn_public_bg_anim.json").write_text(
            "{\n" + "\n".join(lines) + "\n}", encoding="utf-8")
        self.log(f".hrzn_public_bg_anim.json written ({n} frames)")

    def _gen_bg_load_json(self, load_dir, pack_root):
        IMG_EXT = {".png",".jpg",".jpeg",".webp",".bmp"}
        frames  = sorted([f for f in load_dir.iterdir() if f.suffix.lower() in IMG_EXT],
                          key=lambda p: int(p.stem) if p.stem.isdigit() else 0)
        n = len(frames)
        if n == 0:
            self.log("⚠ No loading frames – skipping .hrzn_public_bg_load.json"); return
        ctrl_lines = [
            f'      {{ "{i}@hrzn_ui_load_wextension.img": {{ "$img": "{i}" }} }}{"," if i < n else ""}'
            for i in range(1, n+1)
        ]
        anim_lines = [
            f'  "{i:02d}@hrzn_ui_load_wextension.anim_base":{{"$anm_offset": [ 0, "{"0%" if i==1 else f"-{(i-1)*100}%"}" ],"next": "@hrzn_ui_load_wextension.{(i%n)+1:02d}"}}{"," if i < n else ""}'
            for i in range(1, n+1)
        ]
        content = ('{\n  "namespace": "hrzn_ui_load_wextension",\n\n'
                   '  "anim_base": {\n    "anim_type": "offset",\n    "easing": "linear",\n'
                   '    "duration": "$duration_loading_per_frame",\n'
                   '    "from": "$anm_offset",\n    "to": "$anm_offset"\n  },\n\n'
                   '  "img": {\n    "type": "image",\n    "fill": true,\n    "bilinear": true,\n'
                   '    "size": [ "100%", "100%" ],\n'
                   '    "texture": "(\'hrzn_loading_background/\' + $img )"\n  },\n\n'
                   '  "hans_load_background": {\n    "type": "stack_panel",\n'
                   '    "size": [ "100%", "100%" ],\n    "anchor_from": "top_left",\n'
                   '    "anchor_to": "top_left",\n    "offset": "@hrzn_ui_load_wextension.01",\n'
                   '    "$duration_per_frame|default": 1.5,\n    "controls": [\n'
                   + "\n".join(ctrl_lines) +
                   '\n    ]\n  },\n  /*///// FRAMES /////*/\n'
                   + "\n".join(anim_lines) + '\n}')
        (pack_root / ".hrzn_public_bg_load.json").write_text(content, encoding="utf-8")
        self.log(f".hrzn_public_bg_load.json written ({n} frames)")

    def _gen_manifest(self, pack_root):
        creator  = self.cfg.get("creator", "Unknown")
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
        (pack_root / "manifest.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")
        self.log("manifest.json written")

    def _gen_global_variables(self, pack_root):
        creator = self.cfg.get("creator", "Unknown")
        content = f'''{{
  /* -------------------------- EXTENSION -------------------------- */
  "$hrzn.ui.use_extension": true,
  "$hrzn.ui.creator_name": "{creator}",
  "$hrzn.ui.extension_version": "201.1.0",
  "$duration_per_frame": 0.05,
  "$duration_loading_per_frame": 2,
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
}}'''
        ui_dir = pack_root / UI_DIR
        ui_dir.mkdir(parents=True, exist_ok=True)
        (ui_dir / "_global_variables.json").write_text(content, encoding="utf-8")
        self.log("ui/_global_variables.json written")

    def _gen_music_definitions(self, pack_root):
        out = pack_root / "sounds" / "music_definitions.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(
            {"menu": {"event_name":"music.menu","max_delay":30,"min_delay":0}},
            ensure_ascii=False, indent=3), encoding="utf-8")
        self.log("sounds/music_definitions.json written")

    def _gen_sound_definitions(self, pack_root):
        bgm_name = re.sub(r'[\\/:*?"<>|]', "_",
                          self.cfg.get("bgm_name","bgm").strip()) or "bgm"
        out = pack_root / "sounds" / "sound_definitions.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        content = {
            "format_version": "1.20.20",
            "sound_definitions": {
                "music.menu": {
                    "__use_legacy_max_distance": "true",
                    "category": "music",
                    "max_distance": None, "min_distance": None,
                    "sounds": [{"name": f"sounds/music/bgm/{bgm_name}",
                                 "stream": True, "volume": 0.30}]
                }
            }
        }
        out.write_text(json.dumps(content, ensure_ascii=False, indent=3), encoding="utf-8")
        self.log("sounds/sound_definitions.json written")

                                                                                
    def _copy_loading_bg_folder(self, pack_root):
        src_folder = self.cfg.get("loading_bg_folder","").strip()
        if not src_folder:
            return False
        src = Path(src_folder)
        if not src.is_dir():
            self.log(f"⚠ Loading BG folder not found: {src}"); return False
        IMG_EXT = {".png",".jpg",".jpeg",".webp",".bmp"}
        images  = sorted([f for f in src.iterdir() if f.suffix.lower() in IMG_EXT])
        if not images:
            self.log(f"⚠ No images in {src}"); return False
        dst = pack_root / LOADING_BG_DIR
        if dst.exists(): shutil.rmtree(dst)
        dst.mkdir(parents=True, exist_ok=True)
        try:
            ordered = sorted(images, key=lambda f: int(f.stem))
        except ValueError:
            ordered = images                                                    
        for idx, img in enumerate(ordered, start=1):
            shutil.copy2(img, dst / f"{idx}{img.suffix.lower()}")
        self.log(f"Loading BG: {len(ordered)} images copied from folder")
        return True

                                                                               
    def process(self):
        total = 14
        step  = [0]

        def tick(label=""):
            step[0] += 1
            pct = int(step[0] / total * 100)
            self.progress(pct, label)

        output_folder = Path(self.cfg["output_folder"]).resolve()
        output_folder.mkdir(parents=True, exist_ok=True)
        ext_name  = self.cfg["new_pack_name"].strip()
        pack_root = output_folder / ext_name
        if pack_root.exists(): shutil.rmtree(pack_root)
        pack_root.mkdir(parents=True, exist_ok=True)
        tick("Pack folder created")

        for d in [ANIM_BG_DIR, LOADING_BG_DIR, CONTAINER_BG_DIR, SOUNDS_DIR, UI_DIR]:
            (pack_root / d).mkdir(parents=True, exist_ok=True)
        tick("Folder structure created")

        video_input = self.cfg["video_path"]
        tmp_yt = None
        if re.match(r"^https?://(www\.)?(youtube\.com|youtu\.be)/", str(video_input)):
            self.cfg["is_trimmed"] = False
            tmp_yt = output_folder / "_tmp_yt"
            video  = self._download_youtube(video_input, tmp_yt)
        else:
            video = Path(video_input).resolve()
            if not video.exists():
                raise FileNotFoundError(f"Video not found: {video}")
            self.cfg["is_trimmed"] = False
        tick("Video ready")

        anim_dir = self._extract_frames_anim(video, pack_root)
        tick("Anim frames extracted")

        if self._copy_loading_bg_folder(pack_root):
            load_dir = pack_root / LOADING_BG_DIR
            tick("Loading BG images copied from folder")
        else:
            load_dir = self._extract_frames_loading(video, pack_root)
            tick("Loading frames extracted")

        self._make_blur(anim_dir)
        tick("blur.png created")

        method = self.cfg.get("compress_method", "lossless")
        _log(f"Compressing anim frames ({method})…", level="info")
        self._compress(anim_dir, method, self.cfg)
        tick("Anim frames compressed")

        _log(f"Compressing loading frames ({method})…", level="info")
        self._compress(load_dir, method, self.cfg)
        tick("Loading frames compressed")

        self._download_container_bg(pack_root)
        tick("Container background downloaded")

        self._prep_audio(video, video_input, pack_root)
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
        _log(f"Packing → {zip_base}", level="step")
        shutil.make_archive(str(zip_base.with_suffix("")), "zip", pack_root)
        zip_tmp = zip_base.with_suffix(".zip")
        if zip_tmp.exists(): zip_tmp.rename(zip_base)
        tick("mcpack created")

        shutil.rmtree(pack_root, ignore_errors=True)
        if tmp_yt and tmp_yt.exists():
            shutil.rmtree(tmp_yt, ignore_errors=True)
        tick("Cleanup done")

        _log(f"\n✅  Done!  Output: {zip_base}", level="ok")
        return zip_base

                                                                               
                  
                                                                               

def _ask(prompt, default=None, required=False):
    suffix = f" [{default}]" if default else ""
    while True:
        try:
            val = input(_c(f"  {prompt}{suffix}: ", C_CYAN)).strip()
        except EOFError:
            raise
        if not val and default is not None:
            return default
        if val:
            return val
        if not required:
            return ""
        _log("This field is required.", level="warn")

def _choose(prompt, choices, default=None):
    print(_c(f"\n  {prompt}", C_BOLD))
    for i, c in enumerate(choices, 1):
        marker = " ◀" if c == default else ""
        print(f"    {_c(str(i), C_YELLOW)}) {c}{_c(marker, C_DIM)}")
    while True:
        raw = input(_c(f"  Choice [1-{len(choices)}]: ", C_CYAN)).strip()
        if not raw and default:
            return default
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(choices):
                return choices[idx]
        except ValueError:
            pass
        _log("Invalid choice.", level="warn")

def _interactive():
    _print_banner()
    print(_c("\n  Interactive mode  –  press Enter to accept [defaults]\n", C_DIM))

    def _sec(title, colour=C_YELLOW):
        print(f"\n  {colour}{C_BOLD}── {title} {'─'*(40-len(title))}{C_RESET}")

    cfg = {}

    _sec("SOURCE", C_CYAN)
    cfg["video_path"]    = _ask("Video file or YouTube URL", required=True)
    cfg["start_seconds"] = CLIWorker._parse_time(_ask("Start time (s or mm:ss)", "0"))
    cfg["end_seconds"]   = CLIWorker._parse_time(_ask("End time   (s or mm:ss)", "30"))
    cfg["fps"]           = int(_ask("Extract FPS", str(DEFAULT_FPS)))
    cfg["anim_frames"]   = int(_ask("Animated background frames (max 100)", str(MAX_FRAMES)))
    cfg["load_frames"]   = int(_ask("Loading background frames  (max 100)", str(MAX_FRAMES)))

    _sec("OUTPUT", C_GREEN)
    cfg["new_pack_name"]  = _ask("Extension name", "MyExtension")
    cfg["creator"]        = _ask("Creator name",   "Unknown")
    cfg["output_folder"]  = _ask("Output directory", str(Path.home() / "HorizonExtensions"))

    _sec("ASSETS", C_MAG)
    cfg["bgm_name"]          = _ask("BGM track name (used in sound_definitions)", "bgm")
    cfg["bgm_file"]          = _ask("Custom BGM file (.ogg/.mp3/…) – blank = extract from video", "")
    cfg["loading_bg_folder"] = _ask("Loading BG folder – blank = use video frames", "")

    _sec("COMPRESSION", C_YELLOW)

    compress_methods = ["lossless","pillow","ffmpeg","tinypng","kraken","imagekit","cloudinary","compressor"]
    cfg["compress_method"] = _choose("Compression method", compress_methods, "lossless")
    if cfg["compress_method"] == "pillow":
        cfg["pillow_quality"] = _choose("Pillow quality", ["low","medium","high","maximum"], "high")
    if cfg["compress_method"] == "ffmpeg":
        cfg["ffmpeg_qv"] = int(_ask("FFmpeg -q:v value (1=best, 31=worst)", "1"))
    if cfg["compress_method"] == "tinypng":
        cfg["tinify_key"] = _ask("TinyPNG API key", required=True)
    if cfg["compress_method"] == "kraken":
        cfg["kraken_key"]    = _ask("Kraken API key",    required=True)
        cfg["kraken_secret"] = _ask("Kraken API secret", required=True)
        cfg["kraken_quality"]= int(_ask("Kraken quality", "90"))
    if cfg["compress_method"] == "imagekit":
        cfg["imagekit_key"]         = _ask("ImageKit public key", required=True)
        cfg["imagekit_secret"]      = _ask("ImageKit private key", required=True)
        cfg["imagekit_urlendpoint"] = _ask("ImageKit URL endpoint", required=True)
        cfg["imagekit_quality"]     = int(_ask("ImageKit quality", "90"))
    if cfg["compress_method"] == "cloudinary":
        cfg["cloudinary_name"]    = _ask("Cloudinary cloud name", required=True)
        cfg["cloudinary_key"]     = _ask("Cloudinary API key",    required=True)
        cfg["cloudinary_secret"]  = _ask("Cloudinary API secret", required=True)
        cfg["cloudinary_quality"] = _ask("Cloudinary quality", "auto:best")

    print()
    return cfg

                                                                               
               
                                                                               

def _print_banner():
    M  = C_MAG  + C_BOLD  if _USE_COLOUR else ""
    C  = C_CYAN + C_BOLD  if _USE_COLOUR else ""
    Y  = C_YELLOW         if _USE_COLOUR else ""
    G  = C_GREEN          if _USE_COLOUR else ""
    R  = C_RESET          if _USE_COLOUR else ""
    D  = C_DIM            if _USE_COLOUR else ""
    print(f"""
{M}  ╔══════════════════════════════════════════════════════════╗{R}
{M}  ║  {C}Horizon UI Extension Studio  {D}–{R}{C}  CLI{R}{M}                   ║{R}
{M}  ║  {Y}Tao mcpack cho Minecraft: Bedrock Edition{R}{M}           ║{R}
{M}  ║  {G}Original Creator : Han's404  |  @zxyn404 ( Han's ){R}{M}  ║{R}
{M}  ╚══════════════════════════════════════════════════════════╝{R}""")

def _print_help():
                      
    S  = C_YELLOW + C_BOLD  if _USE_COLOUR else ""                   
    F  = C_CYAN             if _USE_COLOUR else ""                
    V  = C_GREEN            if _USE_COLOUR else ""                    
    D  = C_DIM              if _USE_COLOUR else ""                         
    W  = C_BOLD             if _USE_COLOUR else ""               
    R  = C_RESET            if _USE_COLOUR else ""
    Y  = C_YELLOW           if _USE_COLOUR else ""
    G  = C_GREEN            if _USE_COLOUR else ""
    M  = C_MAG              if _USE_COLOUR else ""

    def sec(name):
        print(f"\n{S}{name}:{R}")

    def row(flag, meta, desc, default=None):
        def_s = f"  {D}(default: {default}){R}" if default else ""
        print(f"  {F}{flag}{R}  {V}{meta}{R}  {D}{desc}{R}{def_s}")

    def flag(flags, desc):
        print(f"  {F}{flags}{R}  {D}{desc}{R}")

    def ex(comment, cmd):
        print(f"  {D}# {comment}{R}")
                                                
        coloured_cmd = re.sub(r'(--[\w-]+|-[a-z])', f'{F}\\1{R}', cmd)
        coloured_cmd = re.sub(r'"([^"]+)"', f'{V}"\\1"{R}', coloured_cmd)
        print(f"  {W}python horizon_cli.py{R} {coloured_cmd}")
        print()

                                                                             
    print(f"\n{W}usage:{R}")
    usage_flags = (
        f"  {W}horizon_cli.py{R} "
        f"{F}[--video{R} {V}PATH_OR_URL{R}{F}]{R} "
        f"{F}[--start{R} {V}TIME{R}{F}]{R} "
        f"{F}[--end{R} {V}TIME{R}{F}]{R}\n"
        f"               "
        f"{F}[--fps{R} {V}N{R}{F}]{R} "
        f"{F}[--anim-frames{R} {V}N{R}{F}]{R} "
        f"{F}[--load-frames{R} {V}N{R}{F}]{R}\n"
        f"               "
        f"{F}[--output{R} {V}DIR{R}{F}]{R} "
        f"{F}[--name{R} {V}NAME{R}{F}]{R} "
        f"{F}[--creator{R} {V}NAME{R}{F}]{R}\n"
        f"               "
        f"{F}[--bgm{R} {V}FILE{R}{F}]{R} "
        f"{F}[--bgm-name{R} {V}NAME{R}{F}]{R} "
        f"{F}[--loading-bg{R} {V}DIR{R}{F}]{R}\n"
        f"               "
        f"{F}[--compress{R} {V}METHOD{R}{F}]{R} "
        f"{F}[--pillow-quality{R} {V}LEVEL{R}{F}]{R} "
        f"{F}[--ffmpeg-qv{R} {V}N{R}{F}]{R}\n"
        f"               "
        f"{F}[--tinypng-key{R} {V}KEY{R}{F}]{R}\n"
        f"               "
        f"{F}[--kraken-key{R} {V}KEY{R}{F}]{R} "
        f"{F}[--kraken-secret{R} {V}SECRET{R}{F}]{R} "
        f"{F}[--kraken-quality{R} {V}N{R}{F}]{R}\n"
        f"               "
        f"{F}[--imagekit-key{R} {V}KEY{R}{F}]{R} "
        f"{F}[--imagekit-secret{R} {V}SECRET{R}{F}]{R}\n"
        f"               "
        f"{F}[--imagekit-endpoint{R} {V}URL{R}{F}]{R} "
        f"{F}[--imagekit-quality{R} {V}N{R}{F}]{R}\n"
        f"               "
        f"{F}[--cloudinary-name{R} {V}NAME{R}{F}]{R} "
        f"{F}[--cloudinary-key{R} {V}KEY{R}{F}]{R}\n"
        f"               "
        f"{F}[--cloudinary-secret{R} {V}SECRET{R}{F}]{R} "
        f"{F}[--cloudinary-quality{R} {V}LEVEL{R}{F}]{R}\n"
        f"               "
        f"{F}[--interactive]{R} "
        f"{F}[--quiet]{R} "
        f"{F}[--skip-bootstrap]{R}"
    )
    print(usage_flags)

                                                                             
    sec("options")
    flag("-h, --help",         "show this help message and exit")
    flag("--interactive, -i",  "Force interactive prompt mode")
    flag("--quiet, -q",        "Suppress detailed log output")
    flag("--skip-bootstrap",   "Skip automatic tool/package installation check")

                                                                             
    sec("source")
    row("--video",       "PATH_OR_URL", "Local video file or YouTube URL")
    row("--start",       "TIME",        "Start time in seconds or mm:ss", "0")
    row("--end",         "TIME",        "End time in seconds or mm:ss",   "30")
    row("--fps",         "N",           "Frame extraction FPS",           "20")
    row("--anim-frames", "N",           "Number of animated background frames, max 100", "100")
    row("--load-frames", "N",           "Number of loading background frames, max 100",  "100")

                                                                             
    sec("output")
    row("--output, -o",  "DIR",  "Output directory",                    "~/HorizonExtensions")
    row("--name, -n",    "NAME", "Extension / pack name",               "MyExtension")
    row("--creator, -c", "NAME", "Creator name embedded in manifest",   "Unknown")

                                                                             
    sec("assets")
    row("--bgm",         "FILE", "Background music file (.ogg/.mp3/.wav/…).\n"
                                 "                    Omit to extract from video.")
    row("--loading-bg",  "DIR",  "Folder with images for loading screen.\n"
                                 "                    Omit to extract from video.")
    row("--bgm-name",    "NAME", "BGM track name used in sound_definitions.json", "bgm")

                                                                             
    sec("compression")
    methods = ["lossless", "pillow", "ffmpeg", "tinypng",
               "kraken",  "imagekit", "cloudinary", "compressor"]
    methods_str = " | ".join(
        f"{M}{m}{R}" if i % 4 == 3 or i == len(methods)-1
        else f"{G}{m}{R}"
        for i, m in enumerate(methods)
    )
    print(f"  {F}--compress{R}  {V}METHOD{R}  {D}Compression method:{R}")
    print(f"              {G}lossless{R} | {G}pillow{R} | {G}ffmpeg{R} | {G}tinypng{R} |")
    print(f"              {G}kraken{R}   | {G}imagekit{R} | {G}cloudinary{R} | {G}compressor{R}")
    print(f"              {D}(default: lossless){R}")
    print(f"  {F}--pillow-quality{R}  {V}{{low,medium,high,maximum}}{R}")
    print(f"  {F}--ffmpeg-qv{R}  {V}N{R}  {D}FFmpeg -q:v value 1-31{R}  {D}(default: 1 = best){R}")
    print(f"  {F}--tinypng-key{R}       {V}KEY{R}")
    print(f"  {F}--kraken-key{R}        {V}KEY{R}")
    print(f"  {F}--kraken-secret{R}     {V}SECRET{R}")
    print(f"  {F}--kraken-quality{R}    {V}N{R}")
    print(f"  {F}--imagekit-key{R}      {V}KEY{R}")
    print(f"  {F}--imagekit-secret{R}   {V}SECRET{R}")
    print(f"  {F}--imagekit-endpoint{R} {V}URL{R}")
    print(f"  {F}--imagekit-quality{R}  {V}N{R}")
    print(f"  {F}--cloudinary-name{R}   {V}NAME{R}")
    print(f"  {F}--cloudinary-key{R}    {V}KEY{R}")
    print(f"  {F}--cloudinary-secret{R} {V}SECRET{R}")
    print(f"  {F}--cloudinary-quality{R} {V}{{auto,auto:best,auto:good,auto:eco,auto:low}}{R}")

                                                                             
    sec("examples")
    ex("Interactive mode (recommended for first-time use)",
       "")
    ex("Non-interactive with a local video",
       '--video myvideo.mp4 --name MyPack --creator Han')
    ex("YouTube URL with time range",
       '--video "https://youtu.be/xxxx" --start 10 --end 40 --name BeachPack')
    ex("With custom BGM and compression",
       '--video clip.mp4 --name CoolPack --compress pillow --pillow-quality high')
    ex("With a loading-background folder",
       '--video clip.mp4 --name CoolPack --loading-bg ./my_screens/')

                                                                               
                                                  
                                                                               

def _parse_args(argv):
    args = argv[1:]
    result = {}

    def _next(i):
        if i + 1 >= len(args):
            _log(f"Expected value after {args[i]}", level="err"); sys.exit(1)
        return args[i + 1], i + 2

    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-h", "--help"):
            _print_banner(); _print_help(); sys.exit(0)
        elif a in ("--interactive", "-i"):
            result["interactive"] = True; i += 1
        elif a in ("--quiet", "-q"):
            result["quiet"] = True; i += 1
        elif a == "--skip-bootstrap":
            result["skip_bootstrap"] = True; i += 1
        elif a == "--video":
            v, i = _next(i); result["video_path"] = v
        elif a in ("--start",):
            v, i = _next(i); result["start"] = v
        elif a in ("--end",):
            v, i = _next(i); result["end"] = v
        elif a == "--fps":
            v, i = _next(i); result["fps"] = int(v)
        elif a == "--anim-frames":
            v, i = _next(i); result["anim_frames"] = int(v)
        elif a == "--load-frames":
            v, i = _next(i); result["load_frames"] = int(v)
        elif a in ("--output", "-o"):
            v, i = _next(i); result["output_folder"] = v
        elif a in ("--name", "-n"):
            v, i = _next(i); result["new_pack_name"] = v
        elif a in ("--creator", "-c"):
            v, i = _next(i); result["creator"] = v
        elif a == "--bgm":
            v, i = _next(i); result["bgm_file"] = v
        elif a == "--bgm-name":
            v, i = _next(i); result["bgm_name"] = v
        elif a == "--loading-bg":
            v, i = _next(i); result["loading_bg_folder"] = v
        elif a == "--compress":
            v, i = _next(i); result["compress_method"] = v
        elif a == "--pillow-quality":
            v, i = _next(i); result["pillow_quality"] = v
        elif a == "--ffmpeg-qv":
            v, i = _next(i); result["ffmpeg_qv"] = int(v)
        elif a == "--tinypng-key":
            v, i = _next(i); result["tinify_key"] = v
        elif a == "--kraken-key":
            v, i = _next(i); result["kraken_key"] = v
        elif a == "--kraken-secret":
            v, i = _next(i); result["kraken_secret"] = v
        elif a == "--kraken-quality":
            v, i = _next(i); result["kraken_quality"] = int(v)
        elif a == "--imagekit-key":
            v, i = _next(i); result["imagekit_key"] = v
        elif a == "--imagekit-secret":
            v, i = _next(i); result["imagekit_secret"] = v
        elif a == "--imagekit-endpoint":
            v, i = _next(i); result["imagekit_urlendpoint"] = v
        elif a == "--imagekit-quality":
            v, i = _next(i); result["imagekit_quality"] = int(v)
        elif a == "--cloudinary-name":
            v, i = _next(i); result["cloudinary_name"] = v
        elif a == "--cloudinary-key":
            v, i = _next(i); result["cloudinary_key"] = v
        elif a == "--cloudinary-secret":
            v, i = _next(i); result["cloudinary_secret"] = v
        elif a == "--cloudinary-quality":
            v, i = _next(i); result["cloudinary_quality"] = v
        else:
            _log(f"Unknown argument: {a}  (use --help for usage)", level="err")
            sys.exit(1)

    return result

                                                                               
             
                                                                               

def main():
    global _quiet_mode

    parsed = _parse_args(sys.argv)

    _quiet_mode = parsed.get("quiet", False)
    skip_boot   = parsed.get("skip_bootstrap", False)

                                                                                        
    is_tty      = hasattr(sys.stdin, "isatty") and sys.stdin.isatty()
    interactive = parsed.get("interactive", False) or (len(sys.argv) == 1 and is_tty)

    _print_banner()
    _bootstrap(skip=skip_boot)

    if interactive:
        try:
            cfg = _interactive()
        except EOFError:
            _log("stdin is not a terminal – use --video and other flags. See --help.", level="err")
            sys.exit(1)
    elif not is_tty and len(sys.argv) == 1:
                                                       
        _print_help(); sys.exit(0)
    else:
        if "video_path" not in parsed:
            _log("--video is required in non-interactive mode. Use --help for usage.", level="err")
            sys.exit(1)

                                                         
        cfg = {
            "video_path":        parsed["video_path"],
            "start_seconds":     CLIWorker._parse_time(parsed.get("start", 0)),
            "end_seconds":       CLIWorker._parse_time(parsed.get("end", 30)),
            "fps":               parsed.get("fps", DEFAULT_FPS),
            "anim_frames":       parsed.get("anim_frames", MAX_FRAMES),
            "load_frames":       parsed.get("load_frames", MAX_FRAMES),
            "new_pack_name":     parsed.get("new_pack_name", "MyExtension"),
            "creator":           parsed.get("creator", "Unknown"),
            "bgm_name":          parsed.get("bgm_name", "bgm"),
            "bgm_file":          parsed.get("bgm_file", ""),
            "loading_bg_folder": parsed.get("loading_bg_folder", ""),
            "output_folder":     parsed.get("output_folder",
                                            str(Path.home() / "HorizonExtensions")),
            "compress_method":   parsed.get("compress_method", "lossless"),
            "pillow_quality":    parsed.get("pillow_quality", "high"),
            "ffmpeg_qv":         parsed.get("ffmpeg_qv", 1),
            "tinify_key":        parsed.get("tinify_key", ""),
            "kraken_key":        parsed.get("kraken_key", ""),
            "kraken_secret":     parsed.get("kraken_secret", ""),
            "kraken_quality":    parsed.get("kraken_quality", 90),
            "imagekit_key":      parsed.get("imagekit_key", ""),
            "imagekit_secret":   parsed.get("imagekit_secret", ""),
            "imagekit_urlendpoint": parsed.get("imagekit_urlendpoint", ""),
            "imagekit_quality":  parsed.get("imagekit_quality", 90),
            "cloudinary_name":   parsed.get("cloudinary_name", ""),
            "cloudinary_key":    parsed.get("cloudinary_key", ""),
            "cloudinary_secret": parsed.get("cloudinary_secret", ""),
            "cloudinary_quality":parsed.get("cloudinary_quality", "auto:best"),
        }

    worker = CLIWorker(cfg, quiet=_quiet_mode)
    try:
        worker.process()
    except KeyboardInterrupt:
        _log("\nCancelled by user.", level="warn")
        sys.exit(1)
    except Exception as e:
        import traceback
        _log(f"\n{e}", level="err")
        if not _quiet_mode:
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
