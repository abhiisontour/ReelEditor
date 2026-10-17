# reelkit — AbhiIsOnTour reel pipeline

Talking-head reel (green screen) → finished Instagram reel, driven by one editable file: **the edit compass**.

```
clips + script ──analyze──▶ compass.json (+ compass.md, storyboard.jpg)  ──[Abhishek reviews/edits]──▶  build ──▶ final MP4 + cover + BGM MP3
```

## Setup (once per machine/session, ~3–5 min)
```bash
./setup.sh                      # pip + npm deps, Parakeet/Whisper models from GitHub releases (no Hugging Face)
export REELKIT_MODELS=~/.cache/reelkit/models   # default
```
Needs ffmpeg, Python 3.10+, Node 18+, a Chromium headless shell (auto-found under /opt/pw-browsers or set `REELKIT_CHROME`).

## Use
```bash
P=~/reels/day01 ; mkdir -p $P/input            # put clips (*.mp4/*.mov) + script.txt in $P/input
python -m reelkit.run analyze    $P --name AbhiIsOnTour_Day01 --hook "You can send me|negative|comments if…" --day 1
#   -> edit list (false starts, long pauses), script-aligned words, matte, framing, picture, caption draft, hook/badge
#   -> then design scenes/camera/captions in compass.json (see docs/compass.md)
python -m reelkit.run storyboard $P             # ~30 s: stills of every scene + compass.md for review
python -m reelkit.run build      $P             # full render (re-runs only stages whose compass sections changed)
```
Outputs in `$P/renders/`: `final_<name>.mp4` (1080×1920, 30 fps, H.264, −14 LUFS, TP −1.5), `cover_<name>.jpg`, `bgm_<name>.mp3`; QC in `$P/qc/`.

## Stages (all cached by a hash of the compass sections they read)
| Stage | Module | Reads | Writes |
|---|---|---|---|
| ingest + ASR + script alignment + cut detection | `transcribe.py` | input/ | work/words_raw.json, analysis.json |
| edit list | `transcribe.apply_edit` | compass.edit | work/base.mov, words.json |
| key + matte + face track | `cutout.py` | compass.key, framing.table_line | layers/matte_raw.mkv, fg_raw.mkv |
| props, deflicker, skin, grade | `cutout.enhance` | compass.picture, framing.prop_zones | layers/matte.mkv, fg.mkv |
| captions layer | `captions.py` + `web/captions.html` | compass.captions | layers/captions/ |
| motion layers | `web/motion.html` (scene library) | compass.scenes | layers/behind/, layers/front/ |
| composite | `comp.py` | compass.framing, camera, look | layers/picture.mp4 |
| sound + master + export + cover | `sound.py`, `run.cover` | compass.sound, cover | renders/ |

## Scene library (`compass.scenes[].type`)
Talking-head: `text_hook`, `big_word`, `bubbles`, `route`, `streak_grid`, `calendar`, `cards`, `list`, `icon_tiles` (objects: `coin`, `clock`, `calm`, or any icon as a glossy 3D chip), `stat` (count-up), `badge`, `cta`.
Stage (full-screen, you shrink into a corner circle): `screen` (screen recordings / screenshots with zooms, highlight boxes, taps), `bars`, `steps`, `compare`, `title_card`.
Script markup `[TALK]`, `[DEMO: note | file]`, `[ANIMATION: note]` marks these segments; demo media goes in `input/media/`.
Icons: wrench bolt check x star heart pin plane wallet camera ticket train bed food clock calendar bag map phone sun rupee.
Full field reference: [docs/compass.md](docs/compass.md).
