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
    # Seed only on the first load. add_init_script runs on every navigation, so
    # overwriting unconditionally would wipe the profile on each reload and make
    # persistence impossible to test.
    page.add_init_script(
        "if (!localStorage.getItem('lumo-profile'))"
        f" localStorage.setItem('lumo-profile', JSON.stringify({{name: {name!r}}}))"
    )
    page.goto(BASE)
    page.wait_for_selector(".sb-item")
    return ctx, page


def nav(page, item):
    """Reach a destination the way a user does: rail picks the section, the tab
    row inside the page picks the screen. Single-screen sections have no tabs."""
    group = page.evaluate(
        "(n) => (NAV.find((g) => g.items.some((i) => i.name === n)) || {}).name", item)
    assert group, f"no nav section contains {item!r}"
    if page.locator("#v-match.active").count():
        # the test screen is full-window like the real SAT; leave through Exit
        page.once("dialog", lambda d: d.accept())
        page.click("#btn-exit-test")
        page.wait_for_timeout(300)
    page.click(f'.sb-item[data-navgroup="{group}"]')
    page.wait_for_timeout(250)
    tab = page.locator(f'.view.active .subnav-tab[data-navitem="{item}"]')
    if tab.count():
        tab.click()
    page.wait_for_timeout(350)


def answer_current(page, choice=0):
    """Pick a choice and lock it in; returns True if an answer was submitted.
    Typed-answer (grid-in) questions get a deliberately wrong number, since
    untimed practice waits for an answer instead of timing out."""
    if page.locator("#spr:not(.hidden)").count():
        page.fill("#spr-input", choice if isinstance(choice, str) else "-9999")
        page.wait_for_timeout(120)
        page.click("#btn-lock")
        return True
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
    check("first visit offers a new account first",
          "Create account" in page.inner_text("#btn-save-name"), page.inner_text("#btn-save-name"))
    page.click('[data-acct-tab="guest"]')
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
    rail = page.eval_on_selector_all(".sb-item", "els => els.map(e => e.dataset.navgroup)")
    items = page.evaluate("NAV.flatMap(g => g.items).map(i => i.name)")
    check("rail renders one button per section",
          rail == page.evaluate("NAV.map(g => g.name)"), f"got {rail}")
    check("rail stays short enough to scan", len(rail) <= 7, f"{len(rail)} rail buttons")
    check("every destination is reachable from a section",
          all(page.evaluate("(n) => !!NAV.find(g => g.items.some(i => i.name === n))", n)
              for n in items), str(items))
    # The rail must not carry links that go nowhere. Rather than naming
    # screens, assert structurally that nothing routes to a placeholder.
    check("no dead links in nav",
          page.evaluate("NAV.flatMap(g => g.items).every(i => i.view && i.view !== 'soon')"),
          str(items))
    gaps = page.evaluate("""() => {
        const ys = [...document.querySelectorAll('.sb-item')].map(b => Math.round(b.getBoundingClientRect().y));
        return ys.slice(1).map((y, i) => y - ys[i]); }""")
    # sub-pixel layout rounding means gaps land within a pixel of each other
    check("rail spacing is uniform", max(gaps) - min(gaps) <= 2, str(gaps))
    # labels exist for screen readers but must stay invisible until hover
    check("rail shows no text at rest", page.evaluate("""() => {
        const items = document.querySelectorAll('.sb-item');
        const tips = [...document.querySelectorAll('.sb-item .sb-tip')];
        return tips.length === items.length && tips.every(t => getComputedStyle(t).opacity === '0'); }"""))
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
        ".mistakes.map(m => [m.id, m.type === 'spr' ? m.correctAnswer : m.correctIndex]))")
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
    badge = page.locator('.sb-item[data-navgroup="Progress"] .sb-badge')
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


