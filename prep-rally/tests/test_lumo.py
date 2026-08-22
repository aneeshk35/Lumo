#!/usr/bin/env python3
"""End-to-end tests for Lumo.

Run the server first, then:
    python3 -m playwright install chromium      # once
    python3 tests/test_lumo.py                  # against http://localhost:3000

Each test prints PASS/FAIL and the script exits non-zero if anything fails.
Multiplayer tests use separate browser contexts so the two players don't share
localStorage (same-origin tabs otherwise share one profile).
"""

import os
import sys
import time

from playwright.sync_api import sync_playwright

BASE = os.environ.get("LUMO_URL", "http://localhost:3000")
results = []


def check(name, condition, detail=""):
    results.append((name, bool(condition), detail))
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail and not condition else ""))
    return bool(condition)


def new_player(browser, name):
    """Fresh context with a pre-seeded profile, so the name modal is skipped."""
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    page.add_init_script(
        f"localStorage.setItem('lumo-profile', JSON.stringify({{name: {name!r}}}))"
    )
    page.goto(BASE)
    page.wait_for_selector(".sb-item")
    return ctx, page


def nav(page, item):
    page.click(f'.sb-item[data-navitem="{item}"]')
    page.wait_for_timeout(350)


def answer_current(page, choice=0):
    """Pick a choice and lock it in; returns True if an answer was submitted."""
    btn = page.locator(f'#choice-grid .mchoice[data-i="{choice}"]')
    if btn.count() == 0:
        return False
    btn.click()
    page.wait_for_timeout(120)
    lock = page.locator("#btn-lock")
    if lock.is_enabled():
        lock.click()
        return True
    return False


def play_session(page, max_q=30, choice=0):
    """Answer through a whole session until the results screen appears."""
    for _ in range(max_q):
        if page.locator("#v-results.active").count():
            return True
        answer_current(page, choice)
        try:
            page.wait_for_selector("#reveal-card:not(.hidden)", timeout=8000)
        except Exception:
            return page.locator("#v-results.active").count() > 0
        nxt = page.locator("#btn-next")
        if nxt.is_visible():
            nxt.click()
            page.wait_for_timeout(500)
        else:
            page.wait_for_timeout(1200)  # duel auto-advance
    return page.locator("#v-results.active").count() > 0


# --------------------------------------------------------------------------
def test_first_run(browser):
    print("\n1. First run and identity")
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE)
    check("name modal shown on first visit", page.locator("#name-overlay:not(.hidden)").count() == 1)
    page.fill("#name-input", "Aneesh")
    page.click("#btn-save-name")
    page.wait_for_timeout(300)
    check("modal closes after saving a name", page.locator("#name-overlay.hidden").count() == 1)
    check("greeting uses the name", "Aneesh" in page.inner_text("#greet-name"))
    check("sidebar identifies the player",
          "Aneesh" in page.get_attribute("#btn-user", "aria-label"))
    check("no page errors on boot", not errors, str(errors))
    ctx.close()


def test_navigation(browser):
    print("\n2. Every sidebar destination")
    ctx, page = new_player(browser, "Aneesh")
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    items = page.eval_on_selector_all(".sb-item", "els => els.map(e => e.dataset.navitem)")
    check("all 10 nav items render", len(items) == 10, f"got {len(items)}")
    check("no dead roadmap stubs in nav",
          not ({"Apply As A Tutor", "Ask Lumo AI", "My Classes"} & set(items)), str(items))
    gaps = page.evaluate("""() => {
        const ys = [...document.querySelectorAll('.sb-item')].map(b => Math.round(b.getBoundingClientRect().y));
        return ys.slice(1).map((y, i) => y - ys[i]); }""")
    # sub-pixel layout rounding means gaps land within a pixel of each other
    check("rail spacing is uniform", max(gaps) - min(gaps) <= 2, str(gaps))
    # labels exist for screen readers but must stay invisible until hover
    check("rail shows no text at rest", page.evaluate("""() => {
        const tips = [...document.querySelectorAll('.sb-item .sb-tip')];
        return tips.length === 10 && tips.every(t => getComputedStyle(t).opacity === '0'); }"""))
    for item in items:
        if item in ("Challenge Questions", "Full-Length Tests"):
            continue  # these launch games, covered separately
        nav(page, item)
        active = page.eval_on_selector_all(
            ".view.active", "els => els.map(e => e.id)")
        check(f"{item} opens one view", len(active) == 1, f"active={active}")
    check("no page errors while navigating", not errors, str(errors))
    ctx.close()


