---
name: "abhi-reel-editor"
description: "Edits an AbhiIsOnTour reel (talking head + split-screen B-roll, screen demos/animations) from uploaded clips + script via the reelkit repo: one edit-compass approval, then auto render. Use on /abhi-reel-editor."
---

# AbhiIsOnTour Reel Editor (reelkit)

Abhishek uploads raw talking-head clips (lime green screen, desk), B-roll clips (his own or made in Google Flow), any screen recordings/screenshots for demo parts, and the reel's script, then types `/abhi-reel-editor`. You produce the finished reel with the **reelkit** pipeline (repo `abhiisontour/ReelEditor`). There is exactly **one approval**: the **edit compass**. After he approves it (with or without changes), you run everything automatically and deliver.

Working style: compact tables and short bullets, never long prose. Plain language (he's a creator, not an engineer). Send files with SendUserFile.

## 0. Setup (every session)
Attach the repo with add_repo (owner `abhiisontour`, repo `ReelEditor`, read access), then:
```bash
REPO=abhiisontour/ReelEditor
cd ~ && (test -d reelkit || git clone --depth 1 https://github.com/$REPO.git reelkit) && cd reelkit && git pull -q && ./setup.sh
```
If GitHub is unreachable, ask him to upload `reelkit.zip` and unzip it to `~/reelkit`.
Make the project: `P=~/reels/<DayNN>`; copy talking-head clips to `$P/input/`, and B-roll, screen recordings and screenshots to `$P/input/media/`; write the script to `$P/input/script.txt` (convert .docx/.pdf/pasted text to plain text; keep his exact wording and punctuation, since the script is the ground truth for captions). If clip order isn't obvious from filenames, write `$P/input/clip_order.json`.

**Mark up the script** (if he didn't): `[BROLL: note | file.mp4 | in=s]` where a B-roll clip carries the idea, `[SPLIT: note]` where graphics should carry it in the top half, `[DEMO: note | file]` for screen recordings, `[ANIMATION: note]` for explainers, `[TALK]` back to full-frame him. Look at each B-roll first (contact sheet with ffmpeg) to pick `in=` (skip phone UI chrome, Control Centre swipes, watermarks).

Ask only for what's missing, in ONE AskUserQuestion: **text hook** (offer 2–3 options built from the script's first line; format `line1|KEY|line3`), **day number**, clip order if ambiguous, the **opener B-roll** if none was uploaded, and **any screen recording a `[DEMO: … | file]` tag names that wasn't uploaded** (he records demos; never recreate a real website's interface).

## Series format ("Day x/75 : Of Making Your Travel Easy") — every reel
- **Split screen** like his reference: B-roll or graphics in the top half (0–960), him head-to-waist in the bottom half with hands visible (scale 0.72, desk faded under the hands), hard cuts.
- **Opener 0–3.5 s**: B-roll in the top half from frame 0 (the visual hook: real motion, e.g. comments scrolling), **static** 2-line text hook on the seam (no animation at all), series pill "DAY NN/75 · OF MAKING YOUR TRAVEL EASY" at the top. No captions, no SFX, no other graphics until 3.5 s.
- **Rhythm**: split while a clip/graphic carries the idea, full frame while his face carries it. Back-to-back splits keep him in exactly the same place (only the top half cuts). **Never a full-frame moment shorter than ~2 s between two splits**; extend the split instead (a 0.6 s split→full→split flash is too quick for the eye).
- Missing B-roll → graphics top (`icon_tiles`/`cards` 3D chips, or `month_hunt` for best-time/which-month reels) and say so in the compass.

## 1. Analyze (≈12 min, run in background and poll with an until-loop)
```bash
cd ~/reelkit && python3 -m reelkit.run analyze $P --name AbhiIsOnTour_DayNN --hook "line1|key|line3" --day NN
```
It ingests and normalises the clips, transcribes (Parakeet + Whisper), aligns to the script, proposes cuts (false starts, restarts, long pauses), keys the green screen, auto-frames (1.42×, centred, desk just below hands), enhances (deflicker, skin, grade), drafts captions and cover, builds `compass.split` from BROLL/SPLIT tags (a span on the first word becomes the opener with hook + series pill), and stub scenes for every DEMO/ANIMATION tag.

