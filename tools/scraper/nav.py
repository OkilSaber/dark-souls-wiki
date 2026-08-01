"""Extract the wiki's own category tree from #navMenu."""
import json
import re
import sys
import urllib.parse
from pathlib import Path

from bs4 import BeautifulSoup

HOST = "darksouls.wiki.fextralife.com"


def slug_of(href):
    """Normalize an internal wiki href into a page slug, or None if external."""
    if not href or href.startswith("#"):
        return None
    if href.startswith("http"):
        p = urllib.parse.urlparse(href)
        if p.netloc != HOST:
            return None
        href = p.path
    if not href.startswith("/"):
        return None
    path = href.split("?")[0].split("#")[0].lstrip("/")
    if not path:
        return None
    # Wiki page titles use + for spaces; keep the raw form as the canonical key
    return urllib.parse.unquote(path)


def parse_ul(ul):
    """Recursively turn a <ul> nav level into a list of nodes."""
    out = []
    for li in ul.find_all("li", recursive=False):
        a = li.find("a", recursive=False)
        if a is None:
            # some <li> wrap the anchor a level deeper
            a = li.find("a")
        if a is None:
            continue
        label = " ".join(a.get_text(" ", strip=True).split())
        slug = slug_of(a.get("href"))
        sub = li.find("ul", recursive=False)
        children = parse_ul(sub) if sub else []
        if not label and not children:
            continue
        out.append({"label": label, "slug": slug, "children": children})
    return out


def main():
    html = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "lxml")
    nav = soup.find("ul", id="navMenu")
    if nav is None:
        sys.exit("navMenu not found")
    tree = parse_ul(nav)

    # Drop nav sections that are pure community/meta noise
    SKIP = {"Home"}
    tree = [n for n in tree if n["label"] not in SKIP]

    slugs = set()

    def walk(nodes):
        for n in nodes:
            if n["slug"]:
                slugs.add(n["slug"])
            walk(n["children"])

    walk(tree)

    Path("nav_tree.json").write_text(json.dumps(tree, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"top-level sections: {len(tree)}")
    for n in tree:
        print(f"  {n['label']:<28} children={len(n['children'])}")
    print(f"distinct internal slugs in nav: {len(slugs)}")


if __name__ == "__main__":
    main()
