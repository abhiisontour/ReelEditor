"""reelkit CLI.
  python -m reelkit.run analyze  <project> --name NAME [--hook "line1|key|line3"] [--day N]
  python -m reelkit.run storyboard <project>          # stills of every scene peak (fast) -> qc/storyboard.jpg + compass.md
  python -m reelkit.run build    <project>            # full render from compass.json (re-runs only what changed)
  python -m reelkit.run cover    <project>
Project layout: <project>/input/{clips..., script.txt}; everything else is generated."""
import argparse, hashlib, json, os, sys, shutil
import cv2, numpy as np
from .common import Project, WEB, FPS, log, node_render, at
from . import transcribe, cutout, captions, compass, sound, stage, split
from .comp import Comp


def H(*objs): return hashlib.md5(json.dumps(objs, sort_keys=True, default=str).encode()).hexdigest()[:12]


class State:
    def __init__(self, pr): self.pr = pr; self.s = pr.load("work/state.json", {})
    def changed(self, k, h): return self.s.get(k) != h
    def done(self, k, h): self.s[k] = h; self.pr.save("work/state.json", self.s)


def stage_edit(pr, st, force=False):
    C = pr.compass; h = H(C["edit"])
    if force or st.changed("edit", h) or not pr.has("words.json"): transcribe.apply_edit(pr); st.done("edit", h); return True


def stage_key(pr, st, force=False):
    C = pr.compass; h = H(st.s.get("edit"), C.get("key"), C["framing"].get("table_line"))
    if force or st.changed("key", h) or not pr.has("layers", "matte_raw.mkv"):
        for f in ("plate_k.npy", "plate_kn.npy"):
            if pr.has("work", f): os.remove(pr.p("work", f))
        cutout.build_matte(pr); cutout.face_track(pr); st.done("key", h); return True


def stage_enhance(pr, st, force=False):
    C = pr.compass; h = H(st.s.get("key"), C.get("picture"), C["framing"].get("prop_zones"), C["framing"].get("table_line"))
    if force or st.changed("enhance", h) or not pr.has("layers", "matte.mkv"):
        cutout.enhance(pr); cutout.face_track(pr, "layers/matte.mkv"); st.done("enhance", h); return True


def stage_layers(pr, st, frames=None):
    C = pr.compass; W = pr.load("words.json"); n = frames or W["frames"]
    if any(s["type"] in stage.STAGE_TYPES for s in C.get("scenes", [])): stage.prepare(pr)
    hc = H(st.s.get("enhance"), C["captions"], C["framing"], C.get("scenes"), W["words"])
    hm = H(C.get("scenes"), C.get("palette"), W["words"])
    if frames or st.changed("captions", hc):
        captions.build(pr); node_render(os.path.join(WEB, "captions.html"), f"p={pr.root}", pr.p("layers", "captions"), n)
        if not frames: st.done("captions", hc)
    has_stage = any(s["type"] in stage.STAGE_TYPES for s in C.get("scenes", []))
    hm = H(hm, has_stage and stage.prepare(pr))
    if frames or st.changed("motion", hm):
        for L in ("behind", "front") + (("stage",) if has_stage else ()): node_render(os.path.join(WEB, "motion.html"), f"p={pr.root}&layer={L}", pr.p("layers", L), n)
        if not frames: st.done("motion", hm)
    split.render_hook(pr, node_render, WEB)