def test_question_bank(browser):
    print("\n3. Question Bank")
    ctx, page = new_player(browser, "Aneesh")
    nav(page, "Question Bank")
    page.wait_for_selector(".bank-card")
    total = page.inner_text("#bank-total")
    check("bank reports its size", total.replace(",", "").isdigit() and int(total.replace(",", "")) >= 128, total)
    check("8 domain cards", page.locator(".bank-card").count() == 8)
    check("reading and math split 4/4",
          page.locator("#bank-rw .bank-card").count() == 4 and
          page.locator("#bank-math .bank-card").count() == 4)

    page.click('#bank-diff .seg-btn[data-diff="hard"]')
    page.click('#bank-count .seg-btn[data-count="5"]')
    page.click('[data-bank-domain="Algebra"]')
    page.wait_for_selector("#v-match.active", timeout=8000)
    check("domain practice launches", page.locator("#v-match.active").count() == 1)
    check("respects the 5-question setting", "of 5" in page.inner_text("#match-progress"),
          page.inner_text("#match-progress"))
    check("respects the hard filter", "hard" in page.inner_text("#q-kicker").lower(),
          page.inner_text("#q-kicker"))
    check("labelled as a bank drill", "BANK" in page.inner_text("#match-mode"))
    ctx.close()


def test_solo_and_mistakes(browser):
    print("\n4. Solo session, mistake log, and review")
    ctx, page = new_player(browser, "Aneesh")
    nav(page, "Question Bank")
    page.wait_for_selector(".bank-card")
    page.click('#bank-count .seg-btn[data-count="5"]')
    page.click('[data-bank-domain="Algebra"]')
    page.wait_for_selector("#v-match.active", timeout=8000)

    finished = play_session(page, max_q=8, choice=0)
    check("session reaches the results screen", finished)
    check("results show a score line", len(page.inner_text("#result-sub")) > 0)

    mistakes = page.evaluate("JSON.parse(localStorage.getItem('lumo-profile')).mistakes.length")
    check("missed questions were logged", mistakes > 0, f"{mistakes} logged")

    nav(page, "Saved & Mistakes")
    check("mistake rows render", page.locator(".mistake").count() == mistakes)
    check("weakest domain identified", page.inner_text("#mk-weak") != "—")

    # Review them, answering correctly using the stored answer keys.
    key = page.evaluate(
        "Object.fromEntries(JSON.parse(localStorage.getItem('lumo-profile'))"
        ".mistakes.map(m => [m.id, m.correctIndex]))")
    page.click("#btn-review-all")
    page.wait_for_selector("#v-match.active", timeout=8000)
    check("review session launches", "REVIEW" in page.inner_text("#match-mode"))

    for _ in range(len(key) + 1):
        if page.locator("#v-results.active").count():
            break
        qid = page.evaluate("game.currentQ && game.currentQ.id")
        answer_current(page, key.get(qid, 0))
        try:
            page.wait_for_selector("#reveal-card:not(.hidden)", timeout=8000)
        except Exception:
            break
        nxt = page.locator("#btn-next")
        if nxt.is_visible():
            nxt.click()
            page.wait_for_timeout(500)

    left = page.evaluate("JSON.parse(localStorage.getItem('lumo-profile')).mistakes.length")
    check("correct answers retire mistakes", left == 0, f"{left} left")
    retry = page.evaluate("JSON.parse(localStorage.getItem('lumo-profile')).retryTotal")
    check("retry accuracy is tracked", retry > 0, f"retryTotal={retry}")
    ctx.close()


