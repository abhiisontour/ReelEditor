"""Split-screen segments (series format): B-roll or graphics in the top half, the talking head head-to-waist in the
bottom half, static text hook + series pill on the seam during the opener, captions on the seam.

compass["split"] = {
  "layout":  {"scale": 0.72, "head_y": 1010, "seam": 960, "desk_fade_y": 1335},     # all optional
  "hook":    {"lines": ["You can send me", "negative", "comments if…"], "series": "Day 00/75 · Of making your travel easy"},
  "segments": [{"from": {"time": 0}, "to": {"time": 3.5}, "overlay": "hook",
                "top": {"media": "01_comments.mp4", "in": 1.1, "crop": [x, y, w, h]}},          # B-roll (input/media/)
               {"from": {"word": 42}, "to": {"word": 63}, "top": {"scenes": ["TOOLS", "SAVE"], "zoom": 1.15}}]}  # graphics
Back-to-back segments keep the subject in exactly the same place, so only the top half changes at the cut.
"""
import os, subprocess, cv2, numpy as np
from .common import W, H, FPS, at, log

DEF = {"scale": 0.72, "head_y": 1010, "seam": 960, "desk_fade_y": 1335}


def seg_frames(C, words):
    out = []
    for g in C.get("split", {}).get("segments", []):
        f = g["from"] if isinstance(g["from"], dict) else {"time": g["from"]}
        t = g["to"] if isinstance(g["to"], dict) else {"time": g["to"]}
        a, b = round(at(f, words, 0.0) * FPS), round(at(t, words, 0.0) * FPS)
        if b > a: out.append((a, b, g))
    return out


def windows(C, words):
    """(t0, t1) of each split segment, for captions / sound."""
    return [(a / FPS, b / FPS, g) for a, b, g in seg_frames(C, words)]


class Reader:
    """Sequential frame reader for a B-roll clip, normalised to 30 fps and cropped to fill 1080 x seam."""
    def __init__(self, path, t_in, crop, seam, speed=1.0):
        self.path, self.t_in, self.seam, self.speed = path, t_in, seam, speed; self.p = None; self.pos = -1; self.last = None
        vf = (f"setpts=PTS/{speed}," if abs(speed - 1) > 1e-3 else "") + "fps=30,"
        vf += (f"crop={crop[2]}:{crop[3]}:{crop[0]}:{crop[1]},scale=1080:{seam}:flags=lanczos" if crop else
               f"scale=1080:{seam}:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:{seam}")
        self.vf = vf

    def get(self, k):
        if self.p is None or k < self.pos or k > self.pos + 60:
            if self.p: self.p.kill()
            self.p = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{self.t_in + k * self.speed / FPS:.3f}", "-i", self.path, "-vf", self.vf,
                                       "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            self.pos = k - 1
        while self.pos < k:
            b = self.p.stdout.read(1080 * self.seam * 3)
            if len(b) < 1080 * self.seam * 3: break               # clip ran out: hold the last frame
            self.last = np.frombuffer(b, np.uint8).reshape(self.seam, 1080, 3); self.pos += 1
        self.pos = k
        return self.last if self.last is not None else np.zeros((self.seam, 1080, 3), np.uint8)


