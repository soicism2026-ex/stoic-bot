# Wallpaper packs (Gumroad)

Owner 2026-11-13: "create some Desktop & Mobile Wallpaper Packs I can sell on Gumroad as well for the channel."

One pack = one philosopher x one screen. Six packs in all (Marcus Aurelius, Seneca, Epictetus; phone and desktop), up to 10 wallpapers each. Every wallpaper is a colour painting from the channel's own painter (FLUX.2 [klein] on Cloudflare, the Shorts' look) with one verified quote set over it: Cormorant Garamond Bold, the author in Cinzel gold, the source under it, `forged.in.stoicism` small at the bottom. A picture the painter cannot make is skipped, never swapped for stock.

## Run a pack

Actions > "Wallpaper pack" > Run workflow (manual only, never scheduled):

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

Cloudflare's free 10,000 neurons a day are shared with the daily posts, which paint before 20:00 UTC. A phone picture costs about 208 neurons (1024x1920), a desktop one about 312 (1920x1088), so a pack of 10 is about 2,080 (phone) or 3,120 (desktop). `render` prints the estimate, and refuses before 20:00 UTC unless `--force` (the workflow's `force`). Painted stills are cached in `data/still_cache`, so a re-run of the same pack costs nothing. Without the Cloudflare keys `render` exits 2.

Pillow is not in `requirements.txt`; the workflow installs it. If the painter returns a portrait picture for desktop, the pack builds a 4K frame with the painting centred over a blurred, darkened copy of itself.

## Gumroad listing copy

**Title:** Forged in Stoicism: Marcus Aurelius Wallpaper Pack (swap the name for Seneca or Epictetus; the bundle is "Forged in Stoicism: Complete Wallpaper Collection")

**Description:**

Ten wallpapers for your phone, each one a painting with a single line from Marcus Aurelius. Not a poster, not a slogan: something calm to look at every time you pick the phone up.

The pictures are painted in the same style as the Forged in Stoicism Shorts. Every quote is checked word for word against its source, and the source is printed under it. The top of each is left clear for your lock-screen clock.

Use one for a week, then change it. They are for your own screens. If you want the habit behind the words, the 30-day Stoic Reset journal is on my page too.

**What's inside:**
- 10 wallpapers, 1170x2532 PNG (phone) or 3840x2160 JPEG (desktop)
- One verified quote each, with its source
- A README with how to set them
- Personal-use licence: for your own screens; not for resale or redistribution

**Price:** C$4.99 per pack; C$9.99 for the bundle of all three authors (the journal sells at C$5.99). A phone and desktop pair of one author could ship as one product by zipping both packs.

**Tags:** stoicism, stoic wallpaper, marcus aurelius, seneca, epictetus, phone wallpaper, desktop wallpaper, 4k wallpaper, quote wallpaper, dark wallpaper, motivation, philosophy
