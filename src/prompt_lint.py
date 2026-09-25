"""
Free pre-flight check for storyboard shot prompts — runs BEFORE any paid call.

Owner, 2026-09-25: "Check for weird ai video bugs like double hands, writing
properly and make sure all videos we create are improved by making better
prompts before using tokens on higgsfield api."

Every rule here comes from a failure seen in our own generated footage
(reviewed frame by frame at four moments per shot, 2026-09-25) or from a
limit in the model docs — not from a generic list:

  still       "stays completely still" -> Kling returned a near-frozen clip
              that reads as a photograph (before_breakfast shots 1-2)
  text        any request for legible writing — ledgers, notes, signs, pages.
              Image/video models garble letters; a misspelt word on screen
              reads as cheap instantly.
  mirror      "seen in the mirror" was silently dropped (before_breakfast 6);
              reflections are a known failure
  merge       two held objects in one hand fused (a candle growing out of the
              top of a walking stick, earthenware 3)
  anachronism a glass lantern in ancient Rome (earthenware 6)
  crowd       every extra face and pair of hands is another chance of extra
              fingers or a melted face
  fine hands  writing, typing, lacing, tying — the close-up finger work where
              extra and fused fingers appear
  cost        a Kling shot over 5.5s is billed as a 10s clip — double

Two levels:
  ERROR — the shot must be rewritten; CI fails on it, and at runtime the shot
          is not paid for and falls back to stock.
  WARN  — allowed, but the generator hardens the prompt (see harden()).
"""
from __future__ import annotations

import re

# Things that did not exist in the ancient world and that models love to add.
# Seen in AIRED posts (Higgsfield scene analysis, 2026-09-25): a "bronze stylus
# on a wax tablet" came out as an ornate FOUNTAIN PEN; Seneca wrote in a
# NOTEBOOK and a LEATHER-BOUND JOURNAL in front of a CHALKBOARD.
ANACHRONISMS = ["lantern", "glass lantern", "clock", "wristwatch", "glasses",
                "spectacles", "zipper", "button-up", "paper cup", "light bulb",
                "electric", "phone", "screen", "plastic", "fountain pen", "pen",
                "notebook", "journal", "bound book", "book", "chalkboard", "paper"]
# Words that mark a shot as set in antiquity.
ANCIENT = ["roman", "rome", "greek", "athens", "ancient", "toga", "tunic",
           "emperor", "senator", "philosopher", "legion", "villa", "stoa"]

TEXT_ASK = r"\b(writ(e|es|ing|ten)|letters?|lettering|sign(s|board)?|note(s|book)?|" \
           r"ledger|page|newspaper|book cover|label|caption|handwriting|words?|" \
           r"figures in|columns of|headline|poster|menu)\b"
TEXT_SAFE = r"\b(blank|unreadable|illegible|out of focus|blurred|no text|not readable|" \
            r"too small to read)\b"

STILL = r"\b(completely still|does not move|doesn'?t move|not moving|motionless|" \
        r"stays still|frozen)\b"
CAMERA_MOVE = r"\b(push|pull|dolly|pan|tilt|drift|track|orbit|crane|handheld|" \
              r"zoom|creep|glide)\b"

MIRROR = r"\b(mirror|reflection|reflected)\b"
FINE_HANDS = r"\b(writ(e|es|ing)|typ(e|es|ing)|lac(e|es|ing)|ty(ing|es)|" \
             r"counting|knit|sew|button|playing (a|the) (piano|guitar))\b"
CROWD = r"\b(crowd|group of|students|soldiers|people|colleagues|audience|" \
        r"men\b|several|many)\b"
HELD = r"\b(holding|holds|clutching|carrying|gripping|leaning on)\b"


def _has(pattern: str, text: str) -> bool:
    return re.search(pattern, text, re.I) is not None


