"""The TikTok caption (owner 2026-11-13: "Post every Short to TikTok too").

The Instagram caption's shape without Instagram's extras: the hook, the quote
with its source, the follow line, up to five hashtags (the Instagram caption's
own tags, #shorts never), no links, at most 2,200 characters."""
from __future__ import annotations

import re

import publish_instagram as ig

FOLLOW = "Follow for one Stoic line a day."
DEFAULT_TAGS = ["stoicism", "stoic", "marcusaurelius", "seneca", "epictetus"]
MAX_CHARS = 2200


def tiktok_caption(meta: dict) -> str:
    """meta: a posted-short post.json (hook, quote, author, citation, hashtags, igCaption)."""
    hook = str(meta.get("hook") or "").strip().rstrip(".!? ")
    quote = str(meta.get("quote") or "").strip()
    source = "— " + ", ".join(x for x in (str(meta.get("author") or "").strip(),
                                          str(meta.get("citation") or "").strip()) if x)
    from_ig = re.findall(r"#\w+", str(meta.get("igCaption") or ""))
    tags = ig.hashtags([*(meta.get("hashtags") or []), *from_ig, *DEFAULT_TAGS])
    parts = [f"{hook}." if hook else "", f"“{quote}”\n{source}" if quote else "", FOLLOW, " ".join(tags)]
    return "\n\n".join(p for p in parts if p)[:MAX_CHARS]