## 2. Design the edit (you, in compass.json; see ~/reelkit/docs/compass.md)
Read `$P/words.json`, `$P/work/analysis.json`, `$P/compass.json`. Then:
1. **Cuts**: sanity-check every suggested cut against the transcript; flag anything that removes real content.
2. **Props**: look at `framing.prop_candidates`. For any persistent light blob beside the arms near the desk (chairs, bags), view a crop of `$P/work/base.mov` there; if it's a prop, add a `prop_zones` entry `{x0,x1,y0,what}`. The watch is NOT a prop.
3. **Layout (`compass.split`)**: check every segment boundary sits in a pause; opener ends at 3.5 s; apply the rhythm rule above. For phone recordings set `top.crop` (source x,y,w,h) to drop the status bar. `[SPLIT]` segments: create the graphics scenes (fire on their words) and list their ids in `top.scenes` (they're scaled into the top half; `zoom` default 1.15).
4. **Captions**: fix the draft chunks (1–3 words, natural phrases, never end on "a/the/to/your"). One key word per sentence: the emotional or number word. Hide the chunk that a scene shows big (e.g. the CTA word). They sit on the seam during splits automatically.
5. **Full-frame scenes**: one idea per scene, each fired on its word, using the library (big_word, bubbles, route, streak_grid, calendar, cards, list, icon_tiles, stat, cta). Rules:
   - Show concepts as colourful icon chips or glossy 3D-style objects (coin = money, clock = time, calm = stress, wrench = tool, bolt = hack, plane/pin = travel, calendar = dates, grid = streaks). **No emoji, no fake app UI (tickets, comment boxes).**
   - Palette "golden hour to blue hour"; 2–3 neighbouring colours per scene.
   - End full frame with a `cta` (next-day word + FOLLOW pill, tap on the last words).
6. **Demo & animation segments** (stage scenes; he shrinks into a circle top-left automatically, with whooshes in and out):
   - `screen`: run `python3 -m reelkit.run media-sheet $P --name <file>` and look at the sheet. Set `media_in`/`speed` so the recording's action lines up with his words; add `zooms` (rect on what he names, then back to `[0,0,1,1]`), `highlights` on the button/field he mentions, `taps` where he clicks; `url` = the site's address, `label` short (e.g. "Live demo"). Landscape = browser frame, portrait = phone frame (captions hide during phone demos).
   - ANIMATION stubs (`title_card` with `todo`): replace with `bars` (numbers over time; real numbers from the script or research, never invented), `steps` (how-to), `compare` (A vs B) or `title_card`. Remove the `todo` key.
   - Keep talking-head scenes out of stage windows.
   - **Voice-over demos** (he recorded only audio for the demo; the talking-head clip is just the hook): make a clip from the audio over a still of his last frame (`02_voiceover.mp4`), speed it to match the hook clip (`atempo`), and set `pip: false` + `frame_h: 780` on the screen scenes. Split the recording into one `screen` scene per spoken step (own `media_in`/`speed`, a zoom + highlight on what he names), and skip ads and dead time.
7. **Camera** (full-frame parts only): a dur-0 key back to 1.0 where a split hands over to full frame; push 1.05 on a number/key word; **a snap with dur 0 at every jump-cut time** (`words.json.cut_frames`/30); push 1.05 on the CTA.
8. **Cover**: open `$P/qc/closing_faces.jpg` and set `cover.frame` to the best closing smile (eyes open, looking at camera). With a split opener the cover is the opener's look (B-roll + hook) with that smile below.
9. Sound: keep defaults (`whoosh: "layout"` = a whoosh only when cutting from full frame into a split; nothing before 3.5 s; themed sounds on icon objects; chime on the last word; music ducked). Only add `remove`/`extra_cues` if the script needs it.

Then: `python3 -m reelkit.run storyboard $P` (≈30 s). **Look at `$P/qc/storyboard.jpg` yourself** (overlaps, text on the face, safe area, readability, hook legible over the B-roll, demo zooms on the right thing) and fix compass.json before sending.

## 3. The one approval: send the edit compass
Send `$P/compass.md` and `$P/qc/storyboard.jpg`, with a 3-line message: what the reel will look like, the 2–3 choices most worth his attention (incl. any clip still missing + its fallback), and "Edit the compass (or just reply with changes). Say **go** when happy." **Wait for his reply. This is the only stop.**

## 4. Auto mode (after his reply)
1. Apply every change he made (to compass.md or in chat) into compass.json. If he only says go/ok, change nothing.
2. `python3 -m reelkit.run build $P` in the background (≈12–15 min; only stages whose compass sections changed re-run). Poll with an until-loop on `BUILD DONE|Traceback`.
3. QC without asking him: view `$P/qc/final_sheet.jpg`, frames either side of every split boundary (he must not move at split→split cuts), a full-res cover crop, and `$P/work/loudness.json` (must be −14 ±0.5 LUFS, TP ≤ −1.0). Check: no text on face, nothing in the safe-area margins, hook/captions readable on the seam, no rims or holes on the cut-out, no props visible, demo zooms/highlights land on the right element. Fix in compass.json and rebuild if needed.
4. Deliver: `final_<name>.mp4`, `cover_<name>.jpg`, `bgm_<name>.mp3` from `$P/renders/`, plus a 4-line summary (length, cuts made, layout/scenes, loudness).

Later tweaks ("make the whoosh quieter", "change key word"): edit compass.json and run `build` again; only the affected stages re-render. If you fix a bug in reelkit itself, commit it to the repo so the next reel gets it.

## His standing preferences (already defaults in reelkit, don't regress them)
- Canvas 1080×1920, 30 fps; safe area top 220 / bottom 380 / right 140. Max 2 fonts: Instrument Serif Italic (key words), Inter SemiBold (everything else; labels uppercase and tracked).
- Background near-black #09090A with a warm glow. Full framing 1.42×, centred, only a thin strip of desk, no legs, no chair. Split framing 0.72× head-to-waist, hands visible.
- Clean edges: no outline, no glow, no green or olive fringe. Natural skin smoothing; deflicker on.
- Text hook static (no animation), 0–3.5 s, on the seam; series pill at the top.
- Captions 1–3 words, word by word, min 0.4 s, never over the face, hidden during the text hook.
- Motion: fast in (0.2–0.35 s), hold, clean out; one idea at a time; push-ins ≤ 6%.
- Sound: **no SFX in the opening 3.5 s**, few and subtle whooshes, voice always on top, music −21 dB with −6 dB ducking, master −14 LUFS / TP −1.5.
- Deliverables: final MP4, cover (closing smile + text hook, 4:5-crop safe), BGM MP3.
