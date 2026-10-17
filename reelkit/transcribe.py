"""Pass 01: ingest clips + script, word-level ASR (Parakeet-TDT via sherpa-onnx, Whisper cross-check),
align to the script (script = ground truth for text), detect false starts / long pauses, apply the edit list."""
import os, re, glob, json, difflib
import numpy as np, soundfile as sf
from .common import Project, sh, MODELS, FPS, log

VIDEO_EXT = (".mp4", ".mov", ".m4v", ".mkv")


def ingest(pr: Project):
    clips = sorted(f for f in glob.glob(pr.p("input", "*")) if f.lower().endswith(VIDEO_EXT))
    order = pr.load("input/clip_order.json")
    if order: clips = [pr.p("input", c) for c in order]
    assert clips, "no clips in input/"
    log("clips:", [os.path.basename(c) for c in clips])
    # normalise every clip to 1080x1920 / 30 fps / 48k, then concat
    parts = []
    for i, c in enumerate(clips):
        o = pr.p("work", f"clip{i:02d}.mov"); parts.append(o)
        sh(["ffmpeg", "-v", "error", "-y", "-i", c, "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,format=yuv420p",
            "-c:v", "libx264", "-crf", "12", "-preset", "medium", "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "1", o])
    src = pr.p("work", "source.mov")
    if len(parts) == 1: os.replace(parts[0], src)
    else:
        lst = pr.p("work", "concat.txt"); open(lst, "w").write("".join(f"file '{x}'\n" for x in parts))
        sh(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", src])
    sh(["ffmpeg", "-v", "error", "-y", "-i", src, "-vn", "-ac", "1", "-ar", "16000", pr.p("work", "voice16k.wav")])
    return src


def asr(pr: Project):
    import sherpa_onnx as so
    a, sr = sf.read(pr.p("work", "voice16k.wav"), dtype="float32")
    p = f"{MODELS}/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
    rec = so.OfflineRecognizer.from_transducer(encoder=f"{p}/encoder.int8.onnx", decoder=f"{p}/decoder.int8.onnx", joiner=f"{p}/joiner.int8.onnx",
                                               tokens=f"{p}/tokens.txt", model_type="nemo_transducer", num_threads=2)
    s = rec.create_stream(); s.accept_waveform(sr, a); rec.decode_stream(s); r = s.result
    words = []
    for t, st, d in zip(r.tokens, r.timestamps, r.durations):
        core = t.strip()
        if core and not any(ch.isalnum() for ch in core) and words:
            words[-1]["punct"] = words[-1].get("punct", "") + core; continue
        if t.startswith(" ") or not words: words.append({"w": core, "start": st, "end": st + d})
        else: words[-1]["w"] += t; words[-1]["end"] = st + d
    dur = len(a) / sr
    for i, w in enumerate(words):
        w["end"] = round(min(w["end"], words[i + 1]["start"] if i + 1 < len(words) else dur), 3); w["start"] = round(w["start"], 3)
    q = f"{MODELS}/sherpa-onnx-whisper-small.en"
    wr = so.OfflineRecognizer.from_whisper(encoder=f"{q}/small.en-encoder.int8.onnx", decoder=f"{q}/small.en-decoder.int8.onnx", tokens=f"{q}/small.en-tokens.txt", num_threads=2)
    s2 = wr.create_stream(); s2.accept_waveform(sr, a); wr.decode_stream(s2)
    return words, r.text.strip(), s2.result.text.strip(), dur


norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
TAG = re.compile(r"\[(TALK|DEMO|SCREEN|ANIMATION|ANIM|BROLL|SPLIT)\s*:?\s*([^\]]*)\]", re.I)


def parse_script(raw):
    """Script markup: [TALK] ..., [DEMO: note | file.mp4] ..., [ANIMATION: note] ..., [BROLL: note | file.mp4 | in=5.8] ..., [SPLIT: note] ...
    Returns (plain script text, segments with script-token ranges)."""
    segs, plain, ntok, pos = [], [], 0, 0
    cur = {"kind": "talk", "note": "", "file": None, "t0": 0}
    for m in TAG.finditer(raw):
        chunk = raw[pos:m.start()]; toks = [t for t in re.split(r"\s+", chunk.strip()) if norm(t)]
        plain += toks; ntok += len(toks)
        cur["t1"] = ntok; segs.append(cur)
        kind = {"screen": "demo", "anim": "animation"}.get(m.group(1).lower(), m.group(1).lower())
        parts = [p.strip() for p in m.group(2).split("|")]
        opts = dict(p.split("=", 1) for p in parts[2:] if "=" in p)
        cur = {"kind": kind, "note": parts[0] if parts else "", "file": parts[1] if len(parts) > 1 and parts[1] else None, "opts": opts, "t0": ntok}
        pos = m.end()
    toks = [t for t in re.split(r"\s+", raw[pos:].strip()) if norm(t)]; plain += toks; ntok += len(toks)
    cur["t1"] = ntok; segs.append(cur)
    return " ".join(plain), [x for x in segs if x["t1"] > x["t0"] or x["kind"] != "talk"]


def align(words, script):
    """Script is ground truth for text. ASR gives timing. Returns aligned words + flags."""
    toks = [t for t in re.split(r"\s+", script.strip()) if norm(t)]
    A = [norm(w["w"]) for w in words]; S = [norm(t) for t in toks]
    out, flags = [], []
    sm = difflib.SequenceMatcher(None, A, S, autojunk=False)
    def add(w, text, **kw):
        out.append({"start": w["start"], "end": w["end"], "text": text, "asr": w["w"], **kw})
    J = {"j": None}
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for k in range(i2 - i1): add(words[i1 + k], toks[j1 + k], si=j1 + k)
        elif op == "replace":
            a, s = i2 - i1, j2 - j1
            for k in range(min(a, s)): add(words[i1 + k], toks[j1 + k], replaced=words[i1 + k]["w"], si=j1 + k)
            if a > s:
                for k in range(s, a): add(words[i1 + k], words[i1 + k]["w"], extra=True)
                flags.append({"type": "asr_extra", "at": words[i1 + s]["start"], "asr": " ".join(w["w"] for w in words[i1 + s:i2])})
            elif s > a:  # split the last matched word's time for the missing script words
                w = out[-1]; span = (w["end"] - w["start"]) / (s - a + 1); w["end"] = round(w["start"] + span, 3)
                for k in range(a, s):
                    st = w["end"] + (k - a) * span
                    out.append({"start": round(st, 3), "end": round(st + span, 3), "text": toks[j1 + k], "estimated": True, "si": j1 + k})
        elif op == "delete":
            for k in range(i1, i2): add(words[k], words[k]["w"], extra=True)
            flags.append({"type": "not_in_script", "at": words[i1]["start"], "asr": " ".join(w["w"] for w in words[i1:i2])})
        elif op == "insert":   # script words the ASR missed: place them in the gap before the next word
            prev_end = out[-1]["end"] if out else 0.0
            nxt = words[i1]["start"] if i1 < len(words) else prev_end + 0.3
            gap = max(nxt - prev_end, 0.08 * (j2 - j1)); span = gap / (j2 - j1)
            for k in range(j2 - j1):
                st = prev_end + k * span
                out.append({"start": round(st, 3), "end": round(st + span * 0.9, 3), "text": toks[j1 + k], "estimated": True, "si": j1 + k})
            flags.append({"type": "missed_by_asr", "at": round(prev_end, 3), "script": " ".join(toks[j1:j2])})
    for w in out:
        w["clean"] = norm(w["text"]); w["sentence_end"] = bool(re.search(r"[.?!…]$", w["text"]))
    return out, flags


def find_cuts(pr: Project, words, dur):
    """False starts (speech energy in a gap with no recognised/script word, or repeated words) and long silent pauses."""
    a, sr = sf.read(pr.p("work", "voice16k.wav"), dtype="float32")
    hop = int(0.02 * sr); n = len(a) // hop
    db = 20 * np.log10(np.sqrt((a[:n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-9)
    t2i = lambda t: int(t / 0.02)
    def quiet_point(t, lo, hi):   # nearest quiet frame boundary near t within [lo,hi]
        i0, i1 = t2i(max(lo, 0)), t2i(min(hi, dur))
        if i1 <= i0: return t
        k = i0 + int(np.argmin(db[i0:i1])); return round(round(k * 0.02 * FPS) / FPS, 3)
    cuts = []
    for i in range(len(words) - 1):
        a_, b_ = words[i], words[i + 1]
        g0, g1 = a_["end"], b_["start"]
        if g1 - g0 < 0.5: continue
        seg = db[t2i(g0) + 3:t2i(g1) - 2]
        speech = int((seg > -32).sum()) if len(seg) else 0
        if speech >= 5:
            cuts.append({"from": quiet_point(g0 + 0.12, g0 + 0.06, g0 + 0.25), "to": quiet_point(g1 - 0.06, g1 - 0.2, g1 - 0.02),
                         "why": f"speech in a {g1-g0:.1f}s gap before '{b_['text']}' (likely a false start / retake)", "apply": True})
        elif g1 - g0 > 0.9:
            keep = 0.35; mid0 = g0 + keep / 2; mid1 = g1 - keep / 2
            cuts.append({"from": quiet_point(mid0, mid0 - 0.05, mid0 + 0.05), "to": quiet_point(mid1, mid1 - 0.05, mid1 + 0.05),
                         "why": f"{g1-g0:.1f}s silent pause before '{b_['text']}' (tightened to ~0.35s)", "apply": True})
    # repeated phrase = restart: same 1-3 words said twice in a row -> cut the first take
    for L in (3, 2, 1):
        for i in range(len(words) - 2 * L + 1):
            A = [w["clean"] for w in words[i:i + L]]; B = [w["clean"] for w in words[i + L:i + 2 * L]]
            if A != B or any(words[i + k].get("estimated") for k in range(2 * L)): continue
            if all(words[i + k].get("extra") for k in range(L)):   # first take isn't in the script -> it's the restart
                f, t = words[i]["start"], words[i + L]["start"]
                if not any(c["from"] <= f <= c["to"] for c in cuts):
                    cuts.append({"from": quiet_point(f - 0.04, f - 0.12, f), "to": quiet_point(t - 0.06, t - 0.2, t - 0.02),
                                 "why": f"repeated '{' '.join(w['text'] for w in words[i:i+L])}' (restart)", "apply": True})
    return sorted(cuts, key=lambda c: c["from"])


def analyze(pr: Project):
    ingest(pr)
    raw, ptxt, wtxt, dur = asr(pr)
    raw_script = open(pr.p("input", "script.txt")).read() if pr.has("input", "script.txt") else ptxt
    script, segs = parse_script(raw_script)
    words, flags = align(raw, script)
    cuts = find_cuts(pr, words, dur)
    pr.save("work/words_raw.json", {"duration": round(dur, 3), "parakeet": ptxt, "whisper": wtxt, "words": words})
    log(f"{len(words)} words, {len(flags)} flags, {len(cuts)} suggested cuts, {dur:.2f}s")
    return {"duration": dur, "words": words, "flags": flags, "cuts": cuts, "asr_text": ptxt, "whisper_text": wtxt, "segments": segs}


def apply_edit(pr: Project):
    """compass.edit.cuts (source times) -> keep ranges -> work/base.mov + words.json on the OUTPUT timeline."""
    C = pr.compass; raw = pr.load("work/words_raw.json"); dur = raw["duration"]
    nfr = int(round(dur * FPS))
    cuts = sorted([c for c in C["edit"]["cuts"] if c.get("apply", True)], key=lambda c: c["from"])
    keep, cur = [], 0
    for c in cuts:
        f0, f1 = int(round(c["from"] * FPS)), int(round(c["to"] * FPS))
        if f0 > cur: keep.append([cur, f0])
        cur = max(cur, f1)
    if cur < nfr: keep.append([cur, nfr])
    pr.save("work/edl.json", {"fps": FPS, "keep": keep, "cuts": cuts})
    vf, af = [], []
    for k, (a, b) in enumerate(keep):
        vf.append(f"[0:v]trim=start_frame={a}:end_frame={b},setpts=PTS-STARTPTS[v{k}]")
        af.append(f"[0:a]atrim={a/FPS}:{b/FPS},asetpts=PTS-STARTPTS,afade=t=in:d=0.008,afade=t=out:st={(b-a)/FPS-0.008}:d=0.008[a{k}]")
    n = len(keep)
    fc = ";".join(vf + af) + ";" + "".join(f"[v{k}]" for k in range(n)) + f"concat=n={n}:v=1:a=0,format=yuv420p[v];" + "".join(f"[a{k}]" for k in range(n)) + f"concat=n={n}:v=0:a=1,aresample=48000[a]"
    sh(["ffmpeg", "-v", "error", "-y", "-i", pr.p("work", "source.mov"), "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-crf", "12", "-preset", "medium", "-r", "30", "-c:a", "pcm_s16le", pr.p("work", "base.mov")])
    def s2o(t):
        off = 0
        for a, b in keep:
            if a / FPS - 1e-6 <= t < b / FPS + 1e-6: return off + t - a / FPS
            off += (b - a) / FPS
        return None
    fixes = {int(k): v for k, v in C["edit"].get("text_fixes", {}).items()}
    out = []
    for i, w in enumerate(raw["words"]):
        if w.get("extra") and C["edit"].get("drop_extra_words", True): continue
        s, e = s2o(w["start"]), s2o(max(w["start"], w["end"] - 0.001))
        if s is None: continue
        w = dict(w, src_start=w["start"], src_end=w["end"], start=round(s, 3), end=round(max(e or s + 0.08, s + 0.08), 3))
        if i in fixes: w["text"] = fixes[i]
        out.append(w)
    for k, w in enumerate(out):
        w["i"] = k; w["frame_in"] = round(w["start"] * FPS); w["frame_out"] = round(w["end"] * FPS)
    total = sum(b - a for a, b in keep) / FPS
    sents, curs = [], []
    for w in out:
        curs.append(w["i"])
        if w["sentence_end"]: sents.append(curs); curs = []
    if curs: sents.append(curs)
    pr.save("words.json", {"fps": FPS, "duration": round(total, 3), "frames": int(round(total * FPS)), "cut_frames": [sum(b - a for a, b in keep[:k + 1]) for k in range(n - 1)],
                           "text": " ".join(w["text"] for w in out), "sentences": sents, "words": out})
    log(f"edit applied: {len(cuts)} cuts, {total:.2f}s, {len(out)} words")
