"""Phase 2: parse cached HTML into structured JSON blocks.

Output per page: ordered content blocks that the Flutter renderer walks directly.
Block kinds:
  {"t":"h",  "l":2, "x":"heading text"}
  {"t":"p",  "s":[span,...]}
  {"t":"li", "o":false, "items":[[span,...],...]}
  {"t":"q",  "s":[span,...]}                     blockquote
  {"t":"tbl","info":bool, "rows":[[cell,...],...]}
  {"t":"img","src":"hash.png", "alt":"..."}
span: {"x":text, "l":slug?, "b":1?, "i":1?}
cell: {"s":[span,...], "img":["src",...], "h":1?, "cs":n?, "rs":n?}
"""
import hashlib
import json
import re
import sys
import urllib.parse
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

HOST = "darksouls.wiki.fextralife.com"
CACHE = Path("html_cache")
OUT = Path("parsed")

BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "table",
              "blockquote", "div", "hr", "br", "img", "figure", "center", "section"}

# Boilerplate text we never want in the app
NOISE_RE = re.compile(
    r"(join the page discussion|tired of anon posting|register)|"
    r"(load more|anonymous)\s*$|"
    # in-page anchor jumps are meaningless offline
    r"^\s*(jump to|back to top)\b.{0,40}$", re.I)


def slug_of(href):
    if not href:
        return None
    href = href.strip()
    if href.startswith("#") or href.startswith("mailto:") or href.startswith("javascript:"):
        return None
    if href.startswith("//"):
        href = "https:" + href
    if href.startswith("http"):
        p = urllib.parse.urlparse(href)
        if p.netloc != HOST:
            return None
        href = p.path
    if not href.startswith("/"):
        return None
    path = href.split("?")[0].split("#")[0].lstrip("/")
    if not path or path.startswith("file/"):
        return None
    return urllib.parse.unquote(path)


def img_name(src):
    """Map an image URL to a stable local filename."""
    if not src:
        return None
    src = src.strip()
    if src.startswith("data:"):
        return None
    if src.startswith("//"):
        src = "https:" + src
    if src.startswith("http"):
        p = urllib.parse.urlparse(src)
        if p.netloc != HOST:
            return None
        src = p.path
    if not src.startswith("/file/"):
        return None
    path = urllib.parse.unquote(src.lstrip("/"))
    base = path.split("/")[-1]
    ext = Path(base).suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        ext = ".png"
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", Path(base).stem)[:60]
    h = hashlib.sha1(path.encode()).hexdigest()[:8]
    return f"{stem}_{h}{ext}", path


