---
name: abhi-reel-editor
description: Edits an AbhiIsOnTour talking-head reel from uploaded clips + script with the reelkit pipeline: one edit-compass approval, then fully automatic render. Use on /abhi-reel-editor.
---

# AbhiIsOnTour Reel Editor (reelkit)

Abhishek uploads raw talking-head clips (lime green screen, desk) + the reel's script and types `/abhi-reel-editor`. You produce the finished reel with the **reelkit** pipeline. There is exactly **one approval**: the **edit compass**. After he approves it (with or without changes), you run everything automatically and deliver.

Working style: compact tables and short bullets, never long prose. Plain language (he's a creator, not an engineer). Send files with SendUserFile.

## 0. Setup (every session)
```bash
REPO=abhiisontour/ReelEditor
cd ~ && (test -d reelkit || git clone https://github.com/$REPO.git reelkit) && cd reelkit && git pull -q && ./setup.sh
```
If the clone fails, use add_repo for the repo (read access) and retry. If GitHub is unreachable, ask him to upload `reelkit.zip` and unzip it to `~/reelkit`.
Make the project: `P=~/reels/<DayNN>`; copy talking-head clips to `$P/input/` and any screen recordings / screenshots to `$P/input/media/`; write the script to `$P/input/script.txt` (convert .docx/.pdf/pasted text to plain text; keep his exact wording and punctuation, since the script is the ground truth for captions). If clip order isn't obvious from filenames, write `$P/input/clip_order.json`.

Ask only for what's missing, in ONE AskUserQuestion: **text hook** for 0–3 s (offer 2–3 options built from the script's first line; format `line1|KEY|line3`), **day number**, clip order if ambiguous, and **any screen recording a `[DEMO: … | file]` tag names that wasn't uploaded** (he records; you never fake a website's interface).

## 1. Analyze (≈12 min, run in background and poll with an until-loop)
```bash
cd ~/reelkit && python3 -m reelkit.run analyze $P --name AbhiIsOnTour_DayNN --hook "line1|key|line3" --day NN
```
It ingests and normalises the clips, transcribes (Parakeet + Whisper), aligns to the script, proposes cuts (false starts, restarts, long pauses), keys the green screen, auto-frames (1.42×, centred, desk just below hands), enhances (deflicker, skin, grade), drafts captions, hook, badge and cover.

## 2. Design the edit (you, in compass.json; see ~/reelkit/docs/compass.md)
Read `$P/words.json`, `$P/work/analysis.json`, `$P/compass.json`. Then:
1. **Cuts**: sanity-check every suggested cut against the transcript; flag anything that removes real content.
2. **Props**: look at `framing.prop_candidates`. For any persistent light blob beside the arms near the desk (chairs, bags), view a crop of `$P/work/base.mov` there; if it's a prop, add a `prop_zones` entry `{x0,x1,y0,what}`. The watch is NOT a prop.
3. **Captions**: fix the draft chunks (1–3 words, natural phrases, never end on "a/the/to/your"). One key word per sentence: the emotional or number word. Hide the chunk that a scene shows big (e.g. the CTA word).
4. **Scenes**: one idea per scene, each fired on its word, using the library (text_hook, big_word, bubbles, route, streak_grid, calendar, cards, list, icon_tiles, stat, badge, cta). Rules:
   - The first 3 s belong to the text hook. Then one scene per idea, with gaps where his face carries it.
   - Show concepts as colourful icon chips or glossy 3D-style objects (coin = money, clock = time, calm = stress, wrench = tool, bolt = hack, plane/pin = travel, calendar = dates, grid = streaks). **No emoji, no fake app UI (tickets, comment boxes).**
   - Palette "golden hour to blue hour"; 2–3 neighbouring colours per scene.
   - End with a `cta` (next-day word + FOLLOW pill, tap on the last words).
5. **Demo & animation segments** (script tags `[DEMO: note | file]`, `[ANIMATION: note]` → stub scenes on the right words):
   - `screen`: run `python3 -m reelkit.run media-sheet $P --name <file>` and look at the sheet. Set `media_in`/`speed` so the recording's action lines up with his words; add `zooms` (rect on what he names, then back to `[0,0,1,1]`), `highlights` on the button/field he mentions, `taps` where he clicks; `url` = the site's address, `label` short (e.g. "Live demo"). Landscape = browser frame, portrait = phone frame.
   - ANIMATION stubs (`title_card` with `todo`): replace with `bars` (numbers over time, e.g. rainfall by month; use real numbers from the script or research, never invented), `steps` (how-to), `compare` (A vs B) or `title_card`. Remove the `todo` key.
   - During stage scenes he shrinks into a circle top-left automatically; keep talking-head scenes out of those windows.
6. **Camera**: keep the opening settle; push 1.05 on the hook word and back; **a 1.04 snap with dur 0 at every jump-cut time** (`words.json.cut_frames`/30); push 1.05 on the CTA.
7. **Cover**: open `$P/qc/closing_faces.jpg` and set `cover.frame` to the best closing smile (eyes open, looking at camera).
8. Sound: keep defaults (no SFX before 3 s, subtle whooshes, chime on the last word, music ducked). Only add `remove`/`extra_cues` if the script needs it.

Then: `python3 -m reelkit.run storyboard $P` (≈30 s). **Look at `$P/qc/storyboard.jpg` yourself** (overlaps, text on the face, safe area, readability) and fix compass.json before sending.

## 3. The one approval: send the edit compass
Send `$P/compass.md` and `$P/qc/storyboard.jpg`, with a 3-line message: what the reel will look like, the 2–3 choices most worth his attention, and "Edit the compass (or just reply with changes). Say **go** when happy." **Wait for his reply. This is the only stop.**

## 4. Auto mode (after his reply)
1. Apply every change he made (to compass.md or in chat) into compass.json. If he only says go/ok, change nothing.
2. `python3 -m reelkit.run build $P` in the background (≈12–15 min; only stages whose compass sections changed re-run). Poll with an until-loop on `BUILD DONE|Traceback`.
3. QC without asking him: view `$P/qc/final_sheet.jpg`, a full-res cover crop, and `$P/work/loudness.json` (must be −14 ±0.5 LUFS, TP ≤ −1.0). Check: no text on face, nothing in the safe-area margins, no rims or holes on the cut-out, no props visible. Fix in compass.json and rebuild if needed.
4. Deliver: `final_<name>.mp4`, `cover_<name>.jpg`, `bgm_<name>.mp3` from `$P/renders/`, plus a 4-line summary (length, cuts made, scenes, loudness).

Later tweaks ("make the whoosh quieter", "change key word"): edit compass.json and run `build` again; only the affected stages re-render.

## His standing preferences (already defaults in reelkit, don't regress them)
- Canvas 1080×1920, 30 fps; safe area top 220 / bottom 380 / right 140. Max 2 fonts: Instrument Serif Italic (key words), Inter SemiBold (everything else; labels uppercase and tracked).
- Background near-black #09090A with a warm glow. Framing 1.42×, centred, only a thin strip of desk, no legs, no chair.
- Clean edges: no outline, no glow, no green or olive fringe. Natural skin smoothing; deflicker on.
- Captions 1–3 words, word by word, min 0.4 s, never over the face, hidden during the text hook.
- Motion: fast in (0.2–0.35 s), hold, clean out; one idea at a time; push-ins ≤ 6%.
- Sound: **no SFX in the opening seconds**, whooshes subtle, voice always on top, music −21 dB with −6 dB ducking, master −14 LUFS / TP −1.5.
- Deliverables: final MP4, cover (closing smile + text hook, 4:5-crop safe), BGM MP3.