def test_duel_difficulty(browser):
    print("\n9b. Duels by difficulty and per-difficulty Elo")
    a_ctx, a = new_player(browser, "HardA")
    b_ctx, b = new_player(browser, "EasyB")

    def queue(page, section, difficulty):
        nav(page, "Play")
        page.click(f'#duel-modes [data-sec="{section}"]')
        page.click(f'#duel-diffs [data-diff="{difficulty}"]')
        page.click("#btn-find-match")

    queue(a, "math", "hard")
    a.wait_for_selector("#v-queue.active", timeout=5000)
    check("queue chip names the difficulty", "Hard" in a.inner_text("#queue-mode-chip"), a.inner_text("#queue-mode-chip"))
    queue(b, "math", "easy")
    b.wait_for_selector("#v-queue.active", timeout=5000)
    b.wait_for_timeout(2500)
    check("different difficulties are not paired",
          a.locator("#v-queue.active").count() == 1 and b.locator("#v-queue.active").count() == 1)

    b.click("#btn-queue-cancel")
    b.wait_for_timeout(400)
    queue(b, "math", "hard")
    b.wait_for_selector("#v-lobby.active", timeout=8000)
    a.wait_for_selector("#v-lobby.active", timeout=10000)
    check("same difficulty pairs up", True)
    check("lobby title names the difficulty", "Hard" in a.inner_text("#lobby-title"), a.inner_text("#lobby-title"))
    check("lobby shows both ratings", a.inner_text("#lobby-players").count("ELO") == 2, a.inner_text("#lobby-players"))

    a.click("#btn-ready")
    b.click("#btn-ready")
    a.wait_for_selector("#v-match.active", timeout=8000)
    check("hard duel serves hard questions", "hard" in a.inner_text("#q-kicker").lower(), a.inner_text("#q-kicker"))

    elos = a.evaluate("""() => {
        const before = { ...profile.elos };
        const delta = applyElo('hard', 1400, 1);   // beat a higher-rated player
        return { before, after: { ...profile.elos }, delta };
    }""")
    check("beating a stronger player gains Elo on that ladder only",
          elos["delta"] == 24 and elos["after"]["hard"] == elos["before"]["hard"] + 24
          and elos["after"]["easy"] == elos["before"]["easy"], str(elos))
    b_ctx.close()
    a_ctx.close()


def test_practice_and_grid_in(browser):
    print("\n9c. Untimed practice, typed answers, and Elo")
    ctx, page = new_player(browser, "Gridder")
    page.on("dialog", lambda d: d.accept())
    elo_before = page.evaluate("JSON.stringify(profile.elos)")

    def practice(qid):
        page.evaluate(f"startPractice({{ ids: ['{qid}'], count: 1 }}, 'Test')")
        page.wait_for_selector("#v-match.active", timeout=8000)
        page.wait_for_timeout(400)

    practice("mth-0056")   # slope of a perpendicular line: 5/6
    check("practice shows no countdown", page.locator("#match-timer.hidden").count() == 1
          and page.locator("#tb-untimed:not(.hidden)").count() == 1)
    check("typed-answer box replaces the choices", page.locator("#spr:not(.hidden)").count() == 1
          and page.locator("#choice-grid.hidden").count() == 1)
    bg = lambda: page.evaluate("getComputedStyle(document.getElementById('v-match')).backgroundColor")
    before = bg()
    page.click("#btn-test-theme")
    page.wait_for_timeout(200)
    check("the test screen has its own light/dark switch", bg() != before, f"{before} -> {bg()}")
    page.click("#btn-test-theme")
    page.wait_for_timeout(200)
    page.fill("#spr-input", "5/6x")
    check("letters are stripped from typed answers", page.input_value("#spr-input") == "5/6", page.input_value("#spr-input"))
    page.fill("#spr-input", ".833")
    page.click("#btn-lock")
    page.wait_for_selector("#reveal-card:not(.hidden)", timeout=8000)
    check("a rounded decimal equal to the fraction is correct", "Correct" in page.inner_text("#reveal-title"), page.inner_text("#reveal-title"))
    check("practice pays full points with no speed factor", page.evaluate("game.myScore") == 750, str(page.evaluate("game.myScore")))
    check("practice hides the score and the answered count",
          page.locator("#tb-score.hidden").count() == 1 and page.locator("#locked-note.hidden").count() == 1)

    page.wait_for_timeout(1200)
    practice("mth-0006")   # answer is -9
    page.fill("#spr-input", "9")
    page.click("#btn-lock")
    page.wait_for_selector("#reveal-card:not(.hidden)", timeout=8000)
    check("a wrong typed answer shows the right one", "−9" in page.inner_text("#reveal-title"), page.inner_text("#reveal-title"))
    page.wait_for_timeout(1500)
    check("practice never changes Elo", page.evaluate("JSON.stringify(profile.elos)") == elo_before)

    # "More like this" builds a fresh set on the same skill
    practice("geo-033")
    answer_current(page, 0)
    page.wait_for_selector("#reveal-card:not(.hidden)", timeout=8000)
    check("practice offers More like this", page.locator("#reveal-more:not(.hidden)").count() == 1)
    page.click("#btn-similar")
    page.wait_for_timeout(1800)
    same = page.evaluate("game.currentQ && game.currentQ.skill")
    check("More like this starts a same-skill set", same == "Similar triangles" and "of 5" in page.inner_text("#match-progress"),
          f"{same} / {page.inner_text('#match-progress')}")
    check("math copies are newly generated", page.evaluate("game.currentQ.id").startswith("var-"), page.evaluate("game.currentQ.id"))
    ctx.close()


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