class Parser:
    def __init__(self):
        self.images = {}      # local name -> remote path
        self.links = set()

    # ---------- inline ----------
    def spans(self, node, bold=False, italic=False, link=None):
        out = []
        for child in node.children:
            if isinstance(child, NavigableString):
                txt = str(child)
                if txt.strip():
                    s = {"x": re.sub(r"\s+", " ", txt)}
                    if bold:
                        s["b"] = 1
                    if italic:
                        s["i"] = 1
                    if link:
                        s["l"] = link
                    out.append(s)
                elif txt and out and not out[-1]["x"].endswith(" "):
                    out.append({"x": " "})
                continue
            if not isinstance(child, Tag):
                continue
            name = child.name
            if name == "br":
                out.append({"x": "\n"})
            elif name in ("strong", "b"):
                out += self.spans(child, True, italic, link)
            elif name in ("em", "i"):
                out += self.spans(child, bold, True, link)
            elif name == "a":
                sl = slug_of(child.get("href"))
                if sl:
                    self.links.add(sl)
                out += self.spans(child, bold, italic, sl or link)
            elif name == "img":
                pass  # images handled at block level
            elif name in ("script", "style", "sup", "sub"):
                continue
            else:
                out += self.spans(child, bold, italic, link)
        return self.merge(out)

    @staticmethod
    def merge(spans):
        """Coalesce adjacent spans with identical styling."""
        out = []
        for s in spans:
            if out and out[-1].get("l") == s.get("l") and out[-1].get("b") == s.get("b") \
                    and out[-1].get("i") == s.get("i"):
                out[-1]["x"] += s["x"]
            else:
                out.append(dict(s))
        for s in out:
            s["x"] = re.sub(r" {2,}", " ", s["x"])
        out = [s for s in out if s["x"].strip() or "\n" in s["x"]]
        # Whitespace between an inline link and following punctuation becomes a
        # stray space ("... in Dark Souls ."); close it across the span boundary.
        for i in range(1, len(out)):
            if out[i]["x"][:1] in ",.;:!?)%" and out[i - 1]["x"].endswith(" "):
                out[i - 1]["x"] = out[i - 1]["x"].rstrip(" ")
        return [s for s in out if s["x"]]

    def collect_imgs(self, node):
        names = []
        for im in node.find_all("img"):
            r = img_name(im.get("src"))
            if r:
                name, path = r
                self.images[name] = path
                names.append(name)
        return names

    # ---------- blocks ----------
    def table(self, tb, info=False):
        rows = []
        for tr in tb.find_all("tr"):
            cells = []
            for td in tr.find_all(["td", "th"], recursive=False):
                c = {"s": self.spans(td)}
                imgs = self.collect_imgs(td)
                if imgs:
                    c["img"] = imgs
                if td.name == "th":
                    c["h"] = 1
                try:
                    cs = int(td.get("colspan") or 1)
                    rs = int(td.get("rowspan") or 1)
                except ValueError:
                    cs = rs = 1
                if cs > 1:
                    c["cs"] = cs
                if rs > 1:
                    c["rs"] = rs
                if c["s"] or "img" in c:
                    cells.append(c)
                else:
                    cells.append({"s": []})
            if cells and any(c["s"] or "img" in c for c in cells):
                rows.append(cells)
        if not rows:
            return None
        b = {"t": "tbl", "rows": rows}
        if info:
            b["info"] = 1
        return b

    def list_block(self, ul):
        items = []
        lis = ul.find_all("li", recursive=False)
        if not lis:
            # malformed wiki markup nests <ul> directly inside <ul>; without this
            # fallback the whole list is silently dropped
            lis = ul.find_all("li")
        for li in lis:
            inner = self.spans(li)
            imgs = self.collect_imgs(li)
            if inner or imgs:
                it = {"s": inner}
                if imgs:
                    it["img"] = imgs
                items.append(it)
        if not items:
            return None
        return {"t": "li", "o": 1 if ul.name == "ol" else 0, "items": items}

    def walk(self, node, out, depth=0):
        """Emit blocks in document order."""
        for child in node.children:
            if isinstance(child, NavigableString):
                if child.strip():
                    sp = self.merge([{"x": re.sub(r"\s+", " ", str(child))}])
                    if sp:
                        out.append({"t": "p", "s": sp})
                continue
            if not isinstance(child, Tag):
                continue
            n = child.name
            if n in ("script", "style", "noscript", "iframe", "form", "button", "nav"):
                continue
            cls = " ".join(child.get("class") or [])
            cid = child.get("id") or ""
            # skip comment/discussion widgets and ads
            if re.search(r"comment|disqus|ad-|advert|social|share|breadcrumb|editor|"
                         r"page-tools|toc-", cls + " " + cid, re.I):
                continue

            if n in ("h1", "h2", "h3", "h4", "h5", "h6"):
                # Index pages use headings as gallery cards:
                #   <h3 class="col-sm-4"><a href="/Boss"><img/><br/>Boss</a></h3>
                # so the link and image must be captured, not just the text.
                imgs = self.collect_imgs(child)
                sp = self.spans(child)
                txt = " ".join(child.get_text(" ", strip=True).split())
                if NOISE_RE.search(txt):
                    continue
                if imgs:
                    link = next((s["l"] for s in sp if s.get("l")), None)
                    card = {"t": "card", "src": imgs[0], "x": txt}
                    if link:
                        card["l"] = link
                    out.append(card)
                elif txt:
                    b = {"t": "h", "l": int(n[1]), "x": txt}
                    if any(s.get("l") for s in sp):
                        b["s"] = sp
                    out.append(b)
            elif n == "p":
                imgs = self.collect_imgs(child)
                sp = self.spans(child)
                txt = "".join(s["x"] for s in sp).strip()
                if sp and not NOISE_RE.search(txt):
                    out.append({"t": "p", "s": sp})
                for i in imgs:
                    out.append({"t": "img", "src": i})
            elif n in ("ul", "ol"):
                b = self.list_block(child)
                if b:
                    out.append(b)
            elif n == "table":
                b = self.table(child, info=bool(re.search(r"infobox", cls, re.I)))
                if b:
                    out.append(b)
            elif n == "blockquote":
                sp = self.spans(child)
                if sp:
                    out.append({"t": "q", "s": sp})
            elif n == "img":
                r = img_name(child.get("src"))
                if r:
                    name, path = r
                    self.images[name] = path
                    alt = (child.get("alt") or "").strip()
                    out.append({"t": "img", "src": name, **({"alt": alt} if alt else {})})
            elif n == "hr":
                pass
            elif n in ("a",):
                sl = slug_of(child.get("href"))
                if sl:
                    self.links.add(sl)
                sp = self.spans(child.parent if False else child, link=sl)
                if sp:
                    out.append({"t": "p", "s": sp})
                for i in self.collect_imgs(child):
                    out.append({"t": "img", "src": i})
            else:
                # container: recurse. Infobox divs are tagged so nested tables get info=1
                if re.search(r"infobox", cls, re.I):
                    for tb in child.find_all("table"):
                        b = self.table(tb, info=True)
                        if b:
                            out.append(b)
                    continue
                if depth < 14:
                    self.walk(child, out, depth + 1)


