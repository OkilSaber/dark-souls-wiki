"""Phase 3: assign every scraped page to a category.

Signal priority matters. An index page links to everything it *mentions*
(the Talismans page mentions Firelink Shrine), so index membership alone
misclassifies badly. The page's own opening sentence is authoritative:
the wiki consistently writes "X is a Weapon in Dark Souls".

 pass 1  self-description text classifier      (~64% of pages, high precision)
 pass 2  membership in an index page's *structured listing* only
         (table cells / gallery cards / link-only list items, never prose)
 pass 3  build-page field heuristics, else Lore & Misc
"""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

OUT = Path("parsed")

# ---------------------------------------------------------------- text classifier
# Maps the wiki's own "is a ___ in Dark Souls" phrasing to (category, section).
TEXT_MAP = {
    # Equipment
    "weapon": ("Weapons", "Equipment"),
    "ammunition": ("Ammunition", "Equipment"),
    "ammo": ("Ammunition", "Equipment"),
    "arrow": ("Ammunition", "Equipment"),
    "bolt": ("Ammunition", "Equipment"),
    "shield": ("Shields", "Equipment"),
    "standard shield": ("Shields", "Equipment"),
    "small shield": ("Shields", "Equipment"),
    "greatshield": ("Shields", "Equipment"),
    "ring": ("Rings", "Equipment"),
    "helm": ("Helms", "Equipment"),
    "head armor": ("Helms", "Equipment"),
    "chest armor": ("Chest Armor", "Equipment"),
    "chest armour": ("Chest Armor", "Equipment"),
    "gauntlets": ("Gauntlets", "Equipment"),
    "hand armor": ("Gauntlets", "Equipment"),
    "leg armor": ("Leg Armor", "Equipment"),
    "leg armour": ("Leg Armor", "Equipment"),
    "armor set": ("Armor Sets", "Equipment"),
    "armour set": ("Armor Sets", "Equipment"),
    "unobtainable armour set": ("Armor Sets", "Equipment"),
    "unobtainable armor set": ("Armor Sets", "Equipment"),
    "catalyst": ("Catalysts", "Equipment"),
    "talisman": ("Talismans", "Equipment"),
    "flame": ("Pyromancy Flames", "Equipment"),
    "pyromancy flame": ("Pyromancy Flames", "Equipment"),
    # Magic
    "miracle": ("Miracles", "Magic"),
    "pyromancy": ("Pyromancies", "Magic"),
    "sorcery": ("Sorceries", "Magic"),
    "spell": ("Spells", "Magic"),
    # Items
    "consumable": ("Consumables", "Items"),
    "consumble": ("Consumables", "Items"),
    "projectiles": ("Consumables", "Items"),
    "projectile": ("Consumables", "Items"),
    "key item": ("Key Items", "Items"),
    "key bonfire item": ("Key Items", "Items"),
    "key": ("Keys", "Items"),
    "multiplayer item": ("Multiplayer Items", "Items"),
    "carving": ("Multiplayer Items", "Items"),
    "upgrade material": ("Upgrade Materials", "Items"),
    "ember": ("Upgrade Materials", "Items"),
    "ore": ("Upgrade Materials", "Items"),
    "titanite": ("Upgrade Materials", "Items"),
    "soul": ("Souls", "Items"),
    "tool": ("Items", "Items"),
    "focus": ("Items", "Items"),
    "item": ("Items", "Items"),
    "unobtainable item": ("Items", "Items"),
    # World
    "boss": ("Bosses", "World"),
    "optional boss": ("Bosses", "World"),
    "final boss": ("Bosses", "World"),
    "mini-boss": ("Mini Bosses", "World"),
    "mini boss": ("Mini Bosses", "World"),
    "enemy": ("Enemies", "World"),
    "unique enemy": ("Enemies", "World"),
    "npc enemy": ("Enemies", "World"),
    "npc phantom": ("Invaders", "World"),
    "invader": ("Invaders", "World"),
    "merchant": ("Merchants", "World"),
    "npc": ("NPCs", "World"),
    "character": ("NPCs", "World"),
    "location": ("Locations", "World"),
    "special dlc location": ("Locations", "World"),
    "area": ("Locations", "World"),
    "bonfire": ("Bonfires", "World"),
    # Lore
    "mentioned-only location": ("Lore", "Lore"),
    "mentioned-only character": ("Lore", "Lore"),
    # Character
    "covenant": ("Covenants", "Character"),
    "user-made covenant": ("Builds", "Builds"),
    "class": ("Classes", "Character"),
    "starting class": ("Classes", "Character"),
    "stat": ("Stats", "Character"),
    "gesture": ("Gestures", "Character"),
    "gift": ("Gifts", "Character"),
    # General / Guides
    "gameplay mechanic": ("Game Mechanics", "General"),
    "mechanic": ("Game Mechanics", "General"),
    "system": ("Game Mechanics", "General"),
    "damage type": ("Combat", "General"),
    "trophy and achievement": ("Trophies", "Guides"),
    # Builds
    "player-created build": ("Builds", "Builds"),
    "build": ("Builds", "Builds"),
}

