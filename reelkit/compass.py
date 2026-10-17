"""The edit compass: compass.json (machine truth) + compass.md (what Abhishek reviews and edits)."""
from .common import PALETTE, at, FPS
from . import captions as caps

SUMMARY = {
    "text_hook": lambda s: f"Text hook: \"{' '.join(s['lines'])}\" (key line big serif)",
    "big_word": lambda s: f"Big word behind head: *{s['text']}*",
    "bubbles": lambda s: "Four coloured comment bubbles drift up beside the head",
    "route": lambda s: f"Dotted route, plane flies along it, map pins. Label: {s.get('label','')}",
    "streak_grid": lambda s: f"{s.get('cols',15)}x{s.get('rows',5)} day grid: '{s.get('label_first','')}' then '{s.get('label_full','')}'",
    "calendar": lambda s: f"Tear-off calendar {s.get('month','')} {s.get('day','')}" + (f" + time pill {s['time']}" if s.get('time') else ""),
    "cards": lambda s: "Cards: " + ", ".join(f"{i['title']} ({i.get('icon','')})" for i in s["items"]),
    "list": lambda s: "Checklist: " + ", ".join(i["title"] for i in s["items"]),
    "icon_tiles": lambda s: "3D tiles: " + ", ".join(f"{i['title']} ({i.get('object', i.get('icon',''))})" for i in s["items"]),
    "stat": lambda s: f"Count-up {s.get('prefix','')}{s.get('value')}{s.get('suffix','')} — {s.get('label','')}",
    "badge": lambda s: f"Series badge {s.get('text','')} {s.get('sub','')}",
    "screen": lambda s: f"DEMO: {s.get('media')} in a {s.get('device','auto')} frame (you in a corner circle); {len(s.get('zooms',[]))} zooms, {len(s.get('highlights',[]))} highlights, {len(s.get('taps',[]))} taps",
    "bars": lambda s: f"ANIMATION bar chart: {s.get('title','')} (" + ", ".join(f"{b['label']} {b['value']}" for b in s.get('bars', [])) + ")",
    "steps": lambda s: f"ANIMATION steps: " + " → ".join(x['text'] for x in s.get('steps', [])),
    "compare": lambda s: f"ANIMATION compare: {(s.get('left') or {}).get('title','')} vs {(s.get('right') or {}).get('title','')}",
    "title_card": lambda s: f"ANIMATION title card: *{s.get('text','')}* {s.get('sub','')}" + (" — TODO: design" if s.get('todo') else ""),
    "cta": lambda s: f"*{s.get('word','')}* behind head + {s.get('button','Follow')} pill, spark burst on tap",
}


def draft(name, analysis, hook_lines=None, day=None, total=75):
    words = analysis["words"]; dur = analysis["duration"]
    c = {"name": name, "palette": PALETTE,
         "edit": {"cuts": analysis["cuts"], "text_fixes": {}, "drop_extra_words": True, "flags": analysis["flags"]},
         "framing": {"scale": 1.42, "prop_zones": []}, "key": {}, "picture": {}, "look": {"glow": 0.16, "opening_bloom": 0.6},
         "captions": {"hide_until": 3.0, "chunks": []},
         "scenes": [], "camera": [{"at": {"time": 0.0}, "to": 1.06, "dur": 0.0, "why": "opening settle"}, {"at": {"time": 0.0}, "to": 1.0, "dur": 0.6}],
         "sound": {"quiet_until": 3.0, "music": {"on": True, "key": "D", "bpm": 100, "level_db": -21, "duck_db": -6}, "remove": [], "extra_cues": [], "sfx_trim_db": {}},
         "cover": {"frame": "auto", "text_frame": None, "text_dy": 52, "subject_dy": 48}}
    if hook_lines:
        c["scenes"].append({"id": "HOOK", "type": "text_hook", "lines": hook_lines, "key_line": 1, "colors": ["peach", "coral", "rose"],
                            "in": {"time": 0.0}, "out": {"time": 3.0}, "parts": {"slam": {"time": 0.2}, "rest": {"time": 0.5}}})
    if day is not None:
        c["scenes"].append({"id": "BADGE", "type": "badge", "text": f"Day {day:02d}", "sub": f"/ {total}", "colors": ["sun", "coral"], "in": {"time": 3.0}, "out": None})
    return c


def _t(spec, words):
    t = at(spec, words); return "—" if t is None else f"{t:.2f}s"