def test_theme(browser):
    print("\n17. Light and dark")
    ctx, page = new_player(browser, "Aneesh")

    def bg():
        return page.evaluate("getComputedStyle(document.body).backgroundColor")

    light_bg = bg()
    check("starts light when the OS is light", page.evaluate("!!document.documentElement.dataset.theme") is False
          or page.evaluate("document.documentElement.dataset.theme") == "light", light_bg)
    page.click("#btn-theme")
    page.wait_for_timeout(200)
    dark_bg = bg()
    check("the toggle switches to dark",
          page.evaluate("document.documentElement.dataset.theme") == "dark" and dark_bg != light_bg,
          f"{light_bg} -> {dark_bg}")
    check("the choice is remembered",
          page.evaluate("localStorage.getItem('lumo-theme')") == "dark")
    # Anything readable must stay readable: the rail tooltip and the match timer
    # both paint white text on --ink, which inverts in dark mode.
    tip = page.evaluate("""() => {
        const t = document.querySelector('.sb-tip');
        const cs = getComputedStyle(t);
        return [cs.color, cs.backgroundColor]; }""")
    check("rail tooltip is not white on white", tip[0] != tip[1], str(tip))
    page.reload()
    page.wait_for_selector(".sb-item")
    check("dark survives a reload",
          page.evaluate("document.documentElement.dataset.theme") == "dark")
    page.click("#btn-theme")
    page.wait_for_timeout(200)
    check("the toggle switches back to light",
          page.evaluate("document.documentElement.dataset.theme") == "light" and bg() == light_bg)
    ctx.close()


def test_masterclass(browser):
    print("\n11. Masterclass lessons")
    ctx, page = new_player(browser, "Aneesh")
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    nav(page, "Reading & Writing")
    page.wait_for_selector(".mc-card", timeout=8000)
    rw_cards = page.locator(".mc-card").count()
    check("Reading & Writing lists its lessons", rw_cards == 11, f"{rw_cards} cards")
    check("grouped by domain", page.locator(".mc-group").count() == 4,
          f"{page.locator('.mc-group').count()} groups")
    check("progress starts at zero", "0%" in page.inner_text("#mc-ring-num"))

    nav(page, "Math & Desmos")
    page.wait_for_selector(".mc-card", timeout=8000)
    math_cards = page.locator(".mc-card").count()
    check("Math & Desmos lists its lessons", math_cards == 16, f"{math_cards} cards")
    domains = page.eval_on_selector_all(".mc-domain", "els => els.map(e => e.innerText)")
    check("Desmos gets its own group, sorted last",
          domains and domains[-1] == "Desmos", str(domains))

    # open a lesson and work its example
    page.click(".mc-card")
    page.wait_for_selector("#v-lesson.active", timeout=8000)
    check("lesson reader opens", len(page.inner_text("#lesson-title")) > 0)
    check("lesson has a method block", page.locator(".lb-steps, .lb-desmos").count() >= 1)
    check("lesson has a worked example", page.locator(".lb-example").count() == 1)
    check("walkthrough hidden before answering", page.locator("#lb-walk.hidden").count() == 1)

    answer = page.evaluate(
        "currentLesson.blocks.find(b => b.type === 'example').answer")
    page.click(f'.lb-choice[data-ex-choice="{answer}"]')
    page.wait_for_timeout(300)
    check("answering reveals the walkthrough", page.locator("#lb-walk:not(.hidden)").count() == 1)
    check("correct choice is marked right", page.locator(".lb-choice.correct").count() == 1)
    check("choices lock after answering",
          page.eval_on_selector_all(".lb-choice", "els => els.every(e => e.disabled)"))

    page.click("#lesson-complete")
    page.wait_for_timeout(250)
    done = page.evaluate("JSON.parse(localStorage.getItem('lumo-profile')).lessonsDone.length")
    check("marking complete persists", done == 1, f"{done} done")

    page.click("#lesson-back")
    page.wait_for_selector("#v-masterclass.active", timeout=5000)
    check("back returns to the right masterclass",
          "Math" in page.inner_text("#mc-title"), page.inner_text("#mc-title"))
    check("progress ring updates", page.inner_text("#mc-ring-num") != "0%",
          page.inner_text("#mc-ring-num"))
    check("completed card is ticked", page.locator(".mc-card.done").count() == 1)

    # drilling a lesson launches a real session from the bank
    page.click(".mc-card.done")
    page.wait_for_selector("#v-lesson.active", timeout=5000)
    page.click("#lesson-drill")
    page.wait_for_selector("#v-match.active", timeout=8000)
    check("drill this skill starts a session", page.locator("#v-match.active").count() == 1)
    check("no page errors in the masterclass", not errors, str(errors))
    ctx.close()


