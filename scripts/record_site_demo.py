"""Record a demo GIF of the deployed BioLit Agent site with Playwright.

Captures frames at each interaction (scroll, archive, search) and assembles
them into an optimised GIF. Run:  python3 /tmp/record_site.py <chrome> <out.gif>
"""

import io
import sys
from PIL import Image
from playwright.sync_api import sync_playwright

BASE = "https://MaybeBio.github.io/Daily-Paper-Agent-idp-interaction-ai"
W, H = 1024, 640
QUERY = "molecular dynamics"

frames: list[tuple[Image.Image, int]] = []


def cap(pg, ms: int = 80) -> None:
    frames.append((Image.open(io.BytesIO(pg.screenshot())).convert("RGB"), ms))


def scroll(pg, dy: int, steps: int, ms: int = 70) -> None:
    for _ in range(steps):
        pg.mouse.wheel(0, dy)
        cap(pg, ms)


def main() -> None:
    chrome, out = sys.argv[1], sys.argv[2]
    with sync_playwright() as p:
        b = p.chromium.launch(
            headless=True, executable_path=chrome,
            args=["--no-sandbox", "--disable-gpu", "--no-proxy-server"],
        )
        pg = b.new_page(viewport={"width": W, "height": H})

        # 1) landing + a slow scroll through this week's cards
        pg.goto(BASE + "/", wait_until="load", timeout=60000)
        pg.wait_for_timeout(2000)
        cap(pg, 1100)
        scroll(pg, 130, 18)
        cap(pg, 900)
        scroll(pg, -600, 6, 50)
        cap(pg, 500)

        # 2) archive
        pg.click("nav a:has-text('归档')")
        pg.wait_for_timeout(1500)
        cap(pg, 900)
        scroll(pg, 130, 10)
        cap(pg, 800)

        # 3) search: type a query and show hits
        pg.click("nav a:has-text('搜索')")
        pg.wait_for_timeout(1200)
        cap(pg, 700)
        pg.click("#search-query")
        cap(pg, 250)
        for ch in QUERY:
            pg.keyboard.type(ch)
            cap(pg, 90)
        pg.wait_for_timeout(2000)
        cap(pg, 1400)
        hits = pg.eval_on_selector_all(
            "a[href*='paper'], .result, li", "els => els.length"
        )
        print("result-ish elements after search:", hits)
        scroll(pg, 120, 6)
        cap(pg, 1100)
        b.close()

    imgs = [f for f, _ in frames]
    durs = [d for _, d in frames]
    imgs[0].save(
        out, save_all=True, append_images=imgs[1:], duration=durs,
        loop=0, optimize=True, disposal=2,
    )
    total = sum(durs) / 1000
    print(f"frames={len(imgs)} duration={total:.1f}s -> {out}")


main()
