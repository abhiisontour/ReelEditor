"""Stage scenes: full-screen moments where the talking head shrinks into a picture-in-picture circle.
 - screen   : a screen recording (video) or screenshots (images) of a website/app in a device frame, with zooms,
              highlight boxes and tap ripples fired on words. Media lives in <project>/input/media/.
 - bars / steps / compare / title_card : animated explainers drawn by web/motion.html (layer=stage).
Geometry is computed here and shared with the HTML layer through work/stage.json."""
import os, cv2, numpy as np
from .common import Project, at, W, H, FPS, PALETTE

STAGE_TYPES = {"screen", "bars", "steps", "compare", "title_card"}
PIP = {"cx": 195, "cy": 380, "r": 135}          # top-left, inside the safe area
EASE = lambda x: 1 - (1 - min(max(x, 0), 1)) ** 3


def media_info(path):
    if path.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        im = cv2.imread(path); return {"kind": "image", "w": im.shape[1], "h": im.shape[0], "dur": None}
    c = cv2.VideoCapture(path); w, h = int(c.get(3)), int(c.get(4)); fps = c.get(5) or 30; n = c.get(7)
    return {"kind": "video", "w": w, "h": h, "dur": n / fps if fps else None, "fps": fps}


def geometry(aspect, device):
    """Content rect for the media inside its device frame (output px). Landscape -> browser window, portrait -> phone."""
    if device == "auto": device = "browser" if aspect >= 1 else "phone"
    if device == "browser":
        w = 880; h = int(w / aspect); bar = 64; y = int(590 + (560 - h - bar) / 2) + bar
        return {"device": "browser", "x": 60, "y": y, "w": w, "h": h, "bar": bar}
    h = 940; w = int(h * aspect)
    if w > 600: w = 600; h = int(w / aspect)
    return {"device": "phone", "x": int(500 - w / 2), "y": 560, "w": w, "h": h, "bar": 0}


def prepare(pr: Project):
    C = pr.compass; ws = pr.load("words.json")["words"]; out = {"pip": PIP, "scenes": {}}
    for s in C.get("scenes", []):
        if s["type"] != "screen": continue
        files = s.get("slides") and [x["file"] for x in s["slides"]] or [s["media"]]
        info = media_info(pr.p("input", "media", files[0]))
        g = geometry(info["w"] / info["h"], s.get("device", "auto")); g["media"] = info
        out["scenes"][s["id"]] = g
    pr.save("work/stage.json", out); return out