# ---------------------------------------------------------------- index listings
# (display name, index slug, section) — most specific first. Used only as a
# fallback, and only for links inside that page's structured listing.
CATEGORY_INDEXES = [
    # Locations first: the Places index is small and authoritative, while every
    # equipment table lists the areas its items are found in.
    ("Locations", "Places", "World"),
    ("Helms", "Helms", "Equipment"),
    ("Chest Armor", "Chest+Armor", "Equipment"),
    ("Gauntlets", "Gauntlets", "Equipment"),
    ("Leg Armor", "Leg+Armor", "Equipment"),
    ("Armor Sets", "Armor", "Equipment"),
    ("Shields", "Shields", "Equipment"),
    ("Catalysts", "Catalysts", "Equipment"),
    ("Talismans", "Talismans", "Equipment"),
    ("Pyromancy Flames", "Flames", "Equipment"),
    ("Boss Soul Weapons", "Boss+Soul+Weapons", "Equipment"),
    ("Weapons", "Weapons", "Equipment"),
    ("Rings", "Rings", "Equipment"),
    ("Miracles", "Miracles", "Magic"),
    ("Pyromancies", "Pyromancies", "Magic"),
    ("Sorceries", "Sorceries", "Magic"),
    ("Spells", "Magic", "Magic"),
    ("Key Items", "Key+Items", "Items"),
    ("Keys", "Keys", "Items"),
    ("Consumables", "Consumables", "Items"),
    ("Multiplayer Items", "Multiplayer+Items", "Items"),
    ("Upgrade Materials", "Upgrades", "Items"),
    ("Titanite", "Titanite", "Items"),
    ("Souls", "Souls", "Items"),
    ("Items", "Items", "Items"),
    ("Area Bosses", "Area+Bosses", "World"),
    ("Mini Bosses", "Mini+Bosses", "World"),
    ("DLC Bosses", "Expansion+Bosses", "World"),
    ("Bosses", "Bosses", "World"),
    ("Invaders", "Invading+NPC+Phantoms", "World"),
    ("Merchants", "Merchants", "World"),
    ("NPCs", "NPCs", "World"),
    ("Bonfires", "Bonfire", "World"),
    ("Enemies", "Enemies", "World"),
    ("Classes", "Classes", "Character"),
    ("Stats", "Stats", "Character"),
    ("Covenants", "Covenants", "Character"),
    ("Gestures", "Gestures", "Character"),
    ("Gifts", "Gifts", "Character"),
    ("PvE Builds", "PvE+Builds", "Builds"),
    ("PvP Builds", "PvP+Builds", "Builds"),
    ("Builds", "Character+Builds", "Builds"),
    ("Walkthroughs", "Walkthroughs", "Guides"),
    ("New Player Help", "New+Player+Help", "Guides"),
    ("Trophies", "Trophy+&+Achievement+Guide", "Guides"),
    ("Guides", "Guides+&+Walkthroughs", "Guides"),
    ("Combat", "Combat", "General"),
    ("Secrets", "Secrets", "General"),
    ("Online", "Online", "Online"),
    ("Lore", "Lore", "Lore"),
    ("General Information", "General+Information", "General"),
]

SECTION_ORDER = ["Equipment", "Magic", "Items", "World", "Character",
                 "Builds", "Guides", "Lore", "General", "Online"]

IS_A_RE = re.compile(
    r"\b(?:is|are)\s+(?:a|an|the)?\s*([A-Za-z][A-Za-z \-]{1,28}?)\s+"
    r"(?:in|for|of|found in)\s+Dark\s*Souls", re.I)
JUNK_SLUG_RE = re.compile(r"^(space\.template|todo$)", re.I)
BUILD_FIELD_RE = re.compile(
    r"(starting class|soul level|created by|starting gift)\s*:", re.I)
BUILD_RE = re.compile(r"\b(build|pvp|pve)\b", re.I)
HUB_SLUGS = {s for _, s, _ in CATEGORY_INDEXES}


