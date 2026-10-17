"""Compositor. Split-screen segments (split.py) take over whole frames; otherwise the stack is: backdrop -> BEHIND layer -> cut-out (light-wrapped onto whatever is behind it) -> camera push-in
-> FRONT layer -> captions. Writes layers/picture.mp4 (video only) or stills."""
import os, subprocess, cv2, numpy as np
from .common import Project, reader, writer, at, W, H, FPS, log


def backdrop(glow=0.16):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d1 = np.sqrt(((xx - 540) / (0.60 * W)) ** 2 + ((yy - 0.40 * H) / (0.34 * H)) ** 2)
    d2 = np.sqrt(((xx - 540) / (0.90 * W)) ** 2 + ((yy - H) / (0.50 * H)) ** 2)
    w1 = np.clip(1 - d1, 0, 1) ** 1.4; w2 = np.clip(1 - d2, 0, 1) ** 1.6
    bg = np.zeros((H, W, 3), np.float32) + np.array([10, 9, 9], np.float32)
    bg += w1[..., None] * glow * (np.array([203, 220, 255], np.float32) - 10)        # warm peach (BGR)
    bg += w2[..., None] * 0.05 * (np.array([255, 185, 201], np.float32) - 10)        # faint lilac floor
    return bg


class Comp:
    def __init__(self, pr: Project):
        self.pr = pr; C = pr.compass; self.C = C; fr = C["framing"]
        self.words = pr.load("words.json")["words"]; self.bd = backdrop(C.get("look", {}).get("glow", 0.16))
        s = fr["scale"]; self.M = np.float32([[s, 0, -fr["x0"] * s], [0, s, -fr["y0"] * s]])
        face = pr.load("work/face_src.json"); cy = np.median([(f["y0"] + f["y1"]) / 2 for f in face])
        self.anchor = C.get("camera_anchor") or [540, float((cy - fr["y0"]) * s)]
        self.keys = [(at(k.get("at"), self.words, 0.0), float(k["to"]), float(k.get("dur", 0.3))) for k in C.get("camera", [])]
        self.bloom = C.get("look", {}).get("opening_bloom", 0.6)
        self.layers = {"behind": pr.p("layers", "behind"), "front": pr.p("layers", "front"), "caps": pr.p("layers", "captions"), "stage": pr.p("layers", "stage")}
        from .stage import Stage
        self.stage = Stage(pr, self.words) if any(x["type"] in ("screen", "bars", "steps", "compare", "title_card") for x in C.get("scenes", [])) else None
        self.face = face
        from .split import Split
        self.split = Split(pr, self) if C.get("split", {}).get("segments") else None

    def cam(self, t):
        s = 1.0
        for t0, to, d in sorted(self.keys):
            if t < t0: break
            p = 1.0 if d == 0 else min(1, (t - t0) / d); p = 1 - (1 - p) ** 3
            s = s + (to - s) * p if p < 1 else to
        return s

    @staticmethod
    def rgba(path):
        im = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if im is None: return None, None
        im = im.astype(np.float32); return im[..., :3], im[..., 3:] / 255

    def frame(self, n, fg, a, layers=None, cam=None, subject_dy=0):
        L = layers or self.layers; t = n / FPS
        if self.split is not None and subject_dy == 0:
            seg = self.split.active(n)
            if seg: return self.split.frame(n, fg, a, seg, L, self.bd)
        bg = self.bd.copy()
        op = self.C.get("look", {}).get("opening")
        if op == "sunrise" and t < 1.6:   # visual hook: warm light rises behind the subject, then settles to the normal glow
            p = 1 - (1 - min(t / 1.1, 1)) ** 3; fade = 1 - max(0.0, (t - 1.1) / 0.5)
            yy = np.arange(H, dtype=np.float32)[:, None]; xx = np.arange(W, dtype=np.float32)[None, :]
            cy = H * (1.05 - 0.62 * p); d = np.sqrt(((xx - 540) / (0.75 * W)) ** 2 + ((yy - cy) / (0.42 * H)) ** 2)
            g = (np.clip(1 - d, 0, 1) ** 1.3)[..., None] * 0.34 * fade
            bg = bg + g * (np.array([120, 190, 255], np.float32) - bg)
        if self.bloom and t < self.bloom:
            k = 1 - (1 - t / self.bloom) ** 3; base = np.array([10, 9, 9], np.float32); bg = base + (bg - base) * k
        c, al = self.rgba(f"{L['behind']}/{n:05d}.png")
        if c is not None: bg = c * al + bg * (1 - al)
        M = self.M.copy(); M[1, 2] += subject_dy
        F = cv2.warpAffine(fg, M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE).astype(np.float32)
        A1 = cv2.warpAffine(a, M, (W, H), flags=cv2.INTER_LINEAR, borderValue=0)
        A2 = cv2.warpAffine(a, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        A = np.clip(np.maximum(A1, A2 * (A2 > 0.99)), 0, 1)
        bgb = cv2.GaussianBlur(bg, (0, 0), 18); band = (1 - cv2.GaussianBlur(A, (0, 0), 7))[..., None] * A[..., None]
        w = np.clip(band * 0.9, 0, 0.45); F = F * (1 - w) + bgb * w
        plate = F * A[..., None] + bg * (1 - A[..., None])
        s = self.cam(t) if cam is None else cam
        if abs(s - 1) > 1e-4:
            ax, ay = self.anchor
            plate = cv2.warpAffine(plate, np.float32([[s, 0, ax * (1 - s)], [0, s, ay * (1 - s)]]), (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
        if self.stage is not None:
            e = self.stage.mode(t)
            if e > 0:
                f = self.face[min(n, len(self.face) - 1)]; fr = self.C["framing"]; sc = fr["scale"]
                fx = ((f["x0"] + f["x1"]) / 2 - fr["x0"]) * sc; fy = ((f["y0"] + f["y1"]) / 2 - fr["y0"]) * sc + subject_dy
                ax, ay = self.anchor; fx = ax + (fx - ax) * s; fy = ay + (fy - ay) * s
                sp = self.rgba(f"{L.get('stage', '/none')}/{n:05d}.png")
                st_img = self.stage.render(n, self.bd, sp if sp[0] is not None else None)
                plate = self.stage.pip(st_img, plate, e, (fx, fy))
        for k in ("front", "caps"):
            c, al = self.rgba(f"{L[k]}/{n:05d}.png")
            if c is not None: plate = c * al + plate * (1 - al)
        return np.clip(plate, 0, 255).astype(np.uint8)

    def src(self, start=0, end=None):
        def rd(path, pix, ch):
            vf = f"trim=start_frame={start}" + (f":end_frame={end}" if end else "") + ",setpts=PTS-STARTPTS"
            p = subprocess.Popen(["ffmpeg", "-v", "quiet", "-i", path, "-vf", vf, "-f", "rawvideo", "-pix_fmt", pix, "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            n = W * H * ch
            while True:
                b = p.stdout.read(n)
                if len(b) < n: return
                yield np.frombuffer(b, np.uint8).reshape((H, W, ch) if ch > 1 else (H, W))
        for fg, m in zip(rd(self.pr.p("layers", "fg.mkv"), "bgr24", 3), rd(self.pr.p("layers", "matte.mkv"), "gray", 1)):
            yield fg, m.astype(np.float32) / 255

    def get(self, n):
        cf = cv2.VideoCapture(self.pr.p("layers", "fg.mkv")); cm = cv2.VideoCapture(self.pr.p("layers", "matte.mkv"))
        cf.set(cv2.CAP_PROP_POS_FRAMES, n); cm.set(cv2.CAP_PROP_POS_FRAMES, n); _, fg = cf.read(); _, m = cm.read()
        return fg, m[..., 0].astype(np.float32) / 255

    def _segment(self, args):
        start, end, out = args
        enc = writer(out, codec="x264", extra=["-c:v", "libx264", "-crf", "14", "-preset", "medium", "-pix_fmt", "yuv420p"])
        for k, (fg, a) in enumerate(self.src(start, end)):
            enc.stdin.write(self.frame(start + k, fg, a).tobytes())
            if k % 100 == 0: log("composite", start + k)
        enc.stdin.close(); enc.wait(); return out

    def render(self, out, workers=None):
        """Composite in parallel segments (one per CPU core), then concat losslessly."""
        n = self.pr.load("words.json")["frames"]; workers = workers or max(1, min(4, (os.cpu_count() or 2)))
        cuts = [round(n * i / workers) for i in range(workers + 1)]
        jobs = [(cuts[i], cuts[i + 1], self.pr.p("work", f"seg{i}.mp4")) for i in range(workers)]
        import multiprocessing as mp
        with mp.get_context("fork").Pool(workers) as pool: segs = pool.map(self._segment, jobs)
        lst = self.pr.p("work", "segs.txt"); open(lst, "w").write("".join(f"file '{s}'\n" for s in segs))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out], check=True)

    def sheet(self, frames, out, layers=None, label=True, width=360):
        ims = []
        for n in frames:
            im = self.frame(n, *self.get(n), layers=layers)
            if label: cv2.putText(im, f"{n/FPS:.2f}s", (30, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (245, 245, 244), 3, cv2.LINE_AA)
            ims.append(cv2.resize(im, (width, int(width * 16 / 9))))
        rows = [np.hstack(ims[i:i + 6] + [np.zeros_like(ims[0])] * (6 - len(ims[i:i + 6]))) for i in range(0, len(ims), 6)]
        cv2.imwrite(out, np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 88])
