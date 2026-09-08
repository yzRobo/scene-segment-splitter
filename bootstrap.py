"""
bootstrap.py - Automatically provision the helper binaries.

Scene Segment Splitter needs ffmpeg, ffprobe and mkvmerge. Rather than making
the user download them by hand, ensure_binaries() fetches whatever is missing
into the local ./bin folder on first run.

  * Windows: downloads ffmpeg/ffprobe (gyan.dev release build) and mkvmerge
    (MKVToolNix portable), extracting with the standard library plus a tiny
    standalone 7-Zip extractor (7zr.exe) for the .7z archive. Fully automatic.
  * macOS/Linux: prints the one-line package-manager command, since static
    builds vary by distro (ffmpeg/mkvtoolnix are one 'brew'/'apt' away).

Binaries already present in ./bin or on the system PATH are left alone.
"""

import os
import re
import gzip
import shutil
import zipfile
import platform
import tempfile
import subprocess
import urllib.request
from pathlib import Path

APP_DIR = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.join(APP_DIR, "bin")
BINARIES = ("ffmpeg", "ffprobe", "mkvmerge")

FFMPEG_ZIP_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
SEVENZR_URL = "https://www.7-zip.org/a/7zr.exe"
MKV_VERSION_XML = "https://mkvtoolnix.download/latest-release.xml.gz"
MKV_KNOWN_GOOD = "88.0"  # fallback if the latest version cannot be resolved
_UA = {"User-Agent": "Mozilla/5.0 (scene-segment-splitter bootstrap)"}


def _exe(name: str) -> str:
    return name + (".exe" if platform.system().lower() == "windows" else "")


def find_binary(name: str, bin_dir: str = BIN_DIR):
    """Return the path to a helper binary (bundled bin/ first, then PATH)."""
    local = os.path.join(bin_dir, _exe(name))
    if os.path.exists(local):
        return local
    return shutil.which(name)


def missing_binaries(bin_dir: str = BIN_DIR):
    return [b for b in BINARIES if not find_binary(b, bin_dir)]


def _download(url: str, dest: str, progress=print) -> bool:
    """Download url -> dest. Uses urllib, falling back to PowerShell on Windows
    (which uses the OS certificate store) if urllib fails."""
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as out:
            total = int(resp.headers.get("Content-Length", 0))
            read = 0
            last = -1
            while True:
                chunk = resp.read(262144)
                if not chunk:
                    break
                out.write(chunk)
                read += len(chunk)
                if total:
                    pct = read * 100 // total
                    if pct >= last + 10:
                        last = pct
                        progress(f"    {pct}% ({read // 1048576} / {total // 1048576} MB)")
        return os.path.getsize(dest) > 0
    except Exception as e:
        if platform.system().lower() == "windows":
            progress(f"    (retrying download via PowerShell: {e})")
            try:
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     f"[Net.ServicePointManager]::SecurityProtocol='Tls12';"
                     f"Invoke-WebRequest -Uri '{url}' -OutFile '{dest}'"],
                    check=True, capture_output=True, text=True)
                return os.path.exists(dest) and os.path.getsize(dest) > 0
            except Exception as e2:
                progress(f"    Download failed: {e2}")
                return False
        progress(f"    Download failed: {e}")
        return False