def test_coach(browser):
    print("\n12. Ask Lumo")
    ctx, page = new_player(browser, "Aneesh")
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    nav(page, "Ask Lumo")
    page.wait_for_timeout(500)
    check("greeting card renders", page.locator(".coach-card").count() >= 1)
    check("suggested chips offered", page.locator(".coach-chip").count() >= 3)

    def ask(q):
        page.fill("#coach-input", q)
        page.click("#coach-send")
        page.wait_for_timeout(700)
        return page.locator(".coach-card").last.inner_text()

    a = ask("How do transitions work?")
    check("finds the transitions lesson", "Transitions" in a, a[:80])
    check("offers to open the lesson and drill it",
          "Read the full lesson" in a and "Drill" in a, a[:120])

    a = ask("what does ambivalent mean")
    check("answers a vocab word from the deck", "mixed or conflicting" in a.lower(), a[:80])

    a = ask("explain quadratic vertex")
    check("prefers the concept lesson over the Desmos one",
          "Quadratics" in a and "Desmos move" not in a, a[:80])

    a = ask("how do i use desmos")
    check("still routes calculator questions to Desmos", "Desmos" in a, a[:80])

    a = ask("qwertyzxcvbnm")
    check("says so when it has nothing", "don't have anything solid" in a, a[:80])

    a = ask("what should I study next")
    check("study advice is grounded in real data",
          "Not enough data" in a or "worst first" in a, a[:80])

    # an action button actually does something
    page.locator(".coach-card").last.locator("[data-act]").first.click()
    page.wait_for_timeout(900)
    check("answer actions are wired",
          page.locator("#v-match.active, #v-analytics.active, #v-mistakes.active").count() == 1)
    check("no page errors in the coach", not errors, str(errors))
    ctx.close()


