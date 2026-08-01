"""Phase 4: download every image referenced by a kept page."""
import asyncio
import json
import urllib.parse
from pathlib import Path

import httpx

HOST = "https://darksouls.wiki.fextralife.com"
RAW = Path("images_raw")
CONCURRENCY = 10
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


async def one(client, name, remote, sem, stats):
    dest = RAW / name
    if dest.exists() and dest.stat().st_size > 200:
        stats["cached"] += 1
        return
    url = f"{HOST}/{urllib.parse.quote(remote)}"
    async with sem:
        for attempt in range(3):
            try:
                r = await client.get(url, timeout=60.0, follow_redirects=True)
                if r.status_code == 200 and len(r.content) > 100:
                    dest.write_bytes(r.content)
                    stats["ok"] += 1
                    return
                if r.status_code == 404:
                    stats["404"] += 1
                    return
                await asyncio.sleep(2 * (attempt + 1))
            except Exception:
                await asyncio.sleep(2 * (attempt + 1))
        stats["fail"] += 1
        stats.setdefault("failed", []).append(name)


async def main():
    RAW.mkdir(exist_ok=True)
    images = json.loads(Path("parsed/images.json").read_text())
    pages = json.loads(Path("parsed/pages.json").read_text(encoding="utf-8"))
    kept = set(json.loads(Path("parsed/kept_slugs.json").read_text(encoding="utf-8")))

    # only images actually reachable from a page we ship
    needed = {}
    for slug in kept:
        for n in pages[slug]["images"]:
            if n in images:
                needed[n] = images[n]
    print(f"{len(images)} known images, {len(needed)} referenced by kept pages")

    stats = {"ok": 0, "cached": 0, "404": 0, "fail": 0}
    sem = asyncio.Semaphore(CONCURRENCY)
    async with httpx.AsyncClient(headers={"User-Agent": UA}) as client:
        items = list(needed.items())
        for i in range(0, len(items), 200):
            await asyncio.gather(*[one(client, n, r, sem, stats)
                                   for n, r in items[i:i + 200]])
            print(f"  {min(i+200,len(items))}/{len(items)} {stats}", flush=True)

    print("done:", {k: v for k, v in stats.items() if k != "failed"})
    if stats.get("failed"):
        Path("failed_images.txt").write_text("\n".join(stats["failed"]))
    Path("parsed/needed_images.json").write_text(json.dumps(needed, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
