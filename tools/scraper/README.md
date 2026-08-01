# Scraper pipeline

Regenerates `assets/data` and `assets/img` from the Fextralife Dark Souls wiki.
The app ships the generated output, so this only needs re-running to refresh
content.

The intermediate artefacts (`html_cache/`, `images_raw/`, `parsed/`) are
throwaway — several hundred MB — and are not part of the app.

## Setup

```sh
python3 -m venv venv
./venv/bin/pip install beautifulsoup4 lxml httpx Pillow
```

## Run, in order

```sh
cd tools/scraper
curl -sL https://darksouls.wiki.fextralife.com/sitemap.xml -o sitemap.xml
curl -sL -A "Mozilla/5.0" https://darksouls.wiki.fextralife.com/Dark+Souls+Wiki -o main.html

./venv/bin/python nav.py main.html      # nav_tree.json — the wiki's own section tree
./venv/bin/python fetch_pages.py        # html_cache/  (~1950 pages, ~370 MB)
./venv/bin/python parse_pages.py        # parsed/pages.json — structured blocks
./venv/bin/python audit.py              # flags pages where extraction lost text
./venv/bin/python categorize.py         # parsed/categories.json
./venv/bin/python fetch_images.py       # images_raw/ (~1890 images, ~180 MB)
./venv/bin/python optimize_images.py    # images_opt/ (~55 MB)
./venv/bin/python build_bundle.py       # writes ../../assets/{data,img}
```

`build_bundle.py` resolves the project root from its own location, so it writes
to `assets/` wherever the checkout lives.

## What each stage does

| Script | Purpose |
| --- | --- |
| `nav.py` | Parses `#navMenu` into the section/category skeleton. |
| `fetch_pages.py` | Crawls every sitemap URL into an HTML cache. Honours the `User-agent: *` rules in robots.txt, 8 concurrent requests, retries with backoff. Re-runs skip cached pages. |
| `parse_pages.py` | Extracts `#wiki-content-block` into ordered blocks (headings, paragraphs, lists, tables, infoboxes, images, gallery cards) with inline link/bold/italic spans. |
| `audit.py` | Compares words in the source HTML against words captured in the blocks and reports pages below 80% coverage. This is what catches silent extraction bugs — keep it near zero. |
| `categorize.py` | Assigns each page a category. See below. |
| `fetch_images.py` | Downloads only images reachable from a kept page. |
| `optimize_images.py` | Caps dimensions at 1000px, flattens unused alpha to JPEG, leaves small icons alone. ~180 MB → ~55 MB. |
| `build_bundle.py` | Emits `index.json` plus 64 content shards, copies images, rewrites image names, and drops links pointing at pages that were not kept. |

## How categorisation works

Index-page links are a poor membership signal on this wiki — the Talismans page
links to Firelink Shrine because that is where one is found, which would file a
location under Equipment. So the order is:

1. **Self-description.** Articles open with "X is a Weapon in Dark Souls".
   `TEXT_MAP` maps that phrase to a category. This resolves ~1290 of 1735 pages
   and is the highest-precision signal available.
2. **Structured listing membership.** For the rest, a page counts as a member of
   an index only if the link appears in that index's table, gallery card, or a
   list item that is mostly link text — never in prose.
3. **Fallbacks.** Build pages are recognised by their "Starting Class:" /
   "Soul Level:" fields; anything left becomes Lore/Misc.

Wiki scaffolding (`space.template.*` pages, art stubs with no prose) is dropped.

## Shard hashing

`build_bundle.shard_of` and `WikiRepository.shardOf` must stay in agreement or
articles resolve to the wrong file. `test/wiki_test.dart` asserts this.