def clean_blocks(blocks):
    """Drop trailing boilerplate and collapse empties."""
    out = []
    for b in blocks:
        if b["t"] == "p":
            txt = "".join(s["x"] for s in b["s"]).strip()
            if not txt or NOISE_RE.search(txt):
                continue
            if len(txt) < 2:
                continue
        out.append(b)
    # de-dup consecutive identical blocks (wiki templates repeat)
    ded = []
    for b in out:
        if ded and json.dumps(ded[-1], sort_keys=True) == json.dumps(b, sort_keys=True):
            continue
        ded.append(b)
    # Trim trailing empty section headers, but cap it: some pages (user builds)
    # legitimately use headings as body text, and popping greedily empties them.
    popped = 0
    while ded and ded[-1]["t"] == "h" and popped < 2 and len(ded) > 3:
        ded.pop()
        popped += 1
    return ded


def parse_file(path, slug):
    html = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "lxml")
    cb = soup.find(id="wiki-content-block")
    if cb is None:
        return None
    for bad in cb.find_all(["script", "style", "noscript", "iframe", "form"]):
        bad.decompose()

    p = Parser()
    blocks = []
    p.walk(cb, blocks)
    blocks = clean_blocks(blocks)

    title = slug.replace("+", " ")
    h1 = soup.find("h1")
    if h1:
        t = " ".join(h1.get_text(" ", strip=True).split())
        t = re.sub(r"\s*\|\s*Dark Souls( Remastered)? Wiki\s*$", "", t, flags=re.I).strip()
        if t and len(t) < 120:
            title = t

    # join with "" — spans already carry their own spacing, and re-inserting
    # separators would put a gap before punctuation
    text = " ".join(
        "".join(s["x"] for s in b["s"])
        for b in blocks if b["t"] in ("p", "q")
    )
    return {
        "slug": slug,
        "title": title,
        "blocks": blocks,
        "images": sorted(p.images),
        "links": sorted(p.links),
        "text": re.sub(r"\s+", " ", text).strip()[:1200],
    }, p.images


def main():
    OUT.mkdir(exist_ok=True)
    slugs = Path("all_slugs.txt").read_text(encoding="utf-8").splitlines()
    sys.path.insert(0, ".")
    from fetch_pages import cache_path

    all_images = {}
    pages = {}
    stats = Counter()
    for i, slug in enumerate(slugs):
        cp = cache_path(slug)
        if not cp.exists():
            stats["missing"] += 1
            continue
        try:
            res = parse_file(cp, slug)
        except Exception as e:
            stats["error"] += 1
            print(f"  ERROR {slug}: {e}")
            continue
        if res is None:
            stats["no_content"] += 1
            continue
        page, imgs = res
        if not page["blocks"]:
            stats["empty"] += 1
            continue
        all_images.update(imgs)
        pages[slug] = page
        stats["ok"] += 1
        if (i + 1) % 250 == 0:
            print(f"  parsed {i+1}/{len(slugs)}  ok={stats['ok']}", flush=True)

    (OUT / "pages.json").write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")
    (OUT / "images.json").write_text(json.dumps(all_images, indent=1), encoding="utf-8")
    print("stats:", dict(stats))
    print("pages:", len(pages), "distinct images:", len(all_images))
    nb = Counter(b["t"] for p in pages.values() for b in p["blocks"])
    print("blocks:", dict(nb))


if __name__ == "__main__":
    main()