class Stage:
    """Python side of a stage frame: backdrop + media (zoom/pan) + HTML stage layer + highlights/taps + PIP subject."""
    def __init__(self, pr: Project, words):
        self.pr = pr; self.C = pr.compass; self.ws = words; self.geo = pr.load("work/stage.json", {"scenes": {}, "pip": PIP})
        self.scenes = []
        for s in self.C.get("scenes", []):
            if s["type"] not in STAGE_TYPES: continue
            t0 = at(s.get("in"), words, 0.0); t1 = at(s.get("out"), words, 1e9) if s.get("out") else 1e9
            self.scenes.append((t0, t1, s))
        self.caps = {}

    def mode(self, t):
        """0 = normal talking head, 1 = fully on stage. 0.35 s transitions in and out."""
        best = 0.0
        for t0, t1, s in self.scenes:
            if t0 - 0.0 <= t < t1 + 0.35:
                best = max(best, EASE((t - t0) / 0.35) * (1 - EASE((t - t1) / 0.35)))
        return best

    def active(self, t):
        for t0, t1, s in self.scenes:
            if t0 <= t < t1 + 0.35: return t0, t1, s
        return None

    def _media_frame(self, s, t0, t):
        P = self.pr
        if s.get("slides"):
            cur = s["slides"][0]
            for sl in s["slides"]:
                if at(sl.get("at"), self.ws, t0) <= t: cur = sl
            key = ("img", cur["file"])
            if key not in self.caps: self.caps[key] = cv2.imread(P.p("input", "media", cur["file"]))
            return self.caps[key]
        f = s["media"]; path = P.p("input", "media", f)
        if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            if f not in self.caps: self.caps[f] = cv2.imread(path)
            return self.caps[f]
        mt = s.get("media_in", 0.0) + max(0.0, t - t0) * s.get("speed", 1.0)
        c = self.caps.get(f)
        if c is None or c["t"] > mt:
            cap = cv2.VideoCapture(path); cap.set(cv2.CAP_PROP_POS_MSEC, mt * 1000); c = self.caps[f] = {"cap": cap, "t": mt, "img": cap.read()[1]}
        while c["t"] + 1 / FPS <= mt:
            ok, im = c["cap"].read()
            if not ok: break
            c["img"] = im; c["t"] += 1 / (c["cap"].get(5) or 30)
        return c["img"]

    def _zoom_rect(self, s, t):
        r = [0, 0, 1, 1]; prev = r
        for z in s.get("zooms", []):
            tz = at(z.get("at"), self.ws, 0); d = z.get("dur", 0.45)
            if t < tz: break
            p = EASE((t - tz) / d); tgt = z.get("rect", [0, 0, 1, 1])
            r = [prev[i] + (tgt[i] - prev[i]) * p for i in range(4)]; prev = tgt if p >= 1 else r
        return r

    def render(self, n, bd, stage_png):
        t = n / FPS; act = self.active(t)
        img = bd.copy()
        if act:
            t0, t1, s = act
            if s["type"] == "screen":
                g = self.geo["scenes"].get(s["id"]); m = self._media_frame(s, t0, t)
                if g is not None and m is not None:
                    mh, mw = m.shape[:2]; zx, zy, zw, zh = self._zoom_rect(s, t)
                    asp = g["w"] / g["h"]; cw = zw * mw; ch = cw / asp
                    if ch > zh * mh: ch = zh * mh; cw = ch * asp
                    cx, cy = (zx + zw / 2) * mw, (zy + zh / 2) * mh
                    x0 = int(np.clip(cx - cw / 2, 0, mw - cw)); y0 = int(np.clip(cy - ch / 2, 0, mh - ch))
                    crop = m[y0:y0 + int(ch), x0:x0 + int(cw)]
                    img[g["y"]:g["y"] + g["h"], g["x"]:g["x"] + g["w"]] = cv2.resize(crop, (g["w"], g["h"]), interpolation=cv2.INTER_AREA).astype(np.float32)
                    self._marks(img, s, t, g, (x0, y0, cw, ch, mw, mh))
        if stage_png is not None:
            c, a = stage_png; img = c * a + img * (1 - a)
        if act and act[2]["type"] == "screen": self._overlay_marks(img)
        return img

    def _marks(self, img, s, t, g, z):
        x0, y0, cw, ch, mw, mh = z; sx, sy = g["w"] / cw, g["h"] / ch
        to = lambda u, v: (g["x"] + (u * mw - x0) * sx, g["y"] + (v * mh - y0) * sy)
        self._pending = []
        for h in s.get("highlights", []):
            ta = at(h.get("at"), self.ws, 0); tb = at(h.get("until"), self.ws, ta + 1.5)
            if not (ta <= t < tb): continue
            p = EASE((t - ta) / 0.25) * (1 - EASE((t - tb + 0.15) / 0.15))
            (ax, ay), (bx, by) = to(h["rect"][0], h["rect"][1]), to(h["rect"][0] + h["rect"][2], h["rect"][1] + h["rect"][3])
            m = 14   # keep the box inside the device frame (it may be partly off-screen while zoomed)
            ax, bx = np.clip([ax, bx], g["x"] + m, g["x"] + g["w"] - m); ay, by = np.clip([ay, by], g["y"] + m, g["y"] + g["h"] - m)
            if bx - ax > 12 and by - ay > 12: self._pending.append(("box", ax, ay, bx, by, p, h.get("color", "sun")))
        for tp in s.get("taps", []):
            ta = at(tp.get("at"), self.ws, 0)
            if ta <= t < ta + 0.6: px, py = to(tp["x"], tp["y"]); self._pending.append(("tap", px, py, (t - ta) / 0.6, tp.get("color", "rose")))

    def _overlay_marks(self, img):
        for m in getattr(self, "_pending", []):
            if m[0] == "box":
                _, ax, ay, bx, by, p, col = m; c = tuple(int(v) for v in bytes.fromhex(PALETTE.get(col, col)[1:])[::-1])
                ax, ay, bx, by = int(ax), int(ay), int(bx), int(by)
                ov = img.copy(); cv2.rectangle(ov, (ax, ay), (bx, by), c, -1, cv2.LINE_AA); img[:] = img * (1 - 0.10 * p) + ov * 0.10 * p
                ov = img.copy(); cv2.rectangle(ov, (ax, ay), (bx, by), c, 6, cv2.LINE_AA); img[:] = img * (1 - p) + ov * p
            else:
                _, px, py, q, col = m; c = tuple(int(v) for v in bytes.fromhex(PALETTE.get(col, col)[1:])[::-1])
                ov = img.copy(); cv2.circle(ov, (int(px), int(py)), int(18 + 60 * EASE(q)), c, 5, cv2.LINE_AA); cv2.circle(ov, (int(px), int(py)), 16, c, -1, cv2.LINE_AA)
                img[:] = img * (1 - (1 - q)) + ov * (1 - q)
        self._pending = []

    def pip(self, stage_img, plate, e, face_c):
        """Shrink the talking-head plate into a circle (e: 0 full -> 1 PIP)."""
        if e <= 0: return plate
        P = self.geo.get("pip", PIP); fx, fy = face_c
        s = 1 + (0.46 - 1) * e; cx = fx + (P["cx"] - fx) * e; cy = fy + (P["cy"] - fy) * e
        R = 1500 + (P["r"] - 1500) * e
        M = np.float32([[s, 0, cx - s * fx], [0, s, cy - s * fy]])
        sub = cv2.warpAffine(plate, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        mask = np.zeros((H, W), np.float32); cv2.circle(mask, (int(cx), int(cy)), int(R), 1.0, -1, cv2.LINE_AA)
        mask = cv2.GaussianBlur(mask, (0, 0), 1.0)[..., None]
        out = sub * mask + stage_img * (1 - mask)
        if e > 0.6:
            ring = np.zeros((H, W), np.float32); cv2.circle(ring, (int(cx), int(cy)), int(R), 1.0, 5, cv2.LINE_AA)
            col = np.array(list(bytes.fromhex(PALETTE["coral"][1:]))[::-1], np.float32)
            a = ring[..., None] * (e - 0.6) / 0.4; out = out * (1 - a) + col * a
        return out
