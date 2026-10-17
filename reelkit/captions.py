"""Pass 03: caption chunks (1-3 words), one key word per sentence, face guard. Draft is auto; the compass is the truth."""
import re
from .common import Project, at, PALETTE, FPS

STOP = set("a an the and or but if to of in on at by for with from is am are was were be been it its this that these those you your i me my we our "
           "he she they them his her their will would can could should do does did so as up out not no yes just than then there here what when "
           "who how why all any each every some more most very well".split())
SCENE_GRAD = {"default": ["peach", "coral", "rose"]}


# words that start a phrase (break before them) and words that must not end a caption (dangling)
LEAD = set("to and or but by in on at for with from that which who if when so because than of the a an my your our".split())
DANGLE = set("a an the to of my your our their his her its in on at by for with and or but i you we".split())


def auto_chunks(words, sentences):
    """Phrase-aware 1-3 word groups: break at punctuation, before phrase-starting words, never end on a dangling word."""
    chunks = []
    for sent in sentences:
        k = 0
        while k < len(sent):
            best, bs = None, -9
            for L in (1, 2, 3):
                if k + L > len(sent): break
                grp = sent[k:k + L]; last = words[grp[-1]]; nxt = words[sent[k + L]] if k + L < len(sent) else None
                s = 0.0
                if re.search(r"[,.;:?!…]$", last["text"]): s += 3
                if nxt is None: s += 3
                elif nxt["clean"] in LEAD: s += 1.5
                if last["clean"] in DANGLE and nxt is not None: s -= 4
                if any(re.search(r"[,.;:?!…]$", words[i]["text"]) for i in grp[:-1]): s -= 6
                if nxt is not None and k + L == len(sent) - 1: s -= 2.5          # don't strand the last word alone
                s += {1: -1.6, 2: 0.4, 3: 0.3}[L]
                if s > bs: best, bs = L, s
            chunks.append(sent[k:k + best]); k += best
    out = chunks
    merged = True
    while merged:   # hold >= 0.4 s
        merged = False
        for k in range(len(out) - 1):
            if words[out[k + 1][0]]["start"] - words[out[k][0]]["start"] < 0.4 and len(out[k]) + len(out[k + 1]) <= 3 and not words[out[k][-1]]["sentence_end"]:
                out[k] = out[k] + out[k + 1]; del out[k + 1]; merged = True; break
    return out


def pick_keys(words, sentences, prefer=(), strong=()):
    keys = []
    pref = {re.sub(r"[^a-z0-9]", "", p.lower()) for p in prefer}; strong = {re.sub(r"[^a-z0-9]", "", p.lower()) for p in strong}
    for sent in sentences:
        best, bs = None, -1
        for k, i in enumerate(sent):
            c = words[i]["clean"]
            if not c or c in STOP: continue
            s = (6 - k * 0.01 if re.fullmatch(r"\d+", c) else 4 if re.search(r"\d", c) else len(c) / 3) + (2 if c in pref else 0) + (6 if c in strong else 0) - (1 if k == 0 else 0)
            if s > bs: best, bs = i, s
        keys.append(best)
    return keys


def draft(pr: Project, hook_words=(), hook_key=()):
    W = pr.load("words.json"); ws, sents = W["words"], W["sentences"]
    chunks = auto_chunks(ws, sents); keys = set(k for k in pick_keys(ws, sents, hook_words, hook_key) if k is not None)
    out = []
    for c in chunks:
        d = {"w": c, "text": " ".join(ws[i]["text"] for i in c)}
        kk = [i for i in c if i in keys]
        if kk: d["key"] = kk[0]
        out.append(d)
    return out


def build(pr: Project):
    """compass.captions -> work/captions_render.json with absolute times, colours and the face-guarded y position per chunk."""
    C = pr.compass; W = pr.load("words.json"); ws = W["words"]; cap = C["captions"]
    face = pr.load("work/face_src.json"); fr = C["framing"]; s = fr["scale"]
    fy1 = [(f["y1"] - fr["y0"]) * s for f in face]
    hide_until = cap.get("hide_until", 0.0)
    scenes = [(at(x.get("in"), ws, 0), at(x.get("out"), ws, W["duration"] + 1), x.get("colors")) for x in C.get("scenes", []) if x.get("colors")]
    stg = pr.load("work/stage.json", {"scenes": {}})["scenes"]
    phone_demo = [] if cap.get("show_during_demo") else [(at(x.get("in"), ws, 0), at(x.get("out"), ws, 1e9)) for x in C.get("scenes", [])
                                                         if x["type"] == "screen" and stg.get(x["id"], {}).get("device") == "phone"]
    ch = cap["chunks"]; out = []
    for k, c in enumerate(ch):
        t0 = ws[c["w"][0]]["start"]; t1 = ws[ch[k + 1]["w"][0]]["start"] if k + 1 < len(ch) else W["duration"] + 0.7
        hide = c.get("hide") or t1 <= hide_until or any(a <= t0 < b for a, b in phone_demo)
        grad = c.get("grad")
        if c.get("key") is not None and not grad:
            col = next((cols for a, b, cols in scenes if a <= ws[c["key"]]["start"] < b), None) or SCENE_GRAD["default"]
            grad = [PALETTE.get(x, x) for x in col]
        f0, f1 = int(t0 * FPS), max(int(t0 * FPS) + 1, int(t1 * FPS))
        out.append({"t0": round(max(t0, hide_until if t0 < hide_until < t1 else t0), 3), "t1": round(t1, 3), "hide": bool(hide), "hide_key": bool(c.get("hide_key")),
                    "words": [{"text": ws[i]["text"], "t": ws[i]["start"], "key": i == c.get("key")} for i in c["w"]],
                    "grad": grad, "face_bottom": max(fy1[f0:f1] or [0])})
    pr.save("work/captions_render.json", {"chunks": out, "style": cap.get("style", {})})