def test_tutor(browser):
    print("\n13. Apply As A Tutor")
    ctx, page = new_player(browser, "Aneesh")
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    nav(page, "Apply As A Tutor")
    page.wait_for_timeout(500)
    check("eligibility checklist renders", page.locator(".elig").count() == 3)
    check("form is shown before applying",
          page.locator("#tutor-form-wrap:not(.hidden)").count() == 1)
    check("nickname pre-fills the name", page.input_value("#tf-name") == "Aneesh")

    def submit():
        page.evaluate("document.getElementById('tutor-form')"
                      ".dispatchEvent(new Event('submit', {cancelable:true, bubbles:true}))")
        page.wait_for_timeout(350)
        return page.inner_text("#tf-error")

    page.fill("#tf-email", "nope")
    check("rejects a malformed email", "valid email" in submit())
    page.fill("#tf-email", "aneesh@example.com")
    check("requires a subject", "at least one subject" in submit())
    page.check('#tf-subjects input[value="Math"]')
    page.fill("#tf-about", "too short")
    check("requires a real answer", "more character" in submit())

    page.fill("#tf-about", "I have worked through most of the bank and I like breaking a hard "
                           "question down into the smallest step that still makes sense.")
    check("accepts a complete application", submit() == "")
    page.wait_for_timeout(600)
    check("status card replaces the form",
          page.locator("#tutor-status-card:not(.hidden)").count() == 1)
    check("status names the review state", "review" in page.inner_text("#ts-title").lower())
    check("submitted details are shown back", page.locator(".ts-cell").count() >= 5)

    # the application survives a reload, because it lives on the server
    page.reload()
    page.wait_for_selector(".sb-item")
    nav(page, "Apply As A Tutor")
    page.wait_for_timeout(600)
    check("application persists across a reload",
          page.locator("#tutor-status-card:not(.hidden)").count() == 1)

    page.on("dialog", lambda d: d.accept())
    page.click("#btn-tutor-withdraw")
    page.wait_for_timeout(700)
    check("withdrawing brings the form back",
          page.locator("#tutor-form-wrap:not(.hidden)").count() == 1)
    check("no page errors in the tutor flow", not errors, str(errors))
    ctx.close()


def test_classes(browser):
    print("\n14. My Classes")
    t_ctx, teacher = new_player(browser, "MsRivera")
    s_ctx, student = new_player(browser, "Sam")
    errors = []
    teacher.on("pageerror", lambda e: errors.append(str(e)))
    student.on("pageerror", lambda e: errors.append(str(e)))

    nav(teacher, "My Classes")
    teacher.wait_for_timeout(400)
    check("empty state before any class", teacher.locator(".empty-note").count() == 1)
    teacher.fill("#class-new-name", "Period 3 SAT Prep")
    teacher.click("#btn-class-create")
    teacher.wait_for_selector("#class-detail:not(.hidden)", timeout=8000)
    code = teacher.inner_text("#cd-code").strip()
    check("teacher gets a 5-letter class code", len(code) == 5, code)
    check("teacher tools are shown",
          teacher.locator("#cd-teacher-tools:not(.hidden)").count() == 1)
    check("domain dropdown is populated",
          teacher.eval_on_selector("#cd-assign-domain", "el => el.options.length") == 9)

    # student joins
    nav(student, "My Classes")
    student.wait_for_timeout(400)
    student.fill("#class-join-code", code)
    student.click("#btn-class-join")
    student.wait_for_selector("#class-detail:not(.hidden)", timeout=8000)
    check("student joins with the code", "Period 3" in student.inner_text("#cd-name"))
    check("student does not see teacher tools",
          student.locator("#cd-teacher-tools.hidden").count() == 1)

    # teacher sees the roster fill in
    teacher.click("#class-back")
    teacher.wait_for_timeout(300)
    teacher.click("[data-class]")
    teacher.wait_for_selector("#class-detail:not(.hidden)", timeout=8000)
    names = teacher.eval_on_selector_all("#cd-roster .roster-row:not(.head) .rn",
                                         "els => els.map(e => e.innerText)")
    check("roster shows the student", any("Sam" in n for n in names), str(names))

    # teacher sets an assignment
    teacher.fill("#cd-assign-name", "Algebra warm-up")
    teacher.select_option("#cd-assign-domain", "Algebra")
    teacher.select_option("#cd-assign-count", "5")
    teacher.click("#cd-assign-save")
    teacher.wait_for_timeout(700)
    check("assignment is set", "Algebra warm-up" in teacher.inner_text("#cd-assign-title"))

    # student sees it and plays it
    student.click("#class-back")
    student.wait_for_timeout(300)
    student.click("[data-class]")
    student.wait_for_selector("#class-detail:not(.hidden)", timeout=8000)
    check("student sees the assignment",
          "Algebra warm-up" in student.inner_text("#cd-assign-title"))
    student.click("#cd-assign-start")
    student.wait_for_selector("#v-match.active", timeout=8000)
    check("assignment launches the right set",
          "of 5" in student.inner_text("#match-progress"), student.inner_text("#match-progress"))
    play_session(student, max_q=8, choice=0)
    student.wait_for_timeout(900)

    # teacher refreshes and sees the work reported
    teacher.click("#class-back")
    teacher.wait_for_timeout(300)
    teacher.click("[data-class]")
    teacher.wait_for_selector("#class-detail:not(.hidden)", timeout=8000)
    row = teacher.inner_text("#cd-roster .roster-row:not(.head)")
    check("student progress reaches the teacher", "Done" in row, row.replace("\n", " "))
    attempted = teacher.eval_on_selector_all(
        "#cd-roster .roster-row:not(.head) .rv", "els => els[0].innerText")
    check("answered count is reported", attempted not in ("", "0"), f"attempted={attempted}")

    check("no page errors in classes", not errors, str(errors))
    s_ctx.close()
    t_ctx.close()