def render_md(C, W):
    ws = W["words"]; L = []
    L += [f"# Edit compass — {C['name']}", "",
          "Edit anything below (or just reply with changes). Times are on the edited timeline unless marked *source*. When you're happy, send it back and I'll render the full reel in one go.", "",
          f"**Length after edit:** {W['duration']:.1f}s · **Words:** {len(ws)}", ""]
    L += ["## 1. Cuts (source times)", "", "| # | Cut | Why | Apply |", "|---|---|---|---|"]
    for i, c in enumerate(C["edit"]["cuts"]): L.append(f"| {i+1} | {c['from']:.2f}–{c['to']:.2f}s | {c['why']} | {'yes' if c.get('apply', True) else 'no'} |")
    if not C["edit"]["cuts"]: L.append("| — | none | | |")
    demos = [s for s in C["scenes"] if s["type"] in ("screen", "bars", "steps", "compare", "title_card")]
    if demos:
        L += ["", "**Demo / animation segments** (you shrink into a corner circle while these play):"] + [f"- {s['id']}: {_t(s.get('in'), ws)} → {_t(s.get('out'), ws) if s.get('out') else 'end'} — {s.get('note') or SUMMARY[s['type']](s)}" for s in demos]
    fl = C["edit"].get("flags", [])
    if fl:
        L += ["", "**Script vs. speech flags:**"] + [f"- {f['type'].replace('_',' ')} at {f['at']:.2f}s: {f.get('asr') or f.get('script')}" for f in fl]
    fr = C["framing"]
    L += ["", "## 2. Framing & picture", "", f"- Zoom **{fr['scale']}×**, subject centred (centre x={fr.get('subject_cx_src','auto')} in source), desk {'found' if fr.get('table_line') else 'not found'}.",
          f"- Props removed: {', '.join(z.get('what','zone') for z in fr.get('prop_zones', [])) or 'none found'}.",
          "- Deflicker on, skin smoothing 55%, gentle contrast/clarity/sharpen (off skin and edges), warmth +1." + (f" Overrides: {C['picture']}" if C.get("picture") else "")]
    SP = C.get("split", {})
    if SP.get("segments"):
        hk = SP.get("hook") or {}
        L += ["", "## Layout (split screen = B-roll / graphics on top, you head-to-waist below; everything else full frame)", "",
              "| From | To | Top half | Note |", "|---|---|---|---|"]
        for g in SP["segments"]:
            f = g["from"] if isinstance(g["from"], dict) else {"time": g["from"]}; t = g["to"] if isinstance(g["to"], dict) else {"time": g["to"]}
            T = g["top"]; top = f"{T['media']} (from {T.get('in', 0)}s)" if T.get("media") else ("graphics: " + ", ".join(T.get("scenes", [])) if T.get("scenes") else "graphics: TODO")
            if g.get("overlay") == "hook": top += " + static hook" + (f" + pill '{hk.get('series')}'" if hk.get("series") else "")
            L.append(f"| {_t(f, ws)} | {_t(t, ws)} | {top} | {g.get('note', '')} |")
        if hk: L += ["", f"**Text hook (static, no animation):** {hk['lines'][0]} / *{hk['lines'][1]}* {hk['lines'][2]}"]
    L += ["", "## 3. Captions", "", f"Hidden until {C['captions'].get('hide_until',0):.1f}s (text hook on screen). *Italic* = big key word.", ""]
    line = []
    for ch in C["captions"]["chunks"]:
        line.append(" ".join(f"*{ws[i]['text']}*" if i == ch.get("key") else ws[i]["text"] for i in ch["w"]) + (" ~~hidden~~" if ch.get("hide") else ""))
    L.append(" · ".join(line))
    L += ["", "## 4. Scenes (motion graphics)", "", "| # | Fires on | Out | What appears | Colours | Layer |", "|---|---|---|---|---|---|"]
    for s in C["scenes"]:
        trig = s.get("in"); tw = f"'{ws[trig['word']]['text']}' " if isinstance(trig, dict) and "word" in trig else ""
        L.append(f"| {s['id']} | {tw}{_t(trig, ws)} | {_t(s.get('out'), ws) if s.get('out') else 'end'} | {SUMMARY.get(s['type'], lambda s: s['type'])(s)} | {', '.join(s.get('colors', []))} | {s.get('layer', 'front' if s['type'] in ('cards','list','icon_tiles','badge') else 'behind')} |")
    L += ["", "**Camera:** " + "; ".join(f"{_t(k['at'], ws)} → {k['to']:.2f}× ({k.get('why','push')})" for k in C["camera"])]
    S = C["sound"]; M = S["music"]
    L += ["", "## 5. Sound", "", f"- No effects before {S['quiet_until']:.1f}s. Whooshes subtle (−27 dB)" + (", only when the layout changes into a split." if S.get("whoosh") == "layout" else ".") + " Voice cleaned (rumble, hiss, de-ess, light compression).",
          f"- Music: {'on' if M['on'] else 'off'} — {M['key']} major, {M['bpm']} bpm, {M['level_db']} dB under voice, ducks {M['duck_db']} dB while you talk.",
          "- Master −14 LUFS, true peak −1.5 dBTP.", "", "| Time | Effect | Cue | dB |", "|---|---|---|---|"]
    for c in C.get("_cues_preview", []): L.append(f"| {c['t']:.2f}s | {c['sfx']} | {c['cue']} | {c['gain_db']} |")
    cv = C["cover"]
    L += ["", "## 6. Exports", "", f"- Final MP4 1080×1920 / 30 fps / H.264, BGM MP3, cover from frame {cv['frame']} (closing smile) + text hook, fitted to the 4:5 grid crop."]
    return "\n".join(L) + "\n"
