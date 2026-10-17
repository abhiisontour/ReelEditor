"""Pass 02: green-screen key -> reusable matte, edge/despill cleanup, prop removal, deflicker, skin smoothing, grade,
auto framing and face tracking. Everything is in source coordinates; framing is a separate transform."""
import json, os
import cv2, numpy as np
from .common import Project, reader, writer, smooth, W, H, log

DEFAULT_KEY = {"ratio_lo": 0.18, "ratio_hi": 0.62, "pinhole_area": 400, "hole_max_area": 6000, "speck_max_area": 4000, "edge_blur_sigma": 1.1}
DEFAULT_PIC = {"skin_amount": 0.55, "skin_sigma_color": 28, "skin_sigma_space": 9, "skin_grain_keep": 0.35, "contrast": 0.10, "clarity": 0.22,
               "sharpen": 0.45, "saturation": 1.04, "warmth_a": 0.6, "warmth_b": 1.2, "deflicker": True, "face_deflicker": True}


# ---------------- screen model + table ----------------
def fit_plate(pr: Project, table_y=None):
    fr = []
    for k, f in enumerate(reader(pr.p("work", "base.mov"))):
        if k % 45 == 0: fr.append(cv2.resize(f, (270, 480)).astype(np.float32))
    fr = np.array(fr); k = fr[..., 1] - np.maximum(fr[..., 0], fr[..., 2])
    yy, xx = np.mgrid[0:480, 0:270]; X, Y = xx / 270, yy / 480
    lim = (table_y or 1900) / 1920
    sel = (k > 25) & (Y[None] < lim)
    A = lambda X, Y: np.stack([np.ones_like(X), X, Y, X * X, X * Y, Y * Y, X ** 3, Y ** 3], -1)
    pts = np.where(sel); M = A(X[pts[1:]], Y[pts[1:]])
    c1, *_ = np.linalg.lstsq(M, k[sel], rcond=None)
    c2, *_ = np.linalg.lstsq(M, (k / np.maximum(fr[..., 1], 1))[sel], rcond=None)
    yy, xx = np.mgrid[0:H, 0:W]; G = A(xx / W, yy / H)
    np.save(pr.p("work", "plate_k.npy"), (G @ c1).astype(np.float32)); np.save(pr.p("work", "plate_kn.npy"), (G @ c2).astype(np.float32))


def detect_table(pr: Project):
    """Top edge of a desk spanning the frame: where greenness ends on both frame sides (None if no desk)."""
    f = next(reader(pr.p("work", "base.mov"))).astype(np.float32)
    k = f[..., 1] - np.maximum(f[..., 0], f[..., 2]); pts = []
    for xs in (range(5, 90), range(990, 1075)):
        col = k[900:1750, list(xs)].mean(1)
        if (col[:60] > 20).mean() < 0.5: return None
        pts.append([int(np.mean(list(xs))), int(np.argmax(col < 20)) + 900])
    if abs(pts[0][1] - pts[1][1]) > 120: return None
    return pts