class Split:
    def __init__(self, pr, comp):
        C = pr.compass; self.pr, self.c = pr, comp; S = C.get("split", {}); L = {**DEF, **S.get("layout", {})}
        self.s, self.hy, self.seam = L["scale"], L["head_y"], L["seam"]
        self.cx = L.get("cx") or C["framing"].get("subject_cx_src") or 540
        self.segs = seg_frames(C, comp.words); self.readers = {}
        face = comp.face
        runs = []
        for a, b, g in self.segs:
            if runs and runs[-1][-1][1] == a: runs[-1].append((a, b, g))
            else: runs.append([(a, b, g)])
        for r in runs:
            top = float(np.median([f["y0"] for f in face[r[0][0]:r[-1][1]]])) - 40
            for a, b, g in r: g["_top"] = top
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        self.fade = np.clip((L["desk_fade_y"] - yy) / 70, 0, 1) * np.clip(np.minimum(xx, W - 1 - xx) / 70, 0, 1)
        sy = yy[:self.seam, :1]
        self.shade = np.maximum(np.clip((sy - (self.seam - 400)) / 200, 0, 1)[..., None] * 0.94, np.clip((340 - sy) / 140, 0, 1)[..., None] * 0.45)
        ov = cv2.imread(pr.p("layers", "split_hook", "00000.png"), cv2.IMREAD_UNCHANGED)
        self.hook = (ov[..., :3].astype(np.float32), ov[..., 3:].astype(np.float32) / 255) if ov is not None else None

    def active(self, n):
        return next(((a, b, g) for a, b, g in self.segs if a <= n < b), None)

    @staticmethod
    def _rgba(path):
        im = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if im is None: return None, None
        im = im.astype(np.float32); return im[..., :3], im[..., 3:] / 255

    def _top(self, n, a, g, L, bd):
        T = g["top"]
        if T.get("media"):
            key = (a, T["media"])
            if key not in self.readers:
                self.readers[key] = Reader(self.pr.p("input", "media", T["media"]), float(T.get("in", 0)), T.get("crop"), self.seam, float(T.get("speed", 1.0)))
            img = self.readers[key].get(n - a).astype(np.float32)
            img = self._marks(img, n, T)
            img = img * (1 - self.shade * T.get("shade", 1.0))
            c, al = self._rgba(f"{L['front']}/{n:05d}.png")      # notes/callouts that belong to this split window
            if c is not None: img = c[:self.seam] * al[:self.seam] + img * (1 - al[:self.seam])
            return img
        base = bd[:self.seam] * (1 - self.shade * 0.5)       # graphics: scene layers scaled into the middle of the top half
        k = float(T.get("zoom", 1.15)); fx, fy = T.get("from", [520, 430]); tx, ty = T.get("to", [540, 470])
        M = np.float32([[k, 0, tx - fx * k], [0, k, ty - fy * k]])
        for name in ("behind", "front"):
            c, al = self._rgba(f"{L[name]}/{n:05d}.png")
            if c is not None:
                c = cv2.warpAffine(c, M, (W, H), flags=cv2.INTER_CUBIC)[:self.seam]
                al = np.clip(cv2.warpAffine(al, M, (W, H), flags=cv2.INTER_CUBIC), 0, 1)[:self.seam, :, None]
                base = c * al + base * (1 - al)
        return base

    def _marks(self, img, n, T):
        """Highlight boxes on a B-roll / screen-recording top: rect in SOURCE pixels [x, y, w, h], fired on words."""
        hl = T.get("highlights") or []
        if not hl: return img
        cr = T.get("crop"); sx = 1080 / cr[2]; sy = self.seam / cr[3]
        t = n / FPS
        for h in hl:
            ta = at(h.get("at"), self.c.words, 0); tb = at(h.get("until"), self.c.words, 1e9)
            if not (ta <= t < tb): continue
            p = min(1, (t - ta) / 0.25); p = 1 - (1 - p) ** 3
            x, y, w, hh = h["rect"]; ax, ay = int((x - cr[0]) * sx), int((y - cr[1]) * sy); bx, by = int((x + w - cr[0]) * sx), int((y + hh - cr[1]) * sy)
            from .common import PALETTE
            col = tuple(int(v) for v in bytes.fromhex(PALETTE.get(h.get("color", "sun"), "#FBBF24")[1:])[::-1])
            ov = img.copy(); cv2.rectangle(ov, (ax, ay), (bx, by), col, -1, cv2.LINE_AA); img = img * (1 - 0.12 * p) + ov * 0.12 * p
            ov = img.copy(); cv2.rectangle(ov, (ax, ay), (bx, by), col, 7, cv2.LINE_AA); img = img * (1 - p) + ov * p
        return img

    def _caption(self, n, img, L):
        c, al = self._rgba(f"{L['caps']}/{n:05d}.png")
        if c is None: return img
        rows = np.where(al[..., 0].max(1) > 0.02)[0]
        if not len(rows): return img
        M = np.float32([[1, 0, 0], [0, 1, int(self.seam - 42 - (rows[0] + rows[-1]) / 2)]])
        c = cv2.warpAffine(c, M, (W, H)); al = cv2.warpAffine(al, M, (W, H))[..., None]
        return c * al + img * (1 - al)

    def frame(self, n, fg, a, seg, L, bd):
        s0, s1, g = seg; s = self.s
        a = a * self.fade
        M = np.float32([[s, 0, 540 - self.cx * s], [0, s, self.hy - g["_top"] * s]])
        F = cv2.warpAffine(fg, M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE).astype(np.float32)
        A = cv2.warpAffine(a, M, (W, H), flags=cv2.INTER_LINEAR, borderValue=0); A[:self.seam] = 0
        img = F * A[..., None] + bd * (1 - A[..., None])
        img[:self.seam] = self._top(n, s0, g, L, bd)
        if g.get("overlay") == "hook" and self.hook is not None:
            oc, oa = self.hook; img = oc * oa + img * (1 - oa)
        else:
            img = self._caption(n, img, L)
        return np.clip(img, 0, 255).astype(np.uint8)


def render_hook(pr, node_render, web):
    """Static hook + series pill overlay (one transparent PNG)."""
    if not pr.compass.get("split", {}).get("hook"): return
    node_render(os.path.join(web, "split_hook.html"), f"p={pr.root}", pr.p("layers", "split_hook"), 1)