def test_friends(browser):
    print("\n15. Friends and invites")
    a_ctx, a = new_player(browser, "FriendA")
    b_ctx, b = new_player(browser, "FriendB")
    errors = []
    a.on("pageerror", lambda e: errors.append(str(e)))
    b.on("pageerror", lambda e: errors.append(str(e)))

    nav(a, "Play")
    nav(b, "Play")
    a.wait_for_timeout(1200)
    b.wait_for_timeout(1200)
    a_code = a.inner_text("#my-friend-code").strip()
    b_code = b.inner_text("#my-friend-code").strip()
    check("each player gets a 6-character friend code",
          len(a_code) == 6 and len(b_code) == 6 and a_code != b_code, f"{a_code} / {b_code}")
    check("friends list starts empty", a.locator("#friends-list .empty-note").count() == 1)

    b.fill("#friend-code-input", a_code)
    b.click("#btn-add-friend")
    b.wait_for_timeout(1200)
    check("adding by code works", b.locator("#friends-list .friend").count() == 1)
    check("friend shows as online", "Online" in b.inner_text("#friends-list .friend .s")
          or "Play" in b.inner_text("#friends-list .friend .s"),
          b.inner_text("#friends-list .friend .s"))

    # B challenges A; A picks the invite up on its next presence poll
    b.click("[data-challenge]")
    b.wait_for_selector("#v-lobby.active", timeout=8000)
    check("challenger lands in a lobby", b.locator("#v-lobby.active").count() == 1)
    a.evaluate("pingPresence()")
    a.wait_for_timeout(900)
    check("invite reaches the friend", a.locator("#invite-pop:not(.hidden)").count() == 1)
    check("invite names the challenger", "FriendB" in a.inner_text("#invite-title"),
          a.inner_text("#invite-title"))
    a.click("#invite-accept")
    a.wait_for_selector("#v-lobby.active", timeout=8000)
    b.wait_for_timeout(700)
    players = b.eval_on_selector_all("#lobby-players .player-card .n", "els => els.map(e => e.innerText)")
    check("both players are in the same lobby", len(players) == 2, str(players))

    # removing a friend
    b.evaluate("teardownGame()")
    nav(b, "Play")
    b.wait_for_timeout(600)
    b.click("[data-unfriend]")
    b.wait_for_timeout(400)
    check("removing a friend empties the list",
          b.locator("#friends-list .empty-note").count() == 1)
    check("no page errors in friends", not errors, str(errors))
    b_ctx.close()
    a_ctx.close()


