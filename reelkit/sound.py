"""Pass 05: voice clean, synthesised SFX placed on cues derived from the compass scenes, music bed ducked under the voice,
two-pass loudness master, final export, cover, BGM file."""
import json, os, re
import numpy as np, soundfile as sf
from scipy import signal
from .common import Project, sh, at, SR, FPS, log

rng = np.random.default_rng(7)
def _t(d): return np.arange(int(d * SR)) / SR
def env(n, a=0.002, d=0.2): x = np.arange(n) / SR; return np.minimum(1, x / max(a, 1e-4)) * np.exp(-x / d)
def bp(x, lo, hi): return signal.sosfilt(signal.butter(2, [lo, hi], "band", fs=SR, output="sos"), x)
def hp(x, f): return signal.sosfilt(signal.butter(2, f, "high", fs=SR, output="sos"), x)
def lp(x, f): return signal.sosfilt(signal.butter(2, f, "low", fs=SR, output="sos"), x)
def norm(x, p=0.9): return x / (np.abs(x).max() + 1e-9) * p

def whoosh(d=0.45, f0=250, f1=3500):
    n = int(d * SR); x = rng.standard_normal(n); out = np.zeros(n); blk = 480; fs = np.geomspace(f0, f1, n // blk + 1)
    for k in range(0, n, blk):
        f = fs[k // blk]; y = bp(x[max(0, k - 2000):k + blk], f * 0.6, min(f * 1.6, SR / 2 - 100)); out[k:k + blk] = y[-len(out[k:k + blk]):]
    return norm(out * np.sin(np.linspace(0, np.pi, n)) ** 1.6, 0.8)
def tap(f=1900, d=0.05):
    t = _t(d + 0.02); return norm(hp(rng.standard_normal(len(t)), 3000) * env(len(t), 0.0003, 0.003) * 0.6 + np.sin(2 * np.pi * f * t) * env(len(t), 0.0005, d / 3), 0.8)
def tick(): return tap(4200, 0.015) * 0.7
def pop():
    f0, f1 = 500 + rng.integers(0, 250), 1100 + rng.integers(0, 300); t = _t(0.09); f = f0 + (f1 - f0) * (1 - np.exp(-t / 0.015))
    return norm(np.sin(2 * np.pi * np.cumsum(f) / SR) * env(len(t), 0.001, 0.025), 0.7)
def coin():
    t = _t(0.7); x = sum(a * np.sin(2 * np.pi * f * t) * env(len(t), 0.0005, d) for f, a, d in [(2093, 1, .35), (3360, .7, .25), (5210, .45, .18), (6870, .3, .12)])
    s = int(0.07 * SR); x[s:] += x[:-s] * 0.45; tp = tap(2600); x[:len(tp)] += tp * 0.5; return norm(x, 0.8)
def zap():
    t = _t(0.16); return norm(bp(rng.standard_normal(len(t)), 1800, 7000) * (0.5 + 0.5 * np.sign(np.sin(2 * np.pi * 70 * t))) * env(len(t), 0.001, 0.05), 0.6)
def clock_ticks(n=6, gap=0.11):
    out = np.zeros(int((n * gap + 0.05) * SR)); tk = tick()
    for i in range(n): s = int(i * gap * SR); out[s:s + len(tk)] += tk * (1 if i % 2 == 0 else 0.7)
    return out
def cascade(n=20, gap=0.016):
    out = np.zeros(int((n * gap + 0.05) * SR)); tk = tick()
    for i in range(n): s = int(i * gap * SR); out[s:s + len(tk)] += tk * (0.6 + 0.4 * (i % 3 == 0))
    return out
def chime():
    out = np.zeros(int(1.9 * SR))
    for i, f in enumerate([1046.5, 1318.5, 1568.0]):
        t = _t(1.6); x = (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * f * 2.76 * t) * env(len(t), .001, .15) + 0.15 * np.sin(2 * np.pi * f * 5.4 * t) * env(len(t), .001, .06)) * env(len(t), .002, .55)
        s = int(i * 0.085 * SR); out[s:s + len(x)] += x * (0.8 + 0.1 * i)
    return norm(out, 0.8)
def plane(d=1.0): n = int(d * SR); return norm(lp(rng.standard_normal(n), 900) * np.sin(np.linspace(0, np.pi, n)) ** 2, 0.5)
def hit():
    t = _t(1.0); f = 38 + 50 * np.exp(-t / 0.05); sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * env(len(t), .001, .32)
    return norm(np.tanh(1.6 * (sub + hp(rng.standard_normal(len(t)), 1500) * env(len(t), .0005, .025) * .5)), 0.95)
BANK = {"whoosh": whoosh, "release": lambda: whoosh(0.5, 2600, 300) * 0.8, "tap": tap, "tap1": lambda: tap(1700), "tap2": lambda: tap(1950), "tap3": lambda: tap(2250),
        "tick": tick, "pop": pop, "coin": coin, "zap": zap, "clock": clock_ticks, "cascade": cascade, "chime": chime, "plane": plane, "hit": hit}
DEFAULT_DB = {"whoosh": -27, "release": -30, "tap": -20, "tap1": -20, "tap2": -21, "tap3": -20, "tick": -26, "pop": -24, "coin": -19, "zap": -25,
              "clock": -23, "cascade": -24, "chime": -15, "plane": -35, "hit": -11}


def auto_cues(pr: Project):
    C = pr.compass; W = pr.load("words.json"); ws = W["words"]; S = C.get("sound", {})
    quiet = S.get("quiet_until", 3.0); cues = []
    T = lambda s, d=None: at(s, ws, d)
    def add(t, name, why, db=None):
        if t is None: return
        cues.append({"t": round(max(0.0, t), 3), "sfx": name, "cue": why, "gain_db": DEFAULT_DB[name] if db is None else db})
    for sc in C.get("scenes", []):
        t0 = T(sc.get("in"), 0.0); P = sc.get("parts", {}); typ = sc["type"]
        if t0 >= quiet and typ not in ("badge", "text_hook"): add(t0 - 0.12, "whoosh", f"scene change {sc['id']}")
        if typ == "bubbles": [add(t0 + i * 0.07, "pop", f"bubble {i+1}") for i in range(4)]
        if typ == "route": add(t0 + 0.1, "plane", "plane pass")
        if typ == "streak_grid": add(t0, "tap", "first tile"); add(T(P.get("grid")), "cascade", "grid fills")
        if typ == "calendar": add(T(P.get("day")), "tap1", "calendar"); add(T(P.get("month")), "tap2", "month"); add(T(P.get("time")), "tap3", "time pill")
        if typ in ("cards", "list", "icon_tiles"):
            for i, it in enumerate(sc.get("items", [])):
                ta = T(it.get("at"), t0 + 0.2 + i * 0.4); o = it.get("object")
                if o == "coin": add(ta, "coin", f"coin ({it['title']})")
                elif o == "clock": add(ta, "clock", f"clock ({it['title']})")
                elif o == "calm": add(ta + 0.08, "release", f"release ({it['title']})")
                else: add(ta, "tap", f"pop ({it['title']})")
                if it.get("icon") == "bolt": add(ta + 0.1, "zap", "bolt flicker")
        if typ == "stat": add(t0, "cascade", "count up")
        if typ == "cta": add(T(P.get("tap")), "tap", "button tap", -18)
        if typ in ("screen", "bars", "steps", "compare", "title_card") and sc.get("out"):
            add(T(sc.get("out")) - 0.1, "whoosh", f"back to camera after {sc['id']}")
        if typ == "screen": [add(T(tp.get("at")), "tap", "screen tap") for tp in sc.get("taps", [])]
        if typ == "bars": add(t0 + 0.35, "cascade", "bars grow")
        if typ == "steps": [add(T(x.get("at"), t0 + 0.3 + i * 0.5), "tap", f"step {i+1}") for i, x in enumerate(sc.get("steps", []))]
        if typ == "compare": add(T((sc.get("left") or {}).get("at"), t0 + 0.2), "tap", "left card"); add(T((sc.get("right") or {}).get("at"), t0 + 0.6), "tap", "right card")
    for k in C.get("camera", []):
        if k.get("dur", 0.3) == 0:
            t = T(k.get("at"))
            if t is not None and t >= quiet and not any(c["sfx"] == "whoosh" and abs(c["t"] - (t - 0.18)) < 0.35 for c in cues): add(t - 0.18, "whoosh", "snap push-in")
    add(T(S.get("chime_at"), ws[-1]["start"]), "chime", "close chime")
    return sorted(cues, key=lambda c: c["t"])


def clean_voice(pr: Project):
    V = pr.compass.get("sound", {}).get("voice", {})
    af = (f"highpass=f={V.get('highpass', 80)}:poles=2,afftdn=nr={V.get('denoise_nr', 12)}:nf=-42:tn=1,"
          f"equalizer=f=300:t=q:w=1.2:g={V.get('boxy_cut_db', -2.5)},equalizer=f=3500:t=q:w=1.0:g={V.get('presence_db', 2.5)},equalizer=f=120:t=q:w=0.8:g=1,"
          "deesser=i=0.35:m=0.5:f=0.5:s=o,acompressor=threshold=-22dB:ratio=3:attack=8:release=120:makeup=3dB:knee=4")
    sh(["ffmpeg", "-v", "error", "-y", "-i", pr.p("work", "base.mov"), "-vn", "-ac", "1", "-ar", str(SR), "-af", af, "-c:a", "pcm_s24le", pr.p("work", "voice_clean.wav")])


def music(N, dur, M):
    if not M.get("on", True): return np.zeros((N, 2))
    bpm = M.get("bpm", 100); beat = 60 / bpm; root = {"C": 48, "D": 50, "E": 52, "F": 53, "G": 55, "A": 45, "B": 47}[M.get("key", "D")]
    prog = [[0, 7, 12, 16], [-3, 4, 9, 12], [-7, 0, 5, 9], [-5, 2, 7, 11]]          # I vi IV V
    mf = lambda m: 440 * 2 ** ((m - 69) / 12); bar = 4 * beat; mus = np.zeros((N, 2))
    for b in range(int(dur / bar) + 1):
        ch = [root + x for x in prog[b % 4]]; s = int(b * bar * SR); n = int((bar + 0.6) * SR); t = np.arange(n) / SR
        pad = sum(np.sin(2 * np.pi * mf(m) * t * (1 + d)) for m in ch for d in (-0.003, 0.003)) / 8
        pad = lp(pad + 0.2 * np.sign(pad) * pad ** 2, 1400) * np.minimum(1, t / 0.6) * np.minimum(1, (bar + 0.6 - t) / 0.6)
        e = min(N, s + n); mus[s:e] += pad[:e - s, None] * 0.55
        for i in range(8):
            m = ch[[0, 1, 2, 3, 2, 1, 2, 3][i]] + 12; st = s + int(i * beat / 2 * SR); nn = int(0.5 * SR); tt = np.arange(nn) / SR
            p = (np.sin(2 * np.pi * mf(m) * tt) + 0.3 * np.sin(4 * np.pi * mf(m) * tt)) * env(nn, 0.002, 0.18); pan = 0.35 if i % 2 else -0.35; e2 = min(N, st + nn)
            if st < N: mus[st:e2, 0] += p[:e2 - st] * 0.22 * (1 - pan); mus[st:e2, 1] += p[:e2 - st] * 0.22 * (1 + pan)
    return mus * (np.minimum(1, np.arange(N) / SR / 0.8) * np.clip((dur - np.arange(N) / SR) / 1.2, 0, 1))[:, None]


def mix(pr: Project):
    C = pr.compass; S = C.get("sound", {}); W = pr.load("words.json"); dur = W["duration"] + 0.6; N = int(dur * SR)
    cues = S.get("cues") if S.get("cues_mode") == "manual" else auto_cues(pr)
    drop = set(S.get("remove", [])); cues = [c for c in cues if c["sfx"] not in drop and c["cue"] not in drop] + S.get("extra_cues", [])
    for c in cues: c["gain_db"] = c.get("gain_db", DEFAULT_DB[c["sfx"]]) + S.get("sfx_trim_db", {}).get(c["sfx"], 0)
    pr.save("work/cues.json", cues)
    v, _ = sf.read(pr.p("work", "voice_clean.wav")); v = np.pad(v, (0, max(0, N - len(v))))[:N]
    rms = np.sqrt(np.convolve(v ** 2, np.ones(int(0.03 * SR)) / int(0.03 * SR), "same")); speaking = (20 * np.log10(rms + 1e-9) > -38).astype(float)
    vref = np.sqrt((v[speaking > 0] ** 2).mean())
    sfx = np.zeros((N, 2))
    for k, c in enumerate(cues):
        x = BANK[c["sfx"]](); g = 10 ** (c["gain_db"] / 20) * vref / 0.085; s = int(c["t"] * SR); e = min(N, s + len(x))
        pan = [-.5, .5, -.3, .3][k % 4] if c["sfx"] == "pop" else 0.0
        sfx[s:e, 0] += x[:e - s] * g * np.sqrt(1 - pan); sfx[s:e, 1] += x[:e - s] * g * np.sqrt(1 + pan)
    M = S.get("music", {}); mus = music(N, dur, M)
    if mus.any():
        duck = np.convolve(speaking, np.ones(int(0.25 * SR)) / int(0.25 * SR), "same")
        mus = mus / np.sqrt((mus ** 2).mean() + 1e-12) * vref * 10 ** (M.get("level_db", -21) / 20)
        bgm = mus.copy(); mus *= (10 ** (M.get("duck_db", -6) * np.clip(duck * 1.5, 0, 1) / 20))[:, None]
        sf.write(pr.p("work", "bgm.wav"), bgm / np.abs(bgm).max() * 0.9, SR, subtype="PCM_24")
    out = np.stack([v, v], 1) + sfx + mus
    sf.write(pr.p("work", "mix_premaster.wav"), out / max(1, np.abs(out).max() / 0.98), SR, subtype="PCM_24")
    log(f"mix: {len(cues)} cues")


def master_and_export(pr: Project, name):
    import subprocess
    pre = pr.p("work", "mix_premaster.wav")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", pre, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"], capture_output=True, text=True)
    J = json.loads(r.stderr[r.stderr.rindex("{"):r.stderr.rindex("}") + 1])
    sh(["ffmpeg", "-v", "error", "-y", "-i", pre, "-af", f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={J['input_i']}:measured_TP={J['input_tp']}:measured_LRA={J['input_lra']}:measured_thresh={J['input_thresh']}:offset={J['target_offset']}:linear=true,alimiter=limit=0.83:attack=1:release=50:level=false",
        "-ar", str(SR), "-c:a", "pcm_s24le", pr.p("work", "master.wav")])
    out = pr.p("renders", f"final_{name}.mp4")
    sh(["ffmpeg", "-v", "error", "-y", "-i", pr.p("layers", "picture.mp4"), "-i", pr.p("work", "master.wav"), "-filter_complex", "[0:v]tpad=stop_mode=clone:stop_duration=0.6,format=yuv420p[v]",
        "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-profile:v", "high", "-level", "4.2", "-r", "30", "-g", "60",
        "-c:a", "aac", "-b:a", "320k", "-ar", str(SR), "-ac", "2", "-shortest", "-movflags", "+faststart", out])
    if os.path.exists(pr.p("work", "bgm.wav")):
        sh(["ffmpeg", "-v", "error", "-y", "-i", pr.p("work", "bgm.wav"), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", str(SR), "-c:a", "libmp3lame", "-b:a", "320k", pr.p("renders", f"bgm_{name}.mp3")])
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", out, "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
    I = re.findall(r"I:\s+(-?[\d.]+) LUFS", r)[-1]; P = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", r)[-1]
    pr.save("work/loudness.json", {"integrated_lufs": float(I), "true_peak_dbtp": float(P)}); log(f"final: {I} LUFS, TP {P} dBTP")
    return out