def test_planner_and_vocab(browser):
    print("\n5. Study Planner and Vocab")
    ctx, page = new_player(browser, "Aneesh")
    nav(page, "Study Planner")
    check("plan has tasks", page.locator("#planner-tasks .task").count() >= 5)
    before = page.inner_text("#planner-lbl")
    page.click("[data-plan-check]")
    page.wait_for_timeout(250)
    check("checking a task updates progress", page.inner_text("#planner-lbl") != before,
          f"{before} -> {page.inner_text('#planner-lbl')}")
    badge = page.locator('.sb-item[data-navitem="Study Planner"] .sb-badge')
    check("sidebar badge reflects open tasks", badge.count() == 1 and badge.inner_text() == "4",
          badge.inner_text() if badge.count() else "no badge")
    page.click("#btn-reset-plan")
    page.wait_for_timeout(200)
    check("uncheck all resets progress", "0 /" in page.inner_text("#planner-lbl"))
    page.click("#btn-regen-plan")
    page.wait_for_timeout(250)
    check("rebuild plan works", page.locator("#planner-tasks .task").count() >= 5)

    nav(page, "Vocab")
    page.wait_for_timeout(500)
    first = page.inner_text("#vc-word")
    check("a word is shown", len(first) > 0)
    page.click("#vocab-card")
    page.wait_for_timeout(200)
    check("card flips to the definition", page.locator("#vocab-back:not(.hidden)").count() == 1)
    check("definition is not empty", len(page.inner_text("#vc-def")) > 0)
    page.click("#vc-next")
    page.wait_for_timeout(250)
    check("next shows a different word", page.inner_text("#vc-word") != first)
    page.click("#vc-known")
    page.wait_for_timeout(250)
    known = page.evaluate("JSON.parse(localStorage.getItem('lumo-profile')).vocabKnown.length")
    check("marking known persists", known == 1, f"{known} known")
    ctx.close()


def test_search(browser):
    print("\n6. Search")
    ctx, page = new_player(browser, "Aneesh")
    page.fill("#search-input", "triangle")
    page.press("#search-input", "Enter")
    page.wait_for_selector("#v-search.active", timeout=5000)
    hits = page.locator("#search-results .mistake").count()
    check("search returns results", hits > 0, f"{hits} hits")
    check("summary names the query", "triangle" in page.inner_text("#search-summary"))
    page.click("[data-search-id]")
    page.wait_for_selector("#v-match.active", timeout=8000)
    check("practising a search hit starts a session", "SEARCH" in page.inner_text("#match-mode"))

    page.goto(BASE)
    page.wait_for_selector(".sb-item")
    page.fill("#search-input", "zzzznotathing")
    page.press("#search-input", "Enter")
    page.wait_for_timeout(600)
    check("empty search shows an empty state", page.locator(".empty-note").count() == 1)
    ctx.close()