def test_2v2(browser):
    print("\n16. 2v2 team duel")
    ctxs, pages = [], []
    for i in range(4):
        c, p = new_player(browser, f"Team{i + 1}")
        ctxs.append(c)
        pages.append(p)
    errors = []
    for p in pages:
        p.on("pageerror", lambda e: errors.append(str(e)))

    for p in pages:
        nav(p, "Play")
    pages[0].click("#btn-find-2v2")
    pages[0].wait_for_selector("#v-queue.active", timeout=8000)
    check("2v2 queue is labelled", "2v2" in pages[0].inner_text("#queue-kind"),
          pages[0].inner_text("#queue-kind"))
    pages[0].wait_for_timeout(1800)
    check("queue reports how many are still needed",
          "of 4" in pages[0].inner_text("#queue-waiting"),
          pages[0].inner_text("#queue-waiting"))

    for p in pages[1:]:
        p.click("#btn-find-2v2")
        p.wait_for_timeout(400)
    for p in pages:
        p.wait_for_selector("#v-lobby.active", timeout=15000)
    check("four players form a 2v2 lobby", True)
    check("lobby names the mode", "2v2" in pages[0].inner_text("#lobby-title"),
          pages[0].inner_text("#lobby-title"))
    check("two teams are shown", pages[0].locator(".team-block").count() == 2)
    roles = pages[0].eval_on_selector_all(".team-block .player-card .s",
                                          "els => els.map(e => e.innerText)")
    check("each team gets a Reading and a Math specialist",
          sorted(roles) == ["Math specialist", "Math specialist",
                            "Reading specialist", "Reading specialist"], str(roles))

    for p in pages:
        p.click("#btn-ready")
    for p in pages:
        p.wait_for_selector("#v-match.active", timeout=12000)
    check("all four ready-ups start the match", True)
    texts = [p.inner_text("#q-text") for p in pages]
    check("same question for all four", len(set(texts)) == 1)

    for i, p in enumerate(pages):
        answer_current(p, i % 4)
    pages[0].wait_for_selector("#reveal-card:not(.hidden)", timeout=10000)
    check("reveal reaches the team match",
          pages[0].locator("#reveal-card:not(.hidden)").count() == 1)
    check("2v2 auto-advances like a duel",
          "in" in pages[0].inner_text("#reveal-note").lower(),
          pages[0].inner_text("#reveal-note"))
    check("no page errors in 2v2", not errors, str(errors))
    for c in ctxs:
        c.close()


def test_bot_duel(browser):
    print("\n17. Bots fill an empty ranked queue")
    ctx, page = new_player(browser, "BotBait")
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    before = page.evaluate("profile.elos.easy")
    nav(page, "Play")
    page.click('#duel-modes [data-sec="rw"]')
    page.click('#duel-diffs [data-diff="easy"]')
    page.click("#btn-find-match")
    page.wait_for_selector("#v-queue.active", timeout=5000)
    page.wait_for_timeout(4000)
    check("no bot shows up right away", page.locator("#v-queue.active").count() == 1)
    page.wait_for_selector("#v-lobby.active", timeout=20000)
    check("a bot takes the seat when nobody else queues", True)
    check("the bot is labeled as a bot", page.locator("#lobby-players .bot-tag").count() == 1,
          page.inner_text("#lobby-players"))
    check("the lobby says why there's a bot", "bot" in page.inner_text("#lobby-sub").lower(),
          page.inner_text("#lobby-sub"))
    card = page.inner_text("#lobby-players")
    check("the bot is rated near the player", "ELO" in card, card)
    page.click("#btn-ready")
    page.wait_for_selector("#v-match.active", timeout=10000)
    check("the bot readies up on its own", True)
    answer_current(page, 0)
    page.wait_for_selector("#reveal-card:not(.hidden)", timeout=15000)
    check("the bot answers so the question reveals", True)
    # Duels auto-advance, so wait for each fresh question rather than clicking
    # through the reveal.
    for _ in range(12):
        page.wait_for_selector("#v-results.active, #choice-grid .mchoice:not([disabled]), #spr:not(.hidden)",
                               timeout=20000)
        if page.locator("#v-results.active").count():
            break
        answer_current(page, 1)
        page.wait_for_selector("#reveal-card:not(.hidden)", timeout=15000)
        page.wait_for_selector("#v-results.active, #reveal-card.hidden", state="attached", timeout=15000)
    finished = page.locator("#v-results.active").count() == 1
    check("a full match against a bot finishes", finished)
    check("results label the bot", page.locator("#result-rows .bot-tag").count() == 1)
    after = page.evaluate("profile.elos.easy")
    check("a bot match is ranked", after != before, f"{before} -> {after}")
    check("no page errors in a bot match", not errors, str(errors))
    ctx.close()