def analyze(a):
    pr = Project(a.project); name = a.name or os.path.basename(pr.root)
    an = transcribe.analyze(pr); pr.save("work/analysis.json", an)
    hook = a.hook.split("|") if a.hook else None
    C = compass.draft(name, an, hook, a.day); pr.save("compass.json", C)
    st = State(pr); stage_edit(pr, st, True)
    table = cutout.detect_table(pr); C["framing"]["table_line"] = table; pr.save("compass.json", C)
    stage_key(pr, st, True)
    fr = cutout.auto_framing(pr, table, C["framing"]["scale"]); C["framing"].update(fr)
    C["framing"]["prop_candidates"] = cutout.prop_scan(pr, table)
    W = pr.load("words.json")
    C["captions"]["chunks"] = captions.draft(pr, [w for l in (hook or []) for w in l.split()], [hook[1]] if hook else [])
    if hook:   # hook pulse when the key word is actually said
        key = hook[1].strip("…. ").lower(); hit = next((w["i"] for w in W["words"] if w["clean"] == key), None)
        if hit is not None: C["scenes"][0]["parts"]["said"] = {"word": hit}
    split_from_script(C, an, W, hook, a.day)
    for k, sg in enumerate(an.get("segments", [])):
        if sg["kind"] in ("talk", "broll", "split"): continue
        w0 = next((w["i"] for w in W["words"] if w.get("si", -1) >= sg["t0"]), None); w1 = next((w["i"] for w in W["words"] if w.get("si", -1) >= sg["t1"]), None)
        if w0 is None: continue
        sc = {"id": f"{sg['kind'].upper()}{k}", "in": {"word": w0}, "out": {"word": w1} if w1 is not None else None, "note": sg["note"], "colors": ["sky", "mint"]}
        if sg["kind"] == "demo":
            sc.update(type="screen", media=sg.get("file") or "MISSING", device="auto", url="", label="", media_in=0.0, speed=1.0, zooms=[], highlights=[], taps=[])
        else:
            sc.update(type="title_card", text=sg["note"][:24], sub="", todo="design: bars / steps / compare / title_card")
        C["scenes"].append(sc)
    last = W["words"][-1]
    C["cover"]["frame"] = max(0, W["frames"] - 6)
    pr.save("compass.json", C)
    stage_enhance(pr, st, True)
    closing_sheet(pr)
    log("analyze done. Next: design scenes in compass.json, then `storyboard`.")


def split_from_script(C, an, W, hook, day, total=75):
    """[BROLL: note | file | in=s] and [SPLIT: note] spans -> compass.split segments. A span starting at the first word
    becomes the series opener: static hook + series pill on the seam for 0-3.5 s (it replaces the HOOK scene and badge)."""
    ws = W["words"]; segs = []
    for sg in an.get("segments", []):
        if sg["kind"] not in ("broll", "split"): continue
        w0 = next((w["i"] for w in ws if w.get("si", -1) >= sg["t0"]), None); w1 = next((w["i"] for w in ws if w.get("si", -1) >= sg["t1"]), None)
        if w0 is None: continue
        t0 = 0.0 if w0 == 0 else round(max(ws[w0 - 1]["end"], ws[w0]["start"] - 0.12), 3)
        t1 = round(ws[w1]["start"] - 0.05, 3) if w1 is not None else round(ws[-1]["end"] + 0.6, 3)
        top = {"media": sg["file"], "in": float(sg.get("opts", {}).get("in", 0))} if sg["kind"] == "broll" and sg.get("file") else \
              {"scenes": [], "zoom": 1.15, "todo": "design: icon_tiles/cards scenes for the top half (" + sg["note"] + ")"}
        segs.append({"from": {"time": t0}, "to": {"time": t1}, "note": sg["note"], "top": top})
    if not segs: return
    for x, y in zip(segs, segs[1:]):          # back-to-back spans share one boundary (no gap, no overlap)
        if y["from"]["time"] - x["to"]["time"] < 0.4: x["to"] = {"time": y["from"]["time"]}
    if segs[0]["from"]["time"] == 0.0 and hook:
        o = segs[0]; HOOK_T = 3.5
        if o["to"]["time"] > HOOK_T + 0.6:   # hook overlay only for the first 3.5 s; the same B-roll continues after it
            rest = {**o, "from": {"time": HOOK_T}, "top": {**o["top"]}}
            if "media" in rest["top"]: rest["top"]["in"] = rest["top"]["in"] + HOOK_T
            o["to"] = {"time": HOOK_T}; segs.insert(1, rest)
            if rest["to"]["time"] - HOOK_T < 1.0 and len(segs) > 2 and segs[2]["from"]["time"] == rest["to"]["time"]:
                segs.pop(1); segs[1]["from"] = {"time": HOOK_T}          # too short to show: cut straight to the next B-roll
        elif len(segs) > 1 and segs[1]["from"]["time"] == o["to"]["time"]:
            o["to"] = {"time": HOOK_T}; segs[1]["from"] = {"time": HOOK_T}
        o["overlay"] = "hook"
        C["scenes"] = [s for s in C["scenes"] if s["type"] not in ("text_hook", "badge")]
        C["captions"]["hide_until"] = o["to"]["time"]; C["sound"]["quiet_until"] = o["to"]["time"]
        hk = {"lines": hook, "colors": ["peach", "coral", "rose"]}
        if day is not None: hk["series"] = f"Day {day:02d}/{total} · Of making your travel easy"
        C["split"] = {"layout": {}, "hook": hk, "segments": segs}
    else:
        C["split"] = {"layout": {}, "segments": segs}
    C["sound"]["whoosh"] = "layout"
    C["camera"] = [k for k in C["camera"] if k.get("why") != "opening settle" and not (k.get("at") == {"time": 0.0} and k.get("dur") == 0.6)] or [{"at": {"time": 0.0}, "to": 1.0, "dur": 0.0}]