def test_tools(browser):
    print("\n7. Calculator and highlighter")
    ctx, page = new_player(browser, "Aneesh")

    cases = [("2+3*4", 14), ("2^10", 1024), ("sqrt(49)", 7), ("3(4+1)", 15),
             ("log(1000)", 3), ("abs(-7)", 7), ("10/4", 2.5)]
    ok = page.evaluate(
        """cases => cases.every(([e, want]) => {
             try { return Math.abs(LumoCalc.compile(e).fn(0) - want) < 1e-9; }
             catch { return false; }
           })""", cases)
    check("calculator evaluates expressions correctly", ok)
    graphs = page.evaluate("() => { const c = LumoCalc.compile('y = 2x + 1'); return c.usesX && c.fn(3) === 7; }")
    check("calculator compiles graphable functions", graphs)

    # math question: calculator available, highlighter hidden
    page.evaluate("startPractice({section:'math', count:5}, 'Bank')")
    page.wait_for_selector("#v-match.active", timeout=8000)
    check("calculator offered on math", page.locator("#btn-calc:not(.hidden)").count() == 1)
    page.click("#btn-calc")
    check("calculator panel opens", page.locator("#calc-panel:not(.hidden)").count() == 1)

    # Desmos is fetched on first open; allow time, then accept either the real
    # calculator or the offline fallback — both are valid working states.
    for _ in range(40):
        if page.evaluate("desmos.state") != "loading":
            break
        page.wait_for_timeout(500)
    state = page.evaluate("desmos.state")
    check("calculator resolves to a working state", state in ("ready", "failed"), state)

    if state == "ready":
        check("real Desmos mounted", page.locator("#desmos-mount.ready").count() == 1)
        check("Desmos API is live", page.evaluate("typeof window.Desmos") == "object")
        check("fallback hidden while Desmos works",
              page.locator("#calc-fallback.hidden").count() == 1)
        page.evaluate("desmos.calc.setExpression({id:'t', latex:'y=2x^2-3'})")
        page.wait_for_timeout(600)
        exprs = page.evaluate("desmos.calc.getExpressions().length")
        check("Desmos accepts an expression", exprs >= 1, f"{exprs} expressions")
    else:
        page.fill("#calc-input", "2x^2 - 3")
        page.wait_for_timeout(400)
        painted = page.evaluate("""() => {
            const cv = document.getElementById('calc-graph');
            const d = cv.getContext('2d').getImageData(0,0,cv.width,cv.height).data;
            let n = 0; for (let i=0;i<d.length;i+=4) if (d[i]>90 && d[i]<130 && d[i+2]>190) n++;
            return n; }""")
        check("fallback graph is drawn", painted > 200, f"{painted} curve pixels")

    # reading question: highlighter available, calculator hidden
    page.evaluate("teardownGame(); startPractice({section:'rw', domains:['Information and Ideas'], count:5}, 'Bank')")
    page.wait_for_selector("#v-match.active", timeout=8000)
    page.wait_for_timeout(400)
    check("calculator hidden on reading", page.locator("#btn-calc.hidden").count() == 1)
    check("highlighter offered on passages", page.locator("#btn-highlight:not(.hidden)").count() == 1)
    page.click("#btn-highlight")
    page.evaluate("""() => {
        const p = document.getElementById('q-passage');
        const r = document.createRange();
        r.setStart(p.firstChild, 0); r.setEnd(p.firstChild, 30);
        const s = getSelection(); s.removeAllRanges(); s.addRange(r);
        document.dispatchEvent(new MouseEvent('mouseup')); }""")
    page.wait_for_timeout(250)
    check("selection becomes a highlight", page.locator("#q-passage mark").count() == 1)
    ctx.close()


def test_party(browser):
    print("\n8. Multiplayer — party codes")
    host_ctx, host = new_player(browser, "HostPlayer")
    join_ctx, guest = new_player(browser, "GuestPlayer")

    nav(host, "Play")
    host.click("#btn-host-party")
    host.wait_for_selector("#v-lobby.active", timeout=8000)
    code = host.inner_text("#lobby-code").strip()
    check("host gets a 5-letter code", len(code) == 5, code)

    nav(guest, "Play")
    guest.fill("#code-input", code)
    guest.click("#btn-join-party")
    guest.wait_for_selector("#v-lobby.active", timeout=8000)
    guest.wait_for_timeout(600)
    names = host.eval_on_selector_all("#lobby-players .player-card .n", "els => els.map(e => e.innerText)")
    check("both players appear in the lobby", len(names) == 2, str(names))

    host.click("#btn-ready")  # host starts
    host.wait_for_selector("#v-match.active", timeout=8000)
    guest.wait_for_selector("#v-match.active", timeout=8000)
    check("both players enter the match", True)
    check("same question for both",
          host.inner_text("#q-text") == guest.inner_text("#q-text"))

    answer_current(host, 0)
    answer_current(guest, 1)
    host.wait_for_selector("#reveal-card:not(.hidden)", timeout=8000)
    check("reveal reaches the host", host.locator("#reveal-card:not(.hidden)").count() == 1)
    bars = host.locator("#hth .hth-side").count()
    check("head-to-head shows both players", bars == 2, f"{bars} bars")
    join_ctx.close()
    host_ctx.close()