# ---------------- keyer ----------------
class Keyer:
    def __init__(self, pr, key, table):
        self.P = {**DEFAULT_KEY, **key}; self.table = table
        self.plate = np.load(pr.p("work", "plate_k.npy")); self.pn = np.load(pr.p("work", "plate_kn.npy"))
        yy = np.arange(H)[:, None]
        if table:
            (x0, y0), (x1, y1) = table; ty = y0 + (np.arange(W) - x0) * (y1 - y0) / (x1 - x0)
            self.TY = ty; self.tmask = np.clip((yy - ty[None, :] + 1.5) / 3.0, 0, 1).astype(np.float32)
        else: self.TY = None; self.tmask = None

    def key(self, img):
        f = img.astype(np.float32); k = f[..., 1] - np.maximum(f[..., 0], f[..., 2])
        ratio = k / np.maximum(self.plate, 8)
        r2 = (k / np.maximum(f[..., 1], 1)) / np.maximum(self.pn, 0.05) * np.clip((k - 8) / 10, 0, 1)
        ratio = np.maximum(ratio, r2); P = self.P
        return 1 - np.clip((ratio - P["ratio_lo"]) / (P["ratio_hi"] - P["ratio_lo"]), 0, 1)

    def refine(self, a):
        P = self.P; raw = a.copy()
        if self.tmask is not None: a = np.maximum(a, self.tmask)
        inv = (a <= 0.5).astype(np.uint8)
        n, lab, st, _ = cv2.connectedComponentsWithStats(inv, 4)
        for i in range(1, n):
            x, y, ww, hh, area = st[i]
            if x == 0 or y == 0 or x + ww >= W or y + hh >= H or area >= P["hole_max_area"]: continue
            reg = lab[y:y + hh, x:x + ww] == i
            if area < P["pinhole_area"] or raw[y:y + hh, x:x + ww][reg].mean() > 0.25: a[y:y + hh, x:x + ww][reg] = 1.0
        core = (a > 0.5).astype(np.uint8)
        n, lab, st, _ = cv2.connectedComponentsWithStats(core, 8)
        if n > 1:
            keep = 1 + np.argmax(st[1:, 4])
            for i in range(1, n):
                if i != keep and st[i, 4] < P["speck_max_area"]: a[lab == i] = 0
        inner = cv2.erode((a > 0.5).astype(np.uint8), np.ones((13, 13), np.uint8))
        a = np.maximum(a, inner.astype(np.float32))
        a = np.clip((a - 0.12) / 0.88, 0, 1)
        return cv2.GaussianBlur(a, (0, 0), P["edge_blur_sigma"])

    @staticmethod
    def despill(img, a):
        f = img.astype(np.float32)
        core = cv2.erode((a > 0.97).astype(np.float32), np.ones((3, 3), np.uint8))
        num = cv2.GaussianBlur(f * core[..., None], (0, 0), 4); den = cv2.GaussianBlur(core, (0, 0), 4)[..., None]
        band = np.clip((0.97 - a) / 0.5, 0, 1)[..., None] * (den > 0.02)
        f = f * (1 - band) + num / np.maximum(den, 1e-4) * band            # edge decontamination (no rim)
        # inner edge: the lime screen bounces yellow-green onto skin edges. Pull the outer ~8 px of the subject toward the
        # colour found deeper inside (hue/chroma only, keep luminance so detail survives).
        solid = (a > 0.97).astype(np.uint8); deep = cv2.erode(solid, np.ones((17, 17), np.uint8)).astype(np.float32)
        n2 = cv2.GaussianBlur(f * deep[..., None], (0, 0), 7); d2 = cv2.GaussianBlur(deep, (0, 0), 7)[..., None]
        inside = n2 / np.maximum(d2, 1e-4)
        dist = cv2.distanceTransform(solid, cv2.DIST_L2, 3)
        wgt = (np.clip(1 - dist / 9, 0, 1) * (a > 0.3) * (d2[..., 0] > 0.01))[..., None] * 0.85
        lum = lambda x: (0.114 * x[..., 0] + 0.587 * x[..., 1] + 0.299 * x[..., 2])[..., None]
        f = f * (1 - wgt) + (inside - lum(inside) + lum(f)) * wgt
        b, g, r = f[..., 0], f[..., 1], f[..., 2]
        lim = np.maximum(r, b) * 0.5 + (r + b) * 0.25; g2 = np.minimum(g, lim)
        out = f.copy(); out[..., 1] = g2; out += ((g - g2) * 0.25)[..., None]
        return np.clip(out, 0, 255).astype(np.uint8)


