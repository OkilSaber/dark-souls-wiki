<div align="center">

<img src="icon/icon_1024.png" width="120" alt="Dark Souls Wiki app icon">

# Dark Souls Wiki — Offline

An Android app holding a complete offline copy of the
[Fextralife Dark Souls wiki](https://darksouls.wiki.fextralife.com).
No network access at any point, including images.

**1,696 pages · 1,887 images · ~80 MB bundled**

</div>

---

## Why

Dark Souls is a game you play with a wiki open, and that wiki is exactly the
kind of site that struggles on a phone: ad-heavy, slow, and useless without
signal. This bundles the whole thing into the APK — every article, table,
infobox and image — and renders it natively.

## Features

- **Fully offline.** No requests, no spinners, no degraded mode.
- **Organised the way the wiki is** — 10 sections and ~50 categories, derived
  from the wiki's own navigation rather than invented.
- **Instant ranked search** over every page title, falling back to summaries.
- **Save pages** — tap the bookmark in an article, or long-press any list row.
  Persisted across launches.
- **Faithful articles** — infoboxes, multi-column stat tables with colspans,
  item-description flavour text, gallery grids, tappable cross-links.
- **Pinch-zoom image viewer** with drag-to-dismiss.
- Adapts to the system font-size setting and honours *remove animations*.

## Quick start

The scraped content is **not committed** (see [Content](#content)), so generate
it once, then build:

```sh
# 1. Generate assets/data and assets/img  (~20 min, ~550 MB of scratch space)
cd tools/scraper
python3 -m venv venv
./venv/bin/pip install beautifulsoup4 lxml httpx Pillow
#    then follow tools/scraper/README.md for the seven stages

# 2. Build and run
cd ../..
flutter pub get
flutter run
```

Release builds should split per ABI — a fat APK carries three copies of the
Flutter engine and lands at ~104 MB, where `arm64-v8a` alone is ~78 MB:

```sh
flutter build apk --release --split-per-abi
```

## How it works

### The pipeline

Seven stages, each cached so any one can be re-run without redoing the others.
Full detail in [`tools/scraper/README.md`](tools/scraper/README.md).

```
sitemap.xml → fetch_pages → parse_pages → categorize
                                 ↓             ↓
                           fetch_images → optimize_images → build_bundle
                                                                 ↓
                                                        assets/{data,img}
```

The interesting stage is **categorisation**. Index-page links turn out to be a
bad membership signal: the Talismans page links to Firelink Shrine because
that's where one is found, which would file a location under Equipment. So the
wiki's own prose is used instead — articles open with *"X is a Weapon in Dark
Souls"*, which resolves ~1,290 of 1,735 pages at high precision. Structured
listing membership and field heuristics handle the rest.

`audit.py` compares words in the source HTML against words captured in the
parsed blocks and flags anything under 80% coverage — that's the check that
catches silent extraction bugs.

### The app

| Path | Role |
| --- | --- |
| `lib/wiki_repository.dart` | Loads a ~0.5 MB index at startup; article bodies come from 64 shards on demand, behind an LRU cache. |
| `lib/block_renderer.dart` | Turns parsed blocks into widgets — the bulk of the rendering. |
| `lib/motion.dart` | Curves, durations, `Pressable`, staggered entrances, page transitions. |
| `lib/theme.dart` | Palette and type scale. |
| `lib/favorites.dart` | Saved pages, persisted via `SharedPreferences`. |
| `lib/screens/` | Home, section, category, article, search, saved, image viewer. |

Sharding keeps startup cheap: the index parses in one frame, and a ~380 KB shard
is only touched when you open a page inside it. Both are decoded on a background
isolate via `compute`. A page's shard is `hash(slug) % 64`, and the Dart and
Python implementations must agree — `test/wiki_test.dart` pins that.

### Design notes

A few decisions that aren't obvious from the code:

- **Feedback starts on pointer-down, never on release.** Every tap target is a
  `Pressable` driven by an `AnimationController`, so a fast tap still reverses
  smoothly from wherever the shrink had reached.
- **No `ease-in` anywhere.** It delays the first frames — exactly the ones being
  watched. Entrances use a strong ease-out.
- **Type is sized as a set.** Tracking is negative on display text (letters
  drift apart as they grow), zero on body, slightly positive on small labels.
  One letter-spacing value is always wrong at some size.
- **Layout scales with text, not just fonts.** The section grid states its
  height and grows with `MediaQuery.textScalerOf`; a fixed aspect ratio clips
  labels the moment the system font scales up.
- **The image viewer decides on projected momentum,** not raw distance — a short
  flick dismisses where a slow drag of the same length springs back.

## Icon

`icon/icon.svg` is the source — a bonfire coiled sword in the app's own palette.
`icon/make_icons.py` regenerates every density plus the adaptive layers.

```sh
cd icon && python3 make_icons.py     # requires rsvg-convert
```

## Tests

```sh
flutter test
flutter analyze
```

Beyond unit coverage, the suite renders a wide sample of *real bundled articles*
and fails on any layout error, and sweeps the home screen across three widths ×
four text scales. Those two catch the failures that otherwise only surface as a
striped overflow banner on a real device.

The suite reads `assets/`, so run the scraper first.

## Known gaps

- Embedded YouTube walkthroughs can't work offline, so those headings appear
  with no body.
- The ~300 pages under Lore/Misc are genuinely uncategorised on the wiki (lore
  fragments, community pages, calculators) rather than misfiled.
- Forum, comment and login areas are not scraped at all.

## Content

The wiki text and images belong to
[Fextralife](https://darksouls.wiki.fextralife.com) and its contributors; Dark
Souls is © FromSoftware / Bandai Namco. **None of that content is committed
here** — only the code that fetches and renders it. Run the scraper to build
your own local copy.

The crawler honours the `User-agent: *` rules in the wiki's `robots.txt` and
rate-limits itself. Built for personal offline use, not redistribution.