def test_duel(browser):
    print("\n9. Multiplayer — ranked duel matchmaking")
    a_ctx, a = new_player(browser, "DuelA")
    b_ctx, b = new_player(browser, "DuelB")

    nav(a, "Play")
    a.click("#btn-find-match")
    a.wait_for_selector("#v-queue.active", timeout=5000)
    check("first player enters the queue", a.locator("#v-queue.active").count() == 1)

    nav(b, "Play")
    b.click("#btn-find-match")
    b.wait_for_selector("#v-lobby.active", timeout=8000)
    a.wait_for_selector("#v-lobby.active", timeout=10000)
    check("both players matched into a duel lobby", True)
    check("lobby names the mode", "Duel" in a.inner_text("#lobby-title"), a.inner_text("#lobby-title"))

    a.click("#btn-ready")
    b.click("#btn-ready")
    a.wait_for_selector("#v-match.active", timeout=8000)
    b.wait_for_selector("#v-match.active", timeout=8000)
    check("ready-up starts the duel", True)
    check("duel labelled correctly", "DUEL" in a.inner_text("#match-mode"))
    check("identical question for both", a.inner_text("#q-text") == b.inner_text("#q-text"))

    answer_current(a, 0)
    answer_current(b, 1)
    a.wait_for_selector("#reveal-card:not(.hidden)", timeout=8000)
    check("duel reveal auto-advances", "in" in a.inner_text("#reveal-note").lower(),
          a.inner_text("#reveal-note"))
    b_ctx.close()
    a_ctx.close()


def test_responsive(browser):
    print("\n10. Mobile layout")
    ctx = browser.new_context(viewport={"width": 375, "height": 812},
                              user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)")
    page = ctx.new_page()
    page.add_init_script("localStorage.setItem('lumo-profile', JSON.stringify({name:'Aneesh'}))")
    page.goto(BASE)
    page.wait_for_selector(".sb-item")

    # nav should sit at the top, above the content
    box = page.locator(".sidebar").bounding_box()
    check("nav is a top bar, not a side rail", box["y"] < 60 and box["width"] > 300,
          f"y={box['y']} w={box['width']}")
    check("nav is compact", box["height"] < 130, f"height={box['height']}")
    check("group headings hidden for minimalism",
          page.locator(".sb-label:visible").count() == 0)
    check("second banner hidden on mobile", page.locator("#announce-bar:visible").count() == 0)

    for item in ["Question Bank", "Saved & Mistakes", "Study Planner", "Vocab", "Play", "Home"]:
        nav(page, item)
        overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
        check(f"{item} has no horizontal scroll", not overflow)
    ctx.close()


def main():
    print(f"Lumo end-to-end tests against {BASE}")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for fn in (test_first_run, test_navigation, test_question_bank,
                   test_solo_and_mistakes, test_planner_and_vocab, test_search,
                   test_tools, test_party, test_duel, test_responsive):
            try:
                fn(browser)
            except Exception as exc:  # a crash in one group shouldn't hide the rest
                results.append((f"{fn.__name__} crashed", False, str(exc)[:300]))
                print(f"  [FAIL] {fn.__name__} crashed — {str(exc)[:300]}")
        browser.close()

    passed = sum(1 for _, ok, _ in results if ok)
    failed = [(n, d) for n, ok, d in results if not ok]
    print(f"\n{'=' * 60}\n{passed}/{len(results)} checks passed")
    if failed:
        print("\nFailures:")
        for name, detail in failed:
            print(f"  - {name}" + (f": {detail}" if detail else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