def check_shot(spec: dict, cast: dict | None = None) -> list[tuple[str, str]]:
    """[(level, message)] for one shot. level is 'ERROR' or 'WARN'."""
    cast = cast or {}
    pic = spec.get("picture", "")
    motion = spec.get("motion", "")
    who = cast.get(spec.get("who"), {}).get("look", "") if spec.get("who") else ""
    full = f"{who} {pic}"
    out = []

    if _has(TEXT_ASK, full) and not _has(TEXT_SAFE, full):
        out.append(("ERROR", "asks for visible writing/text — models garble "
                    "letters; show the object face-down, from behind, or blurred"))
    if _has(MIRROR, full):
        out.append(("ERROR", "mirror/reflection — the reflection is dropped or "
                    "warped; shoot the person directly"))
    if spec.get("model") == "kling":
        if _has(STILL, motion) and not _has(CAMERA_MOVE, motion):
            out.append(("ERROR", "motion asks for stillness with no camera move — "
                        "Kling returns a near-frozen clip; add a slow push/drift"))
        if not motion.strip():
            out.append(("ERROR", "kling shot has no motion line"))
        if float(spec.get("seconds", 0)) > 5.5:
            out.append(("ERROR", f"{spec['seconds']}s kling shot bills as a 10s "
                        "clip (double cost) — keep kling shots <= 5.5s, give "
                        "long holds to wan"))
    if spec.get("model") == "kling" and resolves_without_a_face(spec):
        out.append(("ERROR", "resolution shot with no facial expression named — "
                    "body language alone aired as distress; say what the face does"))
    ancient = _has(r"\b(" + "|".join(ANCIENT) + r")\b", full)
    if ancient:
        hits = [a for a in ANACHRONISMS if re.search(r"\b" + re.escape(a) + r"\b", full, re.I)]
        if hits:
            out.append(("ERROR", f"anachronism in an ancient shot: {', '.join(hits)}"))
    held = len(re.findall(HELD, full, re.I))
    if held >= 2 or (held and re.search(r"\b(and|while)\b.*\b(stick|staff|cane|candle|lamp|cup)\b", pic, re.I)
                     and re.search(r"\b(stick|staff|cane)\b", full, re.I)
                     and re.search(r"\b(candle|lamp|cup)\b", full, re.I)):
        out.append(("WARN", "two held objects — they tend to fuse in one hand; "
                    "give each hand one thing, or drop one"))
    if _has(FINE_HANDS, f"{pic} {motion}"):
        out.append(("WARN", "fine finger work — extra/fused fingers risk; frame "
                    "the hands partly out of shot or at a distance"))
    if _has(CROWD, pic):
        out.append(("WARN", "several people — more faces and hands to go wrong; "
                    "keep them distant, from behind, or out of focus"))
    return out


def check_board(board: dict) -> list[tuple[int, str, str]]:
    """[(shot_number, level, message)] for a whole storyboard."""
    res = []
    for i, s in enumerate(board.get("shots", []), 1):
        for level, msg in check_shot(s, board.get("cast", {})):
            res.append((i, level, msg))
    return res


# Appended to every image/video prompt. Positive phrasing (the models have no
# reliable "not"), aimed at the failures above.
SAFE_POSITIVE = ("anatomically correct hands with five fingers each, one object "
                 "per hand, natural proportions, one consistent face, no visible "
                 "lettering anywhere")

# Kling 2.5 accepts a negative_prompt (per its model docs). Wan and Soul do not.
KLING_NEGATIVE = ("extra fingers, missing fingers, fused fingers, extra hands, extra "
                  "arms, extra limbs, deformed hands, mutated hands, two heads, "
                  "duplicate person, distorted face, melting face, morphing, "
                  "flickering, text, letters, words, subtitles, watermark, logo, "
                  "smoke artifacts, glitch, frozen frame")


def harden_motion(motion: str) -> str:
    """Every Kling shot gets visible movement: a stillness request without a
    camera move produced a frozen clip."""
    motion = (motion or "").strip() or "subtle natural movement"
    if not _has(CAMERA_MOVE, motion):
        motion += ", slow gentle camera push in"
    return motion


# Ancient shots: models fill Roman rooms with glass lanterns and modern
# fittings unless the period is stated as physical objects (seen: a glass
# lantern in earthenware 6 even though the prompt said "iron oil lamp").
ERA_GUARD = ("strictly period-accurate ancient Roman world: writing only with a "
             "bronze stylus on a wax tablet or a reed on a papyrus scroll, light "
             "only from clay or bronze oil lamps and candles, rough wool and linen "
             "clothing, stone, plaster and wood")


def is_ancient(text: str) -> bool:
    return _has(r"\b(" + "|".join(ANCIENT) + r")\b", text)


# EMOTION MUST BE NAMED ON THE FACE. before_breakfast's last shot asked for
# "shoulders relaxed, he exhales and lies back" (relief) and aired as
# "distressed, head in hands, arm over his eyes" — the opposite of the lesson.
# Body language alone is read ambiguously; a closing or resolving beat must say
# what the face does.
EMOTION_WORDS = r"\b(smil|relie|calm|content|peaceful|amused|laugh|grin|serene|" \
                r"settled|at ease|light(er)? expression|small nod)"


def resolves_without_a_face(spec: dict) -> bool:
    """A kling shot marked as the emotional resolution but with no facial cue."""
    text = f"{spec.get('picture', '')} {spec.get('motion', '')}"
    return bool(spec.get("resolve")) and not _has(EMOTION_WORDS, text)