def _install_ffmpeg(bin_dir: str, progress) -> bool:
    progress("Downloading FFmpeg (ffmpeg + ffprobe)...")
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, "ffmpeg.zip")
        if not _download(FFMPEG_ZIP_URL, zip_path, progress):
            return False
        progress("  Extracting FFmpeg...")
        try:
            with zipfile.ZipFile(zip_path) as zf:
                wanted = {"ffmpeg.exe", "ffprobe.exe"}
                got = set()
                for member in zf.namelist():
                    base = os.path.basename(member)
                    if base in wanted and member.endswith("/bin/" + base):
                        with zf.open(member) as src, \
                                open(os.path.join(bin_dir, base), "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        got.add(base)
                return wanted.issubset(got)
        except Exception as e:
            progress(f"  Failed to extract FFmpeg: {e}")
            return False


def _resolve_mkv_urls(progress):
    """Yield candidate MKVToolNix portable .7z URLs, newest first."""
    versions = []
    try:
        req = urllib.request.Request(MKV_VERSION_XML, headers=_UA)
        with urllib.request.urlopen(req, timeout=30) as resp:
            xml = gzip.decompress(resp.read()).decode("utf-8", "replace")
        m = re.search(r"<version>([\d.]+)</version>", xml)
        if m:
            versions.append(m.group(1))
    except Exception:
        pass
    if MKV_KNOWN_GOOD not in versions:
        versions.append(MKV_KNOWN_GOOD)
    for v in versions:
        yield v, f"https://mkvtoolnix.download/windows/releases/{v}/mkvtoolnix-64-bit-{v}.7z"


def _install_mkvmerge(bin_dir: str, progress) -> bool:
    progress("Downloading MKVToolNix (mkvmerge)...")
    with tempfile.TemporaryDirectory() as tmp:
        # A tiny standalone 7-Zip extractor for the .7z archive (no install).
        sevenzr = os.path.join(tmp, "7zr.exe")
        if not _download(SEVENZR_URL, sevenzr, progress):
            progress("  Could not fetch the 7-Zip extractor.")
            return False
        archive = os.path.join(tmp, "mkvtoolnix.7z")
        downloaded = False
        for version, url in _resolve_mkv_urls(progress):
            progress(f"  Trying MKVToolNix {version}...")
            if _download(url, archive, progress):
                downloaded = True
                break
        if not downloaded:
            progress("  Could not download MKVToolNix.")
            return False
        progress("  Extracting mkvmerge...")
        out = os.path.join(tmp, "extracted")
        os.makedirs(out, exist_ok=True)
        try:
            # 'e' extracts (flattened) only the named file, recursively.
            subprocess.run([sevenzr, "e", archive, f"-o{out}", "-r", "mkvmerge.exe", "-y"],
                           check=True, capture_output=True, text=True)
        except Exception as e:
            progress(f"  Failed to extract mkvmerge: {e}")
            return False
        src = os.path.join(out, "mkvmerge.exe")
        if not os.path.exists(src):
            found = list(Path(out).rglob("mkvmerge.exe"))
            if not found:
                progress("  mkvmerge.exe not found in the archive.")
                return False
            src = str(found[0])
        shutil.move(src, os.path.join(bin_dir, "mkvmerge.exe"))
        return True


def ensure_binaries(bin_dir: str = BIN_DIR, progress=print) -> bool:
    """Ensure ffmpeg, ffprobe and mkvmerge are available, downloading any that
    are missing (Windows). Returns True if all are present afterward."""
    missing = missing_binaries(bin_dir)
    if not missing:
        return True

    os.makedirs(bin_dir, exist_ok=True)
    system = platform.system().lower()
    progress(f"Setting up required tools ({', '.join(missing)})...")

    if system != "windows":
        progress("Automatic download is only provided on Windows. Install the")
        progress("tools with your package manager, for example:")
        progress("  macOS:  brew install ffmpeg mkvtoolnix")
        progress("  Debian: sudo apt-get install ffmpeg mkvtoolnix")
        return not missing_binaries(bin_dir)

    ok = True
    if "ffmpeg" in missing or "ffprobe" in missing:
        if _install_ffmpeg(bin_dir, progress):
            progress("  FFmpeg ready.")
        else:
            progress("  FFmpeg setup failed. See "
                     "https://www.gyan.dev/ffmpeg/builds/ to install manually.")
            ok = False
    if "mkvmerge" in missing:
        if _install_mkvmerge(bin_dir, progress):
            progress("  mkvmerge ready.")
        else:
            progress("  MKVToolNix setup failed. See "
                     "https://mkvtoolnix.download/ to install manually.")
            ok = False

    still = missing_binaries(bin_dir)
    if still:
        progress(f"Still missing: {', '.join(still)}. Place them in the 'bin' "
                 f"folder or on your PATH.")
        return False
    progress("All required tools are ready.")
    return ok


if __name__ == "__main__":
    ensure_binaries()