def media_sheet(a):
    """Contact sheet of a screen recording with timestamps + a 10% grid, so zoom/highlight rects can be read off it."""
    pr = Project(a.project); f = pr.p("input", "media", a.name); info = stage.media_info(f); ims = []
    if info["kind"] == "image": frames = [(0.0, cv2.imread(f))]
    else:
        cap = cv2.VideoCapture(f); dur = info["dur"] or 10; frames = []
        for t in np.arange(0, dur, max(0.5, dur / 24)):
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000); ok, im = cap.read()
            if ok: frames.append((t, im))
    for t, im in frames:
        h, w = im.shape[:2]; s = 360 / max(w, h); im = cv2.resize(im, (int(w * s), int(h * s)))
        for k in range(1, 10):
            cv2.line(im, (int(im.shape[1] * k / 10), 0), (int(im.shape[1] * k / 10), im.shape[0]), (80, 80, 255), 1)
            cv2.line(im, (0, int(im.shape[0] * k / 10)), (im.shape[1], int(im.shape[0] * k / 10)), (80, 80, 255), 1)
        cv2.putText(im, f"{t:.1f}s", (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        ims.append(cv2.copyMakeBorder(im, 0, 360 - im.shape[0], 0, 360 - im.shape[1], cv2.BORDER_CONSTANT))
    rows = [np.hstack(ims[i:i + 6] + [np.zeros_like(ims[0])] * (6 - len(ims[i:i + 6]))) for i in range(0, len(ims), 6)]
    out = pr.p("qc", f"media_{os.path.splitext(a.name)[0]}.jpg"); cv2.imwrite(out, np.vstack(rows)); log("media sheet:", out)


def closing_sheet(pr):
    W = pr.load("words.json"); n = W["frames"]; fr = list(range(max(0, n - 36), n, 3))
    face = pr.load("work/face_src.json"); ims = []
    cap = cv2.VideoCapture(pr.p("layers", "fg.mkv"))
    for k in fr:
        cap.set(cv2.CAP_PROP_POS_FRAMES, k); _, f = cap.read(); b = face[k]
        c = f[max(0, b["y0"] - 40):b["y1"], max(0, b["x0"] - 60):b["x1"] + 60]; c = cv2.resize(c, (200, int(200 * c.shape[0] / c.shape[1])))
        c = cv2.copyMakeBorder(c[:260], 0, max(0, 260 - c[:260].shape[0]) + 30, 0, 0, cv2.BORDER_CONSTANT, value=(9, 9, 10))
        cv2.putText(c, f"#{k}", (8, c.shape[0] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (245, 245, 244), 2); ims.append(c)
    cv2.imwrite(pr.p("qc", "closing_faces.jpg"), np.hstack(ims))


def storyboard(a):
    pr = Project(a.project); C = pr.compass; W = pr.load("words.json"); ws = W["words"]
    pts = []
    for s in C["scenes"]:
        t0 = at(s.get("in"), ws, 0.0); t1 = at(s.get("out"), ws, W["duration"]) if s.get("out") else W["duration"]
        if s["type"] in ("badge",): continue
        pts.append(min(t1 - 0.1, t0 + max(0.45, (t1 - t0) * 0.75)))
    frames = sorted(set(min(W["frames"] - 1, int(t * FPS)) for t in pts))
    st = State(pr); stage_layers(pr, st, ",".join(map(str, frames)))
    S = C.get("sound", {}); C["_cues_preview"] = S.get("cues") if S.get("cues_mode") == "manual" else sound.auto_cues(pr); pr.save("compass.json", C)
    Comp(pr).sheet(frames, pr.p("qc", "storyboard.jpg"))
    open(pr.p("compass.md"), "w").write(compass.render_md(C, W))
    log("storyboard + compass.md ready:", pr.p("qc", "storyboard.jpg"), pr.p("compass.md"))


def build(a):
    pr = Project(a.project); st = State(pr); name = pr.compass["name"]
    for f in (stage_edit, stage_key, stage_enhance):
        f(pr, st)
    stage_layers(pr, st)
    log("compositing"); Comp(pr).render(pr.p("layers", "picture.mp4"))
    sound.clean_voice(pr); sound.mix(pr); out = sound.master_and_export(pr, name)
    cover(a); qc(pr); log("BUILD DONE", out)


def cover(a):
    pr = Project(a.project); C = pr.compass; cv = C["cover"]; W = pr.load("words.json"); comp = Comp(pr)
    n = cv["frame"] if isinstance(cv["frame"], int) else W["frames"] - 6
    if comp.split is not None and comp.split.segs and comp.split.segs[0][2].get("overlay") == "hook":
        # series cover = the opener's split look: opener B-roll on top, hook on the seam, closing smile below
        a0, b0, g = comp.split.segs[0]; g = {**g, "_top": comp.face[n]["y0"] - 40}
        fg, al = comp.get(n); im = comp.split.frame(a0 + (b0 - a0) // 2, fg, al, (a0, b0, g), comp.layers, comp.bd)
        cv2.imwrite(pr.p("renders", f"cover_{C['name']}.jpg"), im, [cv2.IMWRITE_JPEG_QUALITY, 95]); return
    hook = next((s for s in C["scenes"] if s["type"] == "text_hook"), None)
    tf = cv.get("text_frame") or (int((at(hook["out"], W["words"], 3.0) - 0.8) * FPS) if hook else n)
    tmp = pr.p("work", "cover_layers"); os.makedirs(tmp, exist_ok=True)
    node_render(os.path.join(WEB, "motion.html"), f"p={pr.root}&layer=behind", tmp, f"{tf},{tf}")
    b = cv2.imread(f"{tmp}/{tf:05d}.png", cv2.IMREAD_UNCHANGED); dy = cv.get("text_dy", 52)
    b = np.roll(b, dy, axis=0); b[:dy] = 0; cv2.imwrite(f"{tmp}/{n:05d}.png", b)
    im = comp.frame(n, *comp.get(n), layers={"behind": tmp, "front": "/nonexistent", "caps": "/nonexistent"}, cam=1.0, subject_dy=cv.get("subject_dy", 48))
    cv2.imwrite(pr.p("renders", f"cover_{C['name']}.jpg"), im, [cv2.IMWRITE_JPEG_QUALITY, 95])


def qc(pr):
    W = pr.load("words.json"); n = W["frames"]; fr = [int(x) for x in np.linspace(3, n - 3, 12)]
    out = pr.p("renders", f"final_{pr.compass['name']}.mp4")
    sel = "+".join(f"eq(n\\,{k})" for k in fr)
    os.system(f"ffmpeg -v error -y -i '{out}' -vf \"select='{sel}',scale=270:480,tile=6x2\" -frames:v 1 '{pr.p('qc','final_sheet.jpg')}'")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("cmd"); ap.add_argument("project")
    ap.add_argument("--name"); ap.add_argument("--hook"); ap.add_argument("--day", type=int)
    a = ap.parse_args()
    {"analyze": analyze, "storyboard": storyboard, "build": build, "cover": cover, "media-sheet": media_sheet}[a.cmd](a)


if __name__ == "__main__":
    main()