def build_matte(pr: Project):
    C = pr.compass; key = C.get("key", {}); table = C["framing"].get("table_line") or None
    if not pr.has("work", "plate_k.npy"): fit_plate(pr, min(p[1] for p in table) if table else None)
    K = Keyer(pr, key, table)
    lum = lambda im: cv2.GaussianBlur(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY).astype(np.float32), (0, 0), 2)
    mo, fo = writer(pr.p("layers", "matte_raw.mkv"), "gray"), writer(pr.p("layers", "fg_raw.mkv"))
    buf = []; n = 0
    def emit(prev, cur, nxt):
        nonlocal n
        im, a = cur; acc, ws = a * 0.5, np.full_like(a, 0.5)
        for nb in (prev, nxt):
            if nb is None: continue
            w = 0.25 * np.clip(1 - np.abs(lum(im) - lum(nb[0])) / 10, 0, 1); acc += nb[1] * w; ws += w
        a = K.refine(acc / ws)
        mo.stdin.write((a * 255 + .5).astype(np.uint8).tobytes()); fo.stdin.write(K.despill(im, a).tobytes()); n += 1
        if n % 100 == 0: log("matte", n)
    for im in reader(pr.p("work", "base.mov")):
        buf.append((im, K.key(im)))
        if len(buf) == 2: emit(None, buf[0], buf[1])
        elif len(buf) == 3: emit(buf[0], buf[1], buf[2]); buf.pop(0)
    emit(buf[-2] if len(buf) > 1 else None, buf[-1], None)
    for p in (mo, fo): p.stdin.close(); p.wait()


# ---------------- face track (from matte, no extra model) ----------------
def face_track(pr: Project, matte="layers/matte_raw.mkv"):
    out = []
    for m in reader(pr.p(matte), "gray", 1):
        m = m[:1250] > 128; rows = m.sum(1); top = int(np.argmax(rows > 40))
        hw = rows[min(top + 120, 1249)]; sh = top + 120 + int(np.argmax(rows[top + 120:] > hw * 1.9))
        xs = np.where(m[min(top + 150, 1249)])[0]
        x0, x1 = (int(xs.min()), int(xs.max())) if len(xs) else (400, 680)
        out.append({"x0": x0, "y0": top, "x1": x1, "y1": int(sh)})
    pr.save("work/face_src.json", out); return out


def auto_framing(pr: Project, table, scale=1.42):
    """Centre the subject (torso/head centre from the matte) and cut the frame just below the hands on the desk."""
    face = pr.load("work/face_src.json"); cx = []
    for k, m in enumerate(reader(pr.p("layers", "matte_raw.mkv"), "gray", 1)):
        if k % 5: continue
        xs = np.where(m[1000] > 128)[0]
        if len(xs): cx.append(np.median(xs))
    cx = float(np.median(cx)) if cx else 540.0
    head_top = float(np.median([f["y0"] for f in face]))
    y_bottom = (np.mean([p[1] for p in table]) + 110) if table else head_top + 1300 / scale
    y0 = y_bottom - H / scale
    ht_out = (head_top - y0) * scale
    if ht_out < 560: y0 -= (560 - ht_out) / scale
    if ht_out > 700: y0 += (ht_out - 700) / scale
    return {"scale": scale, "x0": round(cx - (W / 2) / scale, 1), "y0": round(max(0.0, y0), 1), "subject_cx_src": round(cx, 1)}


