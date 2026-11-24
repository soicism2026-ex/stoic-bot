# Wallpaper packs (Gumroad)

Owner 2026-11-13: "create some Desktop & Mobile Wallpaper Packs I can sell on Gumroad as well for the channel."

One pack = one philosopher x one screen. Six packs in all (Marcus Aurelius, Seneca, Epictetus; phone and desktop), up to 10 wallpapers each. Every wallpaper is a colour painting from the channel's own painter (FLUX.2 [klein] on Cloudflare, the Shorts' look) with one verified quote set over it: Cormorant Garamond Bold, the author in Cinzel gold, the source under it, `forged.in.stoicism` small at the bottom. A picture the painter cannot make is skipped, never swapped for stock.

## Run a pack

Actions > "Wallpaper pack" > Run workflow (evenings 20:33-23:13 UTC from the queue, one pack a night, or by hand):

| Input | Values |
|-------|--------|
| `pack` | marcus, seneca, epictetus |
| `size` | phone (1170x2532 PNG), desktop (3840x2160 JPEG) |
| `limit` | 10 (shortest quotes first) |
| `force` | leave off; see the budget |

First pack: `pack=marcus`, `size=phone`, `limit=10`, `force=false`, started after 20:00 UTC.

The run paints, zips, and uploads `<pack>-<size>.zip`, `<pack>-<size>-cover.jpg` and `<pack>-<size>-manifest.json` to the `wallpapers` release (a same-named asset is replaced), and attaches the cover as a workflow artifact. Download the zip and cover from the release and upload them to Gumroad by hand.

Locally: `python scripts/wallpapers.py render|package|publish --pack marcus --size phone --out wallpapers_out` (needs `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN`, ffmpeg, Pillow).

## The budget rule

Cloudflare's free 10,000 neurons a day (reset 00:00 UTC) belong to the Shorts and their rehearsals. A phone picture costs about 208 neurons (1024x1920), a desktop one about 312 (1920x1088), so a pack of 10 is about 2,080 (phone) or 3,120 (desktop). `render` prints the estimate and paints only when `src/spare_paint.py` allows it (20:00-23:59 UTC, tomorrow's first Short rehearsed and fully painted; see docs/reference.md "Painting budget") unless `--force` (the workflow's `force`). A night with a pack already finished, or while the next long video still has unpainted scenes, exits 0 with one log line. Painted stills are cached in `data/still_cache`, so a re-run of the same pack costs nothing. Without the Cloudflare keys `render` exits 2.

Pillow is not in `requirements.txt`; the workflow installs it. If the painter returns a portrait picture for desktop, the pack builds a 4K frame with the painting centred over a blurred, darkened copy of itself.

## Two versions of every pack (owner 2026-11-24)

"I dont think we can sell the wallpapers unless we sell them low quality for free then sell high quality for 5 bucks." Each run makes two zips, both private workflow artifacts (`wallpapers-<pack>-<size>`); the public `wallpapers` release still carries only the cover and the manifest, and the manifest lists both (`free` block + the full pack at the top level).

| | Free sample | Full pack ($5) |
|---|---|---|
| File | `<pack>-<size>-free.zip` | `<pack>-<size>.zip` |
| Wallpapers | 5 (the first five) | all (up to 10) |
| Size | phone 1080x1920, desktop 1920x1080 | phone 1170x2532 PNG, desktop 3840x2160 JPEG 92 |
| Quality | JPEG 80 | full |
| Mark | `@forged.in.stoicism` in the bottom-right corner | none |

A phone sample (a different shape from the 1170x2532 original) is set whole over a blurred copy of itself, never cropped. Code: `free_version`, `package_free` in `scripts/wallpapers.py`; tests in `tests/test_wallpapers.py`.

## Gumroad listing copy

Two listings per pack. Upload the free zip to the first and the full zip to the second (both from the run's workflow artifact).

### Listing 1: the free sample ($0+, "pay what you want")

**Title:** Forged in Stoicism: Marcus Aurelius Wallpapers, Free Sample (swap the name for Seneca or Epictetus)

**Price:** $0+ (pay what you want; a tip is welcome, nothing is required)

**Description:**

Five wallpapers for your phone (or desktop), each a painting with one line from Marcus Aurelius, free. Take them, use them, see if you like them.

They are the lighter version: smaller files, with a small @forged.in.stoicism mark in the corner. If you want the whole set at full quality and without the mark, the full pack is $5 on my page: "Forged in Stoicism: Marcus Aurelius Wallpaper Pack".

**What's inside:** 5 wallpapers (1080x1920 phone / 1920x1080 desktop, JPEG), a README, personal-use licence.

### Listing 2: the full pack ($5)

**Title:** Forged in Stoicism: Marcus Aurelius Wallpaper Pack (swap the name for Seneca or Epictetus; the bundle is "Forged in Stoicism: Complete Wallpaper Collection")

**Description:**

Ten wallpapers for your phone, each one a painting with a single line from Marcus Aurelius. Not a poster, not a slogan: something calm to look at every time you pick the phone up.

The pictures are painted in the same style as the Forged in Stoicism Shorts. Every quote is checked word for word against its source, and the source is printed under it. The top of each is left clear for your lock-screen clock. Full quality, no corner mark; try the free sample first if you like.

Use one for a week, then change it. They are for your own screens. If you want the habit behind the words, the 30-day Stoic Reset journal is on my page too.

**What's inside:**
- 10 wallpapers, 1170x2532 PNG (phone) or 3840x2160 JPEG (desktop), no mark
- One verified quote each, with its source
- A README with how to set them
- Personal-use licence: for your own screens; not for resale or redistribution

**Price:** $5 per pack (the journal sells at C$5.99). A bundle of all three authors can be priced at your choice.

**Tags:** stoicism, stoic wallpaper, marcus aurelius, seneca, epictetus, phone wallpaper, desktop wallpaper, 4k wallpaper, quote wallpaper, dark wallpaper, motivation, philosophy
