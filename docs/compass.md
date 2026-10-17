# compass.json reference

Timing specs everywhere: `{"word": <index in words.json>}` (fires on that word's start, optional `"offset"`), `{"time": seconds}` (edited timeline), or `null` (end of reel).
Colours: palette keys `sun peach coral rose lilac sky mint` or any hex.

```jsonc
{
 "name": "AbhiIsOnTour_Day01",
 "palette": {"sun":"#FBBF24","peach":"#FF8A5B","coral":"#FF5D73","rose":"#F472B6","lilac":"#A78BFA","sky":"#60A5FA","mint":"#34D399"},
 "edit": {
   "cuts": [{"from": 10.87, "to": 12.03, "why": "false start", "apply": true}],   // SOURCE times, frame-snapped
   "text_fixes": {"41": "PM."},          // word index (raw) -> display text
   "drop_extra_words": true               // drop ASR words that aren't in the script (ums, restarts)
 },
 "framing": {"scale": 1.42, "x0": 228.7, "y0": 45.9, "table_line": [[47,1272],[1032,1304]],
             "prop_zones": [{"x0": 335, "x1": 430, "y0": 1205, "what": "white chair back (left arm gap)"}]},
 "key": {"ratio_lo": 0.18, "ratio_hi": 0.62},                // only if the key needs tuning
 "picture": {"skin_amount": 0.55, "contrast": 0.10, "clarity": 0.22, "sharpen": 0.45, "saturation": 1.04},
 "look": {"glow": 0.16, "opening_bloom": 0.6},
 "captions": {"hide_until": 3.0, "style": {"small_px": 58},
   "chunks": [{"w": [10, 11], "key": 10, "grad": null, "hide": false, "hide_key": false}]},
 "scenes": [ ...see below... ],
 "camera": [{"at": {"time": 0}, "to": 1.06, "dur": 0}, {"at": {"time": 0}, "to": 1.0, "dur": 0.6},
            {"at": {"word": 10}, "to": 1.05, "dur": 0.3}, {"at": {"time": 10.8}, "to": 1.04, "dur": 0, "why": "snap on cut"}],
 "sound": {"quiet_until": 3.0, "music": {"on": true, "key": "D", "bpm": 100, "level_db": -21, "duck_db": -6},
           "remove": ["plane"], "extra_cues": [{"t": 5.2, "sfx": "tap", "cue": "…", "gain_db": -20}], "sfx_trim_db": {"whoosh": -3},
           "chime_at": {"word": 66}, "voice": {"highpass": 80, "denoise_nr": 12}},
 "cover": {"frame": 579, "text_frame": null, "text_dy": 52, "subject_dy": 48}
}
```

## Scenes
Every scene: `id`, `type`, `in`, `out`, `colors`, optional `layer` (`behind` = behind the head, `front` = over the subject but never on the face), optional `handoff` (fade after `out`), optional `parts` (named timing specs).

| type | fields | parts | default layer |
|---|---|---|---|
| `text_hook` | `lines` [2–3], `key_line`, `tops`, `key_px` | `slam`, `rest`, `said` (pulse when spoken) | behind |
| `big_word` | `text`, `top`, `px` | — | behind |
| `bubbles` | colours ×4 | — | behind |
| `route` | `label` | — | behind |
| `streak_grid` | `label_first`, `label_full`, `cols`, `rows`, `count` | `grid` | behind |
| `calendar` | `label`, `month`, `day`, `time` | `day`, `month`, `time` | behind |
| `cards` | `label`, `items[{title, icon, color, at}]` (1–3) | — | front |
| `list` | `label`, `items[{title, icon, color, at}]` (≤4) | — | front |
| `icon_tiles` | `label`, `items[{title, object: coin/clock/calm/<icon>, color, at, symbol}]` (1–3) | — | front |
| `stat` | `value`, `from`, `prefix`, `suffix`, `label`, `px` | — | behind |
| `badge` | `text`, `sub` | — | front |
| `cta` | `word`, `button`, `top`, `px` | `tap` | both |

### Stage scenes (full-screen; the talking head shrinks into a circle top-left, 0.35 s transitions, whoosh in/out)
| type | fields |
|---|---|
| `screen` | `media` (file in `input/media/`, video or image), or `slides:[{file, at}]` for screenshots; `device` auto/browser/phone; `url` (shown in the browser bar); `label`; `media_in` (s into the recording), `speed`; `zooms:[{at, rect:[x,y,w,h] 0–1 of the media, dur}]` (rect `[0,0,1,1]` = zoom back out); `highlights:[{at, until, rect, color}]`; `taps:[{at, x, y}]` |
| `bars` | `title`, `unit`, `bars:[{label, value, color, at, highlight}]`, `highlight` (index) |
| `steps` | `title`, `steps:[{text, icon, color, at}]` (≤4) |
| `compare` | `left/right: {title, items[], icon, at}` |
| `title_card` | `text`, `sub`, `px` |
Use `python -m reelkit.run media-sheet <project> --name <file>` to get a timestamped contact sheet with a 10% grid, and read zoom/highlight rects off it. Captions are hidden during portrait (phone) demos unless `captions.show_during_demo` is true.

## Split screen (series format)
B-roll or graphics in the top half (y 0–960), you head-to-waist in the bottom half (scale 0.72, desk faded under your hands), hard cuts.
```jsonc
"split": {
  "layout": {"scale": 0.72, "head_y": 1010, "seam": 960, "desk_fade_y": 1335},          // optional overrides
  "hook": {"lines": ["You can send me", "negative", "comments if…"], "series": "Day 00/75 · Of making your travel easy",
           "colors": ["peach", "coral", "rose"]},                                         // static overlay, no animation
  "segments": [
    {"from": {"time": 0}, "to": {"time": 3.5}, "overlay": "hook",
     "top": {"media": "01_comments.mp4", "in": 1.1, "crop": [20, 600, 980, 871]}},     // crop = source x,y,w,h (optional; default = fill)
    {"from": {"time": 3.5}, "to": {"time": 7.6}, "top": {"media": "03_drive.mp4", "in": 5.8}},
    {"from": {"time": 13.2}, "to": {"time": 18.25}, "top": {"scenes": ["TOOLS", "SAVE"], "zoom": 1.15}}  // graphics: scene layers scaled into the top half
  ]}
```
Rules:
- The **opener** segment (0–3.5 s, `overlay: "hook"`) carries the static hook on the seam and the series pill at the top; captions and SFX start at 3.5 s (`captions.hide_until`, `sound.quiet_until`). No `text_hook` scene and no badge when the opener is split.
- **Back-to-back segments keep you in exactly the same place**: only the top half changes at the cut. Never put a full-frame moment shorter than ~2 s between two splits; extend the split instead.
- Captions sit on the seam during splits (auto-moved) and on the chest during full frame.
- Graphics tops use normal scenes (`icon_tiles`, `cards`, `list`…) named in `top.scenes`; they render on the usual layer and get scaled (`zoom`, default 1.15) into the top half.
- `sound.whoosh: "layout"`: whoosh only when cutting from full frame into a split (plus stage scenes); no per-scene or snap whooshes.
- The cover becomes the opener's split look (opener B-roll + hook) with the `cover.frame` smile below.

## Script markup
```
[TALK] Planning a trip and not sure about the weather?
[DEMO: open weatherspark, search Munnar | weatherspark1.mp4] Open weatherspark and search Munnar…
[ANIMATION: rainfall rising June to August] Rain peaks in July…
[TALK] Follow for tomorrow's tool.
```
Split-screen tags: `[BROLL: note | file.mp4 | in=5.8]` (B-roll on top from 5.8 s into the clip) and `[SPLIT: note]` (graphics on top; design the scenes and list them in `top.scenes`). A BROLL/SPLIT span starting at the first word becomes the series opener (hook overlay for 0–3.5 s; the same clip continues after it, or the next span takes over at 3.5 s if it starts within a second).
Tags are stripped before alignment; each tagged span becomes a scene stub (`screen` for DEMO, `title_card` with `todo` for ANIMATION) on the right words. Demo media goes in `input/media/` (the talking-head clips stay directly in `input/`).

Graphics live in the space above the head (y ≈ 230–610); captions live on the chest (y 1180–1540); nothing in the top 220 / bottom 380 / right 140 px.