def classify_text(page):
    m = IS_A_RE.search(page["text"][:500])
    if not m:
        return None
    phrase = re.sub(r"\s+", " ", m.group(1).strip().lower())
    # pages phrased in the plural ("are the bosses of") need depluralising
    variants = [phrase]
    singular = re.sub(r"(?:es|s)$", "", phrase)
    words = [re.sub(r"(?:es|s)$", "", w) for w in phrase.split()]
    variants += [singular, " ".join(words)]
    for v in variants:
        if v in TEXT_MAP:
            return TEXT_MAP[v]
    # longest suffix / word match, e.g. "curved greatsword weapon" -> "weapon"
    for key in sorted(TEXT_MAP, key=len, reverse=True):
        for v in variants:
            if v.endswith(key) or key in v.split():
                return TEXT_MAP[key]
    return None


def structured_links(page):
    """Links that appear in an actual listing, not in prose.

    Table cells and gallery cards are listings. A list item counts only when
    its text is mostly link text, which distinguishes an index entry from a
    sentence that happens to contain a link.
    """
    out = set()
    for b in page["blocks"]:
        if b["t"] == "card":
            if b.get("l"):
                out.add(b["l"])
        elif b["t"] == "tbl":
            for row in b["rows"]:
                for cell in row:
                    for s in cell["s"]:
                        if s.get("l"):
                            out.add(s["l"])
        elif b["t"] == "li":
            for item in b["items"]:
                total = sum(len(s["x"]) for s in item["s"])
                linked = sum(len(s["x"]) for s in item["s"] if s.get("l"))
                if total and linked / total > 0.6:
                    for s in item["s"]:
                        if s.get("l"):
                            out.add(s["l"])
    return out


def main():
    pages = json.loads((OUT / "pages.json").read_text(encoding="utf-8"))
    print(f"pages: {len(pages)}")

    stubs = [s for s, p in pages.items()
             if JUNK_SLUG_RE.match(s)
             or (len(p["text"]) < 40 and len(p["blocks"]) <= 4)]
    for s in stubs:
        del pages[s]
    print(f"dropped {len(stubs)} stubs/templates -> {len(pages)} pages")

    assigned = {}
    cat_members = defaultdict(list)
    origin = Counter()

    def place(slug, label, section, how):
        assigned[slug] = (label, section)
        cat_members[(section, label)].append(slug)
        origin[how] += 1

    # pass 1 — self-description (authoritative)
    for slug, page in pages.items():
        r = classify_text(page)
        if r:
            place(slug, r[0], r[1], "text")

    # pass 2 — structured listing membership for whatever text missed
    for label, idx_slug, section in CATEGORY_INDEXES:
        idx = pages.get(idx_slug)
        if not idx:
            print(f"  ! missing index: {idx_slug}")
            continue
        for target in structured_links(idx):
            if target in assigned or target not in pages or target in HUB_SLUGS:
                continue
            place(target, label, section, "listing")

    # index/hub pages land in their own category
    for label, idx_slug, section in CATEGORY_INDEXES:
        if idx_slug in pages and idx_slug not in assigned:
            place(idx_slug, label, section, "hub")

    # pass 3 — builds by their field markers, else misc
    for slug in [s for s in pages if s not in assigned]:
        if (BUILD_FIELD_RE.search(pages[slug]["text"])
                or BUILD_RE.search(pages[slug]["title"]) or BUILD_RE.search(slug)):
            place(slug, "Builds", "Builds", "build-fields")
        else:
            place(slug, "Misc", "Lore", "misc")

    sections = []
    for section in SECTION_ORDER:
        cats = []
        for (sec, label), members in cat_members.items():
            if sec != section:
                continue
            members = sorted(set(members), key=lambda s: pages[s]["title"].lower())
            if members:
                cats.append({"name": label, "count": len(members), "slugs": members})
        if not cats:
            continue
        cats.sort(key=lambda c: -c["count"])
        sections.append({"name": section, "categories": cats})

    (OUT / "categories.json").write_text(
        json.dumps(sections, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "kept_slugs.json").write_text(
        json.dumps(sorted(pages), ensure_ascii=False), encoding="utf-8")

    print(f"\nassignment source: {dict(origin)}")
    total = sum(c["count"] for s in sections for c in s["categories"])
    print(f"sections {len(sections)}  categorized {total}")
    for s in sections:
        n = sum(c["count"] for c in s["categories"])
        print(f"  {s['name']:<10} {n:>5}  " +
              ", ".join(f"{c['name']}({c['count']})" for c in s["categories"][:8]))


if __name__ == "__main__":
    main()