def test_accounts(browser):
    print("\n18. Accounts and saved progress")
    import random as _r
    user = f"tester{_r.randint(10000, 99999)}"
    pw = "correct-horse-9"

    # A guest with some progress makes an account; the progress comes along.
    a_ctx, a = new_player(browser, "Guesty")
    errors = []
    a.on("pageerror", lambda e: errors.append(str(e)))
    a.evaluate("profile.attempted = 7; profile.correct = 5; profile.elos.hard = 1333; saveProfile()")
    a.click("#btn-user")
    a.wait_for_selector("#name-overlay:not(.hidden)")
    check("guests can close the account window", a.locator("#btn-acct-close:not(.hidden)").count() == 1)
    a.fill("#acct-username", user)
    a.fill("#acct-password", "short")
    a.click("#btn-save-name")
    check("short passwords are refused", "8 characters" in a.inner_text("#acct-error"), a.inner_text("#acct-error"))
    a.fill("#acct-password", pw)
    a.click("#btn-save-name")
    a.wait_for_selector("#name-overlay.hidden", state="attached", timeout=8000)
    check("signing up closes the window", True)
    check("signed-in dot shows on the rail", a.locator("#btn-user.signed-in").count() == 1)
    check("the rail says who is signed in", user in a.get_attribute("#btn-user", "aria-label"),
          a.get_attribute("#btn-user", "aria-label"))

    # A change after signup reaches the server.
    a.evaluate("profile.attempted = 9; saveProfile()")
    a.wait_for_function("!JSON.parse(localStorage.getItem('lumo-account')).dirty", timeout=8000)
    check("progress saves to the account", True)

    # The same account on a fresh device gets that progress.
    b_ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    b = b_ctx.new_page()
    b.goto(BASE)
    b.wait_for_selector("#name-overlay:not(.hidden)")
    b.click('[data-acct-tab="login"]')
    check("sign in hides the nickname field", b.locator("#acct-nick-row.hidden").count() == 1)
    b.fill("#acct-username", user.upper())
    b.fill("#acct-password", "wrong-password")
    b.click("#btn-save-name")
    b.wait_for_selector("#acct-error:not(.hidden)", timeout=8000)
    check("a wrong password is refused", "Wrong" in b.inner_text("#acct-error"), b.inner_text("#acct-error"))
    b.fill("#acct-password", pw)
    b.click("#btn-save-name")
    b.wait_for_selector("#name-overlay.hidden", state="attached", timeout=8000)
    got = b.evaluate("[profile.name, profile.attempted, profile.elos.hard]")
    check("progress follows the account to another device", got == ["Guesty", 9, 1333], str(got))
    check("usernames aren't case sensitive", True)

    # Device B saves; device A is now stale, and its next save must not win.
    b.evaluate("profile.attempted = 20; saveProfile()")
    b.wait_for_function("!JSON.parse(localStorage.getItem('lumo-account')).dirty", timeout=8000)
    a.evaluate("profile.attempted = 10; saveProfile()")
    a.wait_for_function("profile.attempted === 20", timeout=8000)
    check("a stale device takes the newer progress instead of overwriting it", True)

    # Reload keeps the session.
    b.reload()
    b.wait_for_selector(".sb-item")
    b.wait_for_timeout(800)
    check("sessions survive a reload", b.locator("#btn-user.signed-in").count() == 1
          and b.evaluate("profile.attempted") == 20)

    # Signing out leaves nothing behind.
    b.click("#btn-user")
    b.wait_for_selector("#acct-signed:not(.hidden)")
    check("the account window shows the sync state", "saved" in b.inner_text("#acct-sync").lower(),
          b.inner_text("#acct-sync"))
    with b.expect_navigation():
        b.click("#btn-signout")
    b.wait_for_selector("#name-overlay:not(.hidden)", timeout=8000)
    check("signing out clears this device", b.evaluate("profile.attempted") == 0
          and b.locator("#btn-user.signed-in").count() == 0)
    check("no page errors with accounts", not errors, str(errors))
    b_ctx.close()
    a_ctx.close()


def main():
    print(f"Lumo end-to-end tests against {BASE}")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for fn in (test_first_run, test_navigation, test_question_bank,
                   test_solo_and_mistakes, test_planner_and_vocab, test_search,
                   test_tools, test_party, test_duel, test_duel_difficulty, test_practice_and_grid_in, test_responsive,
                   test_masterclass, test_coach, test_tutor, test_classes,
                   test_friends, test_2v2, test_bot_duel, test_accounts, test_theme):
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
