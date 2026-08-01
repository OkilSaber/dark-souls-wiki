"""Safety net: compare visible text in the source HTML against text captured
in the parsed blocks, to catch systematic parser content loss."""
import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, ".")
from fetch_pages import cache_path

STOP = re.compile(r"[^a-z0-9]+")


def words(s):
    return [w for w in STOP.split(s.lower()) if len(w) > 3]


def block_text(blocks):
    parts = []
    for b in blocks:
        t = b["t"]
        if t in ("p", "q"):
            parts += [s["x"] for s in b["s"]]
        elif t == "h":
            parts.append(b["x"])
        elif t == "card":
            parts.append(b["x"])
        elif t == "li":
            for it in b["items"]:
                parts += [s["x"] for s in it["s"]]
        elif t == "tbl":
            for r in b["rows"]:
                for c in r:
                    parts += [s["x"] for s in c["s"]]
    return " ".join(parts)


def main():
    pages = json.loads(Path("parsed/pages.json").read_text(encoding="utf-8"))
    bad = []
    checked = 0
    for slug, page in pages.items():
        cp = cache_path(slug)
        if not cp.exists():
            continue
        checked += 1
        if checked % 200 == 0:
            print(f"  audited {checked}", flush=True)
        soup = BeautifulSoup(cp.read_text(encoding="utf-8", errors="replace"), "lxml")
        cb = soup.find(id="wiki-content-block")
        if cb is None:
            continue
        for t in cb.find_all(["script", "style", "noscript"]):
            t.decompose()
        src = set(words(cb.get_text(" ", strip=True)))
        got = set(words(block_text(page["blocks"])))
        if not src:
            continue
        missing = src - got
        cov = 1 - len(missing) / len(src)
        if cov < 0.80 and len(src) > 40:
            bad.append((cov, slug, len(src), sorted(missing)[:12]))
    bad.sort()
    print(f"\naudited {checked} pages; {len(bad)} below 80% word coverage")
    for cov, slug, n, miss in bad[:25]:
        print(f"  {cov:.0%} {slug[:44]:<44} src_words={n:<5} missing: {miss[:8]}")


if __name__ == "__main__":
    main()
