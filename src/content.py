"""
Content generation via the Anthropic API.

Asks Claude for one day's Stoic Reel: a real public-domain quote (Marcus
Aurelius / Seneca / Epictetus), a short voiceover script, an engagement
caption, and hashtags. Returns structured JSON.

Source texts (Meditations, Letters from a Stoic, Discourses/Enchiridion) are
public domain, so quoting them carries no licensing risk.
"""
import os
import json
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

MODEL = "claude-opus-4-8"

SYSTEM = """You are the content engine for a faceless Stoicism Instagram Reels \
account. Your job is to produce ONE short-form video script per call.

Rules:
- Use only genuine, public-domain Stoic material: Marcus Aurelius (Meditations), \
Seneca (Letters/essays), Epictetus (Discourses, Enchiridion). Do not fabricate quotes.
- The quote must be punchy and fit on screen in under ~25 words. Lightly modernized \
phrasing of a real passage is fine; attribute to the correct author.
- Voiceover script: 18-35 seconds spoken (~45-90 words). Open with a hook in the \
first line. Plain, grounded, masculine-neutral tone. No hashtags in the voiceover.
- Caption: 1-2 sentences that reframe the idea for daily life + one soft question \
to drive comments.
- Hashtags: 8-12, mixing broad (#stoicism #discipline) and mid-size niche tags.
- Vary the theme each day across: discipline, mortality/memento mori, control vs \
acceptance, anger, desire, resilience, time, ego.

Respond with ONLY valid JSON, no markdown, no preamble, in this exact shape:
{
  "theme": "...",
  "quote": "...",
  "author": "Marcus Aurelius | Seneca | Epictetus",
  "voiceover_text": "...",
  "caption": "...",
  "hashtags": ["#...", "..."]
}"""


def generate_content() -> dict:
    msg = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        system=SYSTEM,
        messages=[{
            "role": "user",
            "content": "Generate today's Stoic Reel. Pick a theme you haven't "
                       "likely used recently and surprise me with the angle."
        }],
    )
    raw = "".join(b.text for b in msg.content if b.type == "text").strip()
    # strip accidental fences just in case
    if raw.startswith("```"):
        raw = raw.split("```")[1].lstrip("json").strip()
    data = json.loads(raw)

    required = {"theme", "quote", "author", "voiceover_text", "caption", "hashtags"}
    missing = required - data.keys()
    if missing:
        raise ValueError(f"Claude response missing keys: {missing}")
    return data