# ---------------- enhancement + props ----------------
def _prop_fix(img, a, TY, zones):
    if TY is None and not zones: return a
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32); chroma = np.hypot(lab[..., 1] - 128, lab[..., 2] - 128)
    yy = np.arange(H)[:, None]; kill = np.zeros((H, W), bool)
    if TY is not None:   # light unsaturated blobs just above the desk that touch the background
        band = (yy > TY[None] - 90) & (yy < TY[None] + 3)
        white = (lab[..., 0] > 140) & (chroma < 14) & band & (a > 0.05)
        if white.any():
            n, lb, st, _ = cv2.connectedComponentsWithStats(white.astype(np.uint8), 8)
            bgnear = cv2.dilate((a < 0.3).astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
            for i in range(1, n):
                if st[i, 4] >= 6 and (bgnear & (lb == i)).any(): kill |= lb == i
    fi = img.astype(np.int16); greenish = (fi[..., 1] - np.maximum(fi[..., 0], fi[..., 2])) > 15
    for z in zones:   # explicit prop zones (compass.framing.prop_zones): near-white plastic + screen slivers
        zone = np.zeros((H, W), bool); y1 = z.get("y1") or (int(TY[(z["x0"] + z["x1"]) // 2]) + 14 if TY is not None else H)
        zone[z["y0"]:y1, z["x0"]:z["x1"]] = True
        strong = (lab[..., 0] > z.get("min_l", 165)) & (chroma < 13) & zone
        weak = (lab[..., 0] > 100) & (chroma < 12) & zone & (cv2.dilate(strong.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0)
        kill |= strong | weak | (greenish & zone)
    if not kill.any(): return a
    k = cv2.GaussianBlur(cv2.dilate(kill.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(np.float32), (0, 0), 1.2)
    return a * (1 - np.clip(k * 1.4, 0, 1))


def enhance(pr: Project):
    C = pr.compass; E = {**DEFAULT_PIC, **C.get("picture", {})}; fr = C["framing"]
    table = fr.get("table_line"); zones = fr.get("prop_zones", [])
    TY = None
    if table: (x0, y0), (x1, y1) = table; TY = y0 + (np.arange(W) - x0) * (y1 - y0) / (x1 - x0)
    face = pr.load("work/face_src.json")
    L = np.array([np.mean([cv2.cvtColor(p, cv2.COLOR_BGR2GRAY).mean() for p in (f[60:300, 30:200], f[60:300, 880:1050], f[700:900, 30:160])])
                  for f in reader(pr.p("work", "base.mov"))])
    gain = smooth(L, 15) / L if E["deflicker"] else np.ones(len(L))
    FL = []
    for n, f in enumerate(reader(pr.p("layers", "fg_raw.mkv"))):
        b = face[n]; cx = (b["x0"] + b["x1"]) // 2; fy = b["y0"] + int((b["y1"] - b["y0"]) * 0.42)
        FL.append(cv2.cvtColor(f[fy - 18:fy + 18, cx - 50:cx + 50], cv2.COLOR_BGR2GRAY).astype(np.float32).mean() * gain[n])
    FL = np.array(FL); fs = smooth(FL, 11)
    fgain = np.where(np.abs(FL - fs) > 6, 1.0, np.clip(fs / FL, 0.96, 1.04)) if E["face_deflicker"] else np.ones(len(FL))
    pr.save("work/deflicker.json", {"screen_jitter": float(np.std(L - smooth(L, 9))), "face_jitter_before": float(np.median(np.abs(FL - fs)))})
    wf, wm = writer(pr.p("layers", "fg.mkv")), writer(pr.p("layers", "matte.mkv"), "gray")
    src = reader(pr.p("work", "base.mov"))
    for n, (fg, m) in enumerate(zip(reader(pr.p("layers", "fg_raw.mkv")), reader(pr.p("layers", "matte_raw.mkv"), "gray", 1))):
        a = _prop_fix(next(src), m.astype(np.float32) / 255, TY, zones)
        wm.stdin.write((a * 255 + .5).astype(np.uint8).tobytes())
        b = face[n]; x0, y0, x1, y1 = b["x0"], b["y0"], b["x1"], b["y1"]
        f = fg.astype(np.float32) * gain[n]
        fm = np.zeros((H, W), np.float32); cv2.rectangle(fm, (x0 - 30, y0 - 30), (x1 + 30, y1 + 10), 1, -1); fm = cv2.GaussianBlur(fm, (0, 0), 30)
        f = np.clip(f * (1 + (fgain[n] - 1) * fm)[..., None], 0, 255).astype(np.uint8)
        ycc = cv2.cvtColor(f, cv2.COLOR_BGR2YCrCb)
        skin = ((ycc[..., 1] > 135) & (ycc[..., 1] < 178) & (ycc[..., 2] > 80) & (ycc[..., 2] < 128) & (ycc[..., 0] > 70)).astype(np.float32)
        skin = cv2.GaussianBlur(cv2.morphologyEx(skin, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)) * fm * (a > 0.9), (0, 0), 3)
        cx0, cy0, cx1, cy1 = max(0, x0 - 40), max(0, y0 - 40), min(W, x1 + 40), min(H, y1 + 20)
        crop = f[cy0:cy1, cx0:cx1].astype(np.float32)
        sm = cv2.bilateralFilter(f[cy0:cy1, cx0:cx1], 0, E["skin_sigma_color"], E["skin_sigma_space"]).astype(np.float32)
        detail = crop - cv2.GaussianBlur(crop, (0, 0), 0.8); mm = skin[cy0:cy1, cx0:cx1, None] * E["skin_amount"]
        out = f.astype(np.float32); out[cy0:cy1, cx0:cx1] = crop * (1 - mm) + (sm + detail * E["skin_grain_keep"]) * mm
        lab = cv2.cvtColor(np.clip(out, 0, 255).astype(np.uint8), cv2.COLOR_BGR2LAB).astype(np.float32)
        Lc = lab[..., 0] / 255; Ln = (Lc + E["contrast"] * (Lc - 0.5) * (1 - np.abs(2 * Lc - 1)) * 2) * 255
        core = cv2.GaussianBlur(cv2.erode((a > 0.95).astype(np.uint8), np.ones((15, 15), np.uint8)).astype(np.float32), (0, 0), 3)
        noskin = (1 - np.clip(skin * 1.5, 0, 1)) * core          # never sharpen skin or the silhouette edge (= no rim)
        Ln += E["clarity"] * (Ln - cv2.GaussianBlur(Ln, (0, 0), 22)) * noskin
        Ln += E["sharpen"] * (noskin + (core - noskin) * 0.35) * (Ln - cv2.GaussianBlur(Ln, (0, 0), 1.1))
        lab[..., 0] = Ln
        lab[..., 1] = 128 + (lab[..., 1] - 128) * E["saturation"] + E["warmth_a"]; lab[..., 2] = 128 + (lab[..., 2] - 128) * E["saturation"] + E["warmth_b"]
        wf.stdin.write(cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR).tobytes())
        if n % 100 == 0: log("enhance", n)
    for p in (wf, wm): p.stdin.close(); p.wait()


def prop_scan(pr: Project, table):
    """For the compass: where do light, unsaturated things keep showing through near the desk? (chairs, props)"""
    if not table: return []
    (x0, y0), (x1, y1) = table; TY = y0 + (np.arange(W) - x0) * (y1 - y0) / (x1 - x0)
    yy = np.arange(H)[:, None]; band = (yy > TY[None] - 90) & (yy < TY[None] + 3); acc = np.zeros((H, W), np.float32); cnt = 0
    for k, (f, m) in enumerate(zip(reader(pr.p("work", "base.mov")), reader(pr.p("layers", "matte_raw.mkv"), "gray", 1))):
        if k % 2: continue
        lab = cv2.cvtColor(f, cv2.COLOR_BGR2LAB).astype(np.float32); ch = np.hypot(lab[..., 1] - 128, lab[..., 2] - 128)
        acc += (lab[..., 0] > 165) & (ch < 13) & band & (m > 12); cnt += 1
    fr = acc / max(cnt, 1); n, lb, st, _ = cv2.connectedComponentsWithStats((fr > 0.05).astype(np.uint8), 8)
    return [{"x0": int(st[i, 0]) - 25, "x1": int(st[i, 0] + st[i, 2]) + 25, "y0": int(st[i, 1]) - 40, "area": int(st[i, 4]), "freq": round(float(fr[lb == i].max()), 2)}
            for i in range(1, n) if st[i, 4] > 15]
