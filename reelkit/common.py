"""Shared helpers: project layout, IO, video pipes, palette."""
import json, os, subprocess, sys, shutil
import numpy as np

W, H, FPS, SR = 1080, 1920, 30, 48000
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(REPO, "web")
MODELS = os.environ.get("REELKIT_MODELS", os.path.expanduser("~/.cache/reelkit/models"))
PALETTE = {"sun": "#FBBF24", "peach": "#FF8A5B", "coral": "#FF5D73", "rose": "#F472B6",
           "lilac": "#A78BFA", "sky": "#60A5FA", "mint": "#34D399"}
INK, MUTE, BG = "#F5F5F4", "#A3A3AB", "#09090A"


class Project:
    """All paths for one reel. Everything lives under <root>/ so passes never step on each other."""
    def __init__(self, root):
        self.root = os.path.abspath(root)
        for d in ("input", "work", "layers", "renders", "qc"):
            os.makedirs(self.p(d), exist_ok=True)

    def p(self, *a): return os.path.join(self.root, *a)
    def has(self, *a): return os.path.exists(self.p(*a))

    def load(self, name, default=None):
        f = self.p(name)
        if not os.path.exists(f): return default
        with open(f) as fh: return json.load(fh)

    def save(self, name, obj):
        with open(self.p(name), "w") as fh: json.dump(obj, fh, indent=1, ensure_ascii=False)

    @property
    def compass(self): return self.load("compass.json")


def sh(cmd, **kw):
    r = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, **kw)
    if r.returncode: sys.stderr.write(r.stderr[-3000:]); raise RuntimeError(f"command failed: {cmd if isinstance(cmd, str) else ' '.join(cmd)}")
    return r.stdout


def reader(path, pix="bgr24", ch=3, w=W, h=H):
    p = subprocess.Popen(["ffmpeg", "-v", "quiet", "-i", path, "-f", "rawvideo", "-pix_fmt", pix, "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    n = w * h * ch
    while True:
        b = p.stdout.read(n)
        if len(b) < n: return
        yield np.frombuffer(b, np.uint8).reshape((h, w, ch) if ch > 1 else (h, w))


def writer(path, pix="bgr24", codec="ffv1", w=W, h=H, extra=()):
    args = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", pix, "-s", f"{w}x{h}", "-r", str(FPS), "-i", "-"]
    args += (["-c:v", "ffv1", "-level", "3"] if codec == "ffv1" else list(extra)) + [path]
    return subprocess.Popen(args, stdin=subprocess.PIPE)


def node_render(page_abs, query, outdir, frames, pages=2):
    """Render an HTML page frame by frame to transparent PNGs (see web/render.mjs)."""
    if os.path.isdir(outdir) and not isinstance(frames, str): shutil.rmtree(outdir)
    url = page_abs + ("?" + query if query else "")
    r = subprocess.run(["node", os.path.join(WEB, "render.mjs"), url, outdir, str(frames), str(pages)], capture_output=True, text=True)
    if r.returncode or "PAGE ERROR" in r.stderr: sys.stderr.write(r.stderr[-3000:]); raise RuntimeError("render failed: " + page_abs)


def smooth(x, k):
    return np.convolve(np.pad(x, (k // 2, k // 2), mode="edge"), np.ones(k) / k, "valid")


def at(spec, words, default=None):
    """Resolve a timing spec: {"time": s} | {"word": index} | number(index) | None."""
    if spec is None: return default
    if isinstance(spec, (int, float)) and not isinstance(spec, bool): return words[int(spec)]["start"]
    if "time" in spec: return float(spec["time"])
    if "word" in spec: return words[int(spec["word"])]["start"] + float(spec.get("offset", 0))
    return default


def log(*a): print("[reelkit]", *a, flush=True)
