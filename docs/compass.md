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

## Script markup
```
[TALK] Planning a trip and not sure about the weather?
[DEMO: open weatherspark, search Munnar | weatherspark1.mp4] Open weatherspark and search Munnar…
[ANIMATION: rainfall rising June to August] Rain peaks in July…
[TALK] Follow for tomorrow's tool.
```
Tags are stripped before alignment; each tagged span becomes a scene stub (`screen` for DEMO, `title_card` with `todo` for ANIMATION) on the right words. Demo media goes in `input/media/` (the talking-head clips stay directly in `input/`).

Graphics live in the space above the head (y ≈ 230–610); captions live on the chest (y 1180–1540); nothing in the top 220 / bottom 380 / right 140 px.
