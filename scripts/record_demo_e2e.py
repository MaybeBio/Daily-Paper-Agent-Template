"""Record the end-to-end BioLit Agent demo:

    repo page -> issues list -> weekly issue (push table) -> click the last
    column's Pages link -> AI deep-read paper page -> nav back to the site
    home (this week / archive / search) -> open a paper from this week.

Run: python3 /tmp/record_daily_e2e.py <chrome> <out.gif>
"""

import io
import sys

from PIL import Image
from playwright.sync_api import sync_playwright

REPO = "https://github.com/MaybeBio/Daily-Paper-Agent-idp-interaction-ai"
SITE = "https://maybebio.github.io/Daily-Paper-Agent-idp-interaction-ai"
# score-9 paper from the latest weekly issue -> has the full Paper Card + review
PICK = "42742050"
QUERY = "molecular dynamics"
W, H = 1024, 640

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
        # NOTE: no --no-proxy-server -- github.com is only reachable via the env
        # proxy here, and the Pages host works through it too.
        b = p.chromium.launch(headless=True, executable_path=chrome,
                              args=["--no-sandbox", "--disable-gpu"])
        pg = b.new_page(viewport={"width": W, "height": H})
        pg.set_default_timeout(60000)

        # 1) repo landing page
        pg.goto(REPO, wait_until="load"); pg.wait_for_timeout(2500)
        cap(pg, 1200)
        scroll(pg, 140, 4)

        # 2) issues list -- the weekly pushes
        pg.goto(REPO + "/issues", wait_until="load"); pg.wait_for_timeout(3000)
        cap(pg, 1200)
        scroll(pg, 120, 3)

        # 3) the latest weekly issue, scrolled to the push table
        pg.goto(REPO + "/issues/3", wait_until="load"); pg.wait_for_timeout(3000)
        cap(pg, 900)
        scroll(pg, 150, 6)
        cap(pg, 1200)          # the table: 标题 / 评分 / 一句话 / 链接

        # 4) follow the LAST column ("解析") to the rendered Pages paper page
        # NB: the href is "MaybeBio.github.io" (capitalised) and CSS attribute
        # selectors are case-sensitive, so match on the host suffix + PMID.
        link = pg.query_selector(f'a[href*="github.io"][href*="{PICK}"]')
        print("解析 link found:", bool(link))
        link.click()
        pg.wait_for_load_state("load"); pg.wait_for_timeout(2500)
        print("  ->", pg.url[:100])
        cap(pg, 1400)                       # title + 摘要 / 摘要翻译

        # the Paper Card is ~11k px tall, so jump to landmark sections instead
        # of scrolling blindly (that would need ~70 frames and reach nothing).
        for heading, hold in (("Paper Card", 1300), ("04 背景与发展脉络", 1100),
                              ("10 实验设计与证据链", 1100), ("审稿人评审", 1400)):
            loc = pg.locator("h2", has_text=heading).first
            if loc.count():
                loc.scroll_into_view_if_needed()
                pg.wait_for_timeout(500)
                cap(pg, hold)
            else:
                print("  !! 未找到小节:", heading)

        # 5) the site's other two tabs -- archive and search must not be lost
        pg.click("nav a:has-text('归档')")
        pg.wait_for_load_state("load"); pg.wait_for_timeout(1800)
        cap(pg, 1400)                       # 历史归档：按年/周
        scroll(pg, 140, 4)
        cap(pg, 1000)

        pg.click("nav a:has-text('搜索')")
        pg.wait_for_load_state("load")
        # the search index (search.json) is fetched client-side on load; give it
        # time before typing, or the results never render and we capture "正在搜索…"
        pg.wait_for_timeout(3000)
        cap(pg, 900)
        pg.click("#search-query")
        for ch in QUERY:
            pg.keyboard.type(ch)
            cap(pg, 80)
        pg.wait_for_timeout(4000)
        cap(pg, 1800)                       # hits, with highlighted matches
        scroll(pg, 120, 4)
        cap(pg, 1200)
        print("search query typed:", QUERY)

        # 6) back to this week -> open a paper -> its AI reading
        pg.click("nav a:has-text('本周')")
        pg.wait_for_load_state("load"); pg.wait_for_timeout(2000)
        cap(pg, 1300)
        card = pg.query_selector("a[href*='/papers/']")
        print("本周 card found:", bool(card))
        card.click()
        pg.wait_for_load_state("load"); pg.wait_for_timeout(2500)
        cap(pg, 1000)
        loc = pg.locator("h2", has_text="Paper Card").first
        if loc.count():
            loc.scroll_into_view_if_needed(); pg.wait_for_timeout(500)
        cap(pg, 1400)
        b.close()

    imgs = [f for f, _ in frames]
    durs = [d for _, d in frames]
    imgs[0].save(out, save_all=True, append_images=imgs[1:], duration=durs,
                 loop=0, optimize=True, disposal=2)
    print(f"frames={len(imgs)} duration={sum(durs)/1000:.1f}s -> {out}")


main()
