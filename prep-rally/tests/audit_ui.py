#!/usr/bin/env python3
"""UI audit for Lumo: crawls every screen and state and checks what a user sees.

    python3 tests/audit_ui.py            # server must be running on :3000

For each screen, at a desktop and a phone viewport, it reports:
  - text whose contrast against its real background fails WCAG AA, walking up
    through translucent layers and taking the worst stop of any gradient, so
    white-on-white text behind a missing gradient is caught
  - a page that scrolls sideways, and elements that run off the right edge
  - text clipped by overflow: hidden without an ellipsis
  - buttons, links, and inputs with no accessible name
  - tap targets under 24px on the phone viewport
  - page errors, console errors, and failed requests

Exits non-zero when anything is found.
"""

import os
import sys
from collections import defaultdict

from playwright.sync_api import sync_playwright

BASE = os.environ.get("LUMO_URL", "http://localhost:3000")
VIEWPORTS = {"desktop": (1280, 900), "phone": (375, 812)}
SCHEMES = ("light", "dark")

# Runs in the page. Returns a list of findings for whatever is on screen now.
PROBE = r"""
(isPhone) => {
  const out = [];
  const W = innerWidth;
  const WHITE = { r: 255, g: 255, b: 255, a: 1 };

  const parse = (s) => {
    const m = s && s.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(/[\s,\/]+/).filter(Boolean).map(Number);
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  };
  const stops = (img) => (img.match(/rgba?\([^)]+\)/g) || []).map(parse).filter(Boolean);
  const lin = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  const lum = (c) => 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const blend = (top, under) => ({
    r: top.r * top.a + under.r * (1 - top.a),
    g: top.g * top.a + under.g * (1 - top.a),
    b: top.b * top.a + under.b * (1 - top.a), a: 1,
  });
  const hex = (c) => '#' + [c.r, c.g, c.b].map((v) => Math.round(v).toString(16).padStart(2, '0')).join('');

  // Every opaque colour that could sit behind an element: translucent layers are
  // blended down onto whatever is underneath, and a gradient yields one
  // candidate per stop so the worst stop is the one judged.
  function backgrounds(el) {
    const layers = [];
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const cs = getComputedStyle(n);
      const img = cs.backgroundImage || '';
      if (img.includes('url(')) return null;            // photo or icon: cannot judge
      let level = null;
      if (img.includes('gradient')) level = stops(img);
      if (!level || !level.length) {
        const bc = parse(cs.backgroundColor);
        if (bc && bc.a > 0) level = [bc];
      }
      if (!level) continue;
      if (level.every((c) => c.a >= 1)) {
        let cands = level;
        for (let i = layers.length - 1; i >= 0; i--) {
          cands = cands.flatMap((c) => layers[i].map((l) => blend(l, c))).slice(0, 24);
        }
        return cands;
      }
      layers.push(level);
    }
    let cands = [WHITE];
    for (let i = layers.length - 1; i >= 0; i--) {
      cands = cands.flatMap((c) => layers[i].map((l) => blend(l, c))).slice(0, 24);
    }
    return cands;
  }

  function shown(el) {
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    let op = 1;
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const cs = getComputedStyle(n);
      if (cs.display === 'none' || cs.visibility === 'hidden') return false;
      op *= parseFloat(cs.opacity);
    }
    return op > 0.05;
  }
  function opacityOf(el) {
    let op = 1;
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) op *= parseFloat(getComputedStyle(n).opacity);
    return op;
  }

  const desc = (el) => {
    let s = el.tagName.toLowerCase();
    if (el.id) s += '#' + el.id;
    else if (el.classList.length) s += '.' + [...el.classList].slice(0, 2).join('.');
    const host = el.closest('[id]');
    const where = host && host !== el ? `${host.id} > ` : '';
    const t = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ').slice(0, 42);
    return `${where}${s}${t ? ` "${t}"` : ''}`;
  };

  const skip = (el) => el.closest('#desmos-mount, svg, script, style, noscript');

  // ---- contrast ----
  for (const el of document.querySelectorAll('body *')) {
    if (skip(el) || !shown(el)) continue;
    const hasText = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (!hasText) continue;
    if (el.closest(':disabled, [aria-disabled="true"]')) continue;   // WCAG exempts inactive controls
    const cs = getComputedStyle(el);
    const fg = parse(cs.color);
    const bgs = backgrounds(el);
    if (!fg || !bgs) continue;
    const size = parseFloat(cs.fontSize), weight = parseInt(cs.fontWeight, 10);
    const large = size >= 24 || (size >= 18.66 && weight >= 700);
    const need = large ? 3 : 4.5;
    const alpha = fg.a * opacityOf(el);
    let worst = Infinity, worstBg = null;
    for (const bg of bgs) {
      const shownFg = alpha < 1 ? blend({ ...fg, a: alpha }, bg) : fg;
      const r = ratio(shownFg, bg);
      if (r < worst) { worst = r; worstBg = bg; }
    }
    if (worst < need) {
      out.push({
        kind: worst < 1.5 ? 'invisible text' : 'low contrast',
        severity: worst < 1.5 ? 'error' : 'warn',
        where: desc(el),
        detail: `${worst.toFixed(2)}:1, needs ${need}:1 (${hex(fg)} on ${hex(worstBg)})`,
      });
    }
  }

  // ---- overflow ----
  if (document.documentElement.scrollWidth > W + 1) {
    out.push({ kind: 'page scrolls sideways', severity: 'error', where: 'document',
               detail: `${document.documentElement.scrollWidth}px wide in a ${W}px viewport` });
  }
  // Content past the right edge of what can actually be seen. A clipping
  // ancestor (overflow hidden/clip) does not make that fine: it stops the page
  // scrolling but still slices the content off. Only a real scroller
  // (overflow auto/scroll) lets the user reach it.
  const ox = (n) => getComputedStyle(n).overflowX;
  for (const el of document.querySelectorAll('body *')) {
    if (skip(el) || !shown(el)) continue;
    const r = el.getBoundingClientRect();
    const leafish = el.children.length === 0 || el.matches('button, a, input, select, textarea, label');
    if (!leafish || getComputedStyle(el).position === 'fixed') continue;
    let clipper = null;
    for (let n = el.parentElement; n && n !== document.documentElement; n = n.parentElement) {
      if (ox(n) !== 'visible') { clipper = n; break; }
    }
    if (clipper && ['auto', 'scroll'].includes(ox(clipper))) continue;
    const edge = clipper ? Math.min(clipper.getBoundingClientRect().right, W) : W;
    if (r.right > edge + 1 && r.left < edge) {
      out.push({ kind: clipper ? 'cut off' : 'runs off screen', severity: 'error', where: desc(el),
                 detail: `right edge at ${Math.round(r.right)}px, visible area ends at ${Math.round(edge)}px` +
                         (clipper ? ` (clipped by ${desc(clipper).split(' "')[0]})` : '') });
    }
  }
  for (const el of document.querySelectorAll('body *')) {
    if (skip(el) || !shown(el)) continue;
    const cs = getComputedStyle(el);
    const hasText = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (hasText && cs.overflowX === 'hidden' && cs.textOverflow !== 'ellipsis' && el.scrollWidth > el.clientWidth + 1) {
      out.push({ kind: 'text clipped', severity: 'warn', where: desc(el),
                 detail: `${el.scrollWidth}px of text in ${el.clientWidth}px` });
    }
  }

  // ---- pills that wrap ----
  // A fully rounded chip or button whose label breaks across lines turns into a
  // lopsided blob (the subject chips did this on phones).
  for (const el of document.querySelectorAll('body *')) {
    if (skip(el) || !shown(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.height < 18) continue;
    const radius = parseFloat(getComputedStyle(el).borderTopLeftRadius) || 0;
    if (radius < r.height / 2 - 1) continue;
    const tops = new Set();
    for (const n of el.childNodes) {
      if (n.nodeType !== 3 || !n.textContent.trim()) continue;
      const range = document.createRange();
      range.selectNodeContents(n);
      for (const rc of range.getClientRects()) if (rc.width > 0) tops.add(Math.round(rc.top / 4));
    }
    if (tops.size > 1) {
      out.push({ kind: 'pill label wraps', severity: 'error', where: desc(el),
                 detail: `label breaks onto ${tops.size} lines inside a ${Math.round(r.width)}x${Math.round(r.height)}px pill` });
    }
  }

  // ---- controls covering each other ----
  // The rail's last icon slid under the avatar once a second button joined the
  // foot: both were on screen, neither overflowed, one was simply unclickable.
  const ctrls = [...document.querySelectorAll('button, a[href], [role="button"], input:not([type="hidden"]), select, textarea')]
    .filter((el) => !skip(el) && shown(el))
    .map((el) => ({ el, r: el.getBoundingClientRect() }))
    .filter((c) => c.r.width > 1 && c.r.height > 1)
    .slice(0, 220);
  for (let i = 0; i < ctrls.length; i++) {
    for (let j = i + 1; j < ctrls.length; j++) {
      const a = ctrls[i], b = ctrls[j];
      if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
      const ox = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left);
      const oy = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top);
      if (ox <= 2 || oy <= 2) continue;
      const cx = (Math.max(a.r.left, b.r.left) + Math.min(a.r.right, b.r.right)) / 2;
      const cy = (Math.max(a.r.top, b.r.top) + Math.min(a.r.bottom, b.r.bottom)) / 2;
      if (cx < 0 || cy < 0 || cx > W || cy > innerHeight) continue;
      const top = document.elementFromPoint(cx, cy);
      if (!top) continue;
      // Only report when one of the two actually wins the hit test there; an
      // overlay or sticky bar on top of both is a different, legitimate stack.
      let covered = null, cover = null;
      if (a.el.contains(top) || a.el === top) { covered = b; cover = a; }
      else if (b.el.contains(top) || b.el === top) { covered = a; cover = b; }
      if (!covered) continue;
      // Scrolled out of its own scroll area is not covered: the student scrolls
      // to it. Only judge the part of it that its scroller actually shows.
      const scroller = (el) => {
        for (let n = el.parentElement; n && n !== document.body; n = n.parentElement) {
          const o = getComputedStyle(n).overflowY;
          if (o === 'auto' || o === 'scroll') return n;
        }
        return null;
      };
      const sc = scroller(covered.el);
      if (sc && !sc.contains(cover.el)) {
        const v = sc.getBoundingClientRect();
        if (cy < v.top || cy > v.bottom || cx < v.left || cx > v.right) continue;
      }
      // A dialog sitting over the page it interrupts is the point of a dialog.
      const inModal = (el) => el.closest('.overlay, .modal, dialog, [role="dialog"]');
      if (inModal(cover.el) && !inModal(covered.el)) continue;
      out.push({ kind: 'control covered by another control', severity: 'error',
                 where: desc(covered.el),
                 detail: `${Math.round(ox)}x${Math.round(oy)}px of it sits under ${desc(cover.el)}` });
    }
  }

  // ---- stacked cards touching ----
  // Home's study-plan rows sat edge to edge: their wrapper was one child of a
  // flex list, so the list's gap never reached them. Rounded, bordered boxes
  // stacked one above the other need visible space between them.
  const boxed = (el) => {
    const cs = getComputedStyle(el);
    return parseFloat(cs.borderTopWidth) > 0 && parseFloat(cs.borderBottomWidth) > 0
      && cs.borderTopStyle !== 'none' && (parseFloat(cs.borderTopLeftRadius) || 0) >= 4;
  };
  for (const el of document.querySelectorAll('body *')) {
    if (skip(el) || !shown(el) || !boxed(el)) continue;
    let next = el.nextElementSibling;
    while (next && !shown(next)) next = next.nextElementSibling;
    if (!next || !boxed(next)) continue;
    const a = el.getBoundingClientRect(), b = next.getBoundingClientRect();
    if (a.height < 24 || b.height < 24) continue;
    const ox = Math.min(a.right, b.right) - Math.max(a.left, b.left);
    if (ox < Math.min(a.width, b.width) / 2) continue;
    const space = b.top - a.bottom;
    if (space >= -1 && space < 4) {
      out.push({ kind: 'stacked cards touching', severity: 'error', where: desc(el),
                 detail: `only ${Math.round(space)}px between it and ${desc(next)}` });
    }
  }

  // ---- names and targets ----
  for (const el of document.querySelectorAll('button, a[href], [role="button"], input:not([type="hidden"]), select, textarea')) {
    if (skip(el) || !shown(el)) continue;
    let name = el.getAttribute('aria-label') || '';
    const lb = el.getAttribute('aria-labelledby');
    if (!name && lb) name = lb.split(/\s+/).map((id) => (document.getElementById(id) || {}).innerText || '').join(' ');
    if (!name && el.labels && el.labels.length) name = [...el.labels].map((l) => l.innerText).join(' ');
    if (!name) name = el.innerText || el.getAttribute('title') || el.getAttribute('placeholder') || '';
    if (!name.trim()) {
      out.push({ kind: 'no accessible name', severity: 'error', where: desc(el),
                 detail: 'a screen reader announces this as an unlabelled control' });
    }
    if (isPhone && el.matches('button, [role="button"], input, select')) {
      let r = el.getBoundingClientRect();
      // A label wrapping or pointing at a control activates it too, so the
      // label's box is part of the target (a checkbox with its text, or an
      // input inside a styled search pill).
      for (const lab of el.labels || []) {
        const lr = lab.getBoundingClientRect();
        r = { width: Math.max(r.width, lr.width), height: Math.max(r.height, lr.height) };
      }
      if (r.width < 24 || r.height < 24) {
        out.push({ kind: 'tap target too small', severity: 'warn', where: desc(el),
                   detail: `${Math.round(r.width)}x${Math.round(r.height)}px, minimum 24x24` });
      }
    }
  }
  return out;
}
"""


def nav(page, name):
    """The rail picks a section; a tab inside the page picks the screen."""
    group = page.evaluate(
        "(n) => (NAV.find((g) => g.items.some((i) => i.name === n)) || {}).name", name)
    if page.locator("#v-match.active").count():
        # the test screen is full-window like the real SAT; leave through Exit
        # (the page's dialog handler accepts the "leave this game?" prompt)
        page.click("#btn-exit-test")
        page.wait_for_timeout(300)
    page.click(f'.sb-item[data-navgroup="{group}"]')
    page.wait_for_timeout(250)
    tab = page.locator(f'.view.active .subnav-tab[data-navitem="{name}"]')
    if tab.count():
        tab.click()
    page.wait_for_timeout(450)


def start_drill(page, domain, count="5"):
    nav(page, "Question Bank")
    page.wait_for_selector(".bank-card")
    page.click(f'#bank-count .seg-btn[data-count="{count}"]')
    page.click(f'[data-bank-domain="{domain}"]')
    page.wait_for_selector("#v-match.active", timeout=10000)
    page.wait_for_timeout(400)


def answer(page):
    if page.locator("#spr:not(.hidden)").count():
        page.fill("#spr-input", "-9999")
    else:
        page.click('#choice-grid .mchoice[data-i="0"]')
    page.wait_for_timeout(120)
    if page.locator("#btn-lock").is_enabled():
        page.click("#btn-lock")
    page.wait_for_selector("#reveal-card:not(.hidden)", timeout=10000)
    page.wait_for_timeout(300)


def finish(page):
    for _ in range(12):
        if page.locator("#v-results.active").count():
            return
        if page.locator("#reveal-card.hidden").count():
            answer(page)
        nxt = page.locator("#btn-next")
        if nxt.is_visible():
            nxt.click()
            page.wait_for_timeout(500)
    page.wait_for_selector("#v-results.active", timeout=10000)


def open_calc(page):
    page.click("#btn-calc")
    for _ in range(30):
        if page.evaluate("typeof desmos === 'undefined' || desmos.state !== 'loading'"):
            break
        page.wait_for_timeout(500)
    page.wait_for_timeout(400)


# (label, steps). Steps run in order on one page, so later states can build on
# earlier ones (the match reaches its reveal, then its results).
def plan(page):
    return [
        ("home", lambda: nav(page, "Home")),
        ("study planner", lambda: nav(page, "Study Planner")),
        ("question bank", lambda: (nav(page, "Question Bank"), page.wait_for_selector(".bank-card"))),
        ("question rush", lambda: nav(page, "Question Rush")),
        ("vocab", lambda: nav(page, "Vocab")),
        ("vocab, flipped", lambda: (page.click("#vocab-card"), page.wait_for_timeout(300))),
        ("play", lambda: nav(page, "Play")),
        ("saved & mistakes, empty", lambda: nav(page, "Saved & Mistakes")),
        ("analytics, empty", lambda: nav(page, "Analytics")),
        ("masterclass", lambda: nav(page, "Reading & Writing")),
        ("lesson", lambda: (page.click("[data-lesson]"), page.wait_for_selector("#v-lesson.active"),
                            page.wait_for_timeout(300))),
        ("ask lumo", lambda: nav(page, "Ask Lumo")),
        ("my classes", lambda: nav(page, "My Classes")),
        ("apply as a tutor", lambda: nav(page, "Apply As A Tutor")),
        ("search results", lambda: (nav(page, "Home"), page.fill("#search-input", "algebra"),
                                    page.press("#search-input", "Enter"), page.wait_for_timeout(500))),
        ("matchmaking queue", lambda: (nav(page, "Play"), page.click("#btn-find-match"),
                                       page.wait_for_selector("#v-queue.active"), page.wait_for_timeout(300))),
        ("party lobby", lambda: (page.click("#btn-queue-cancel"), page.wait_for_timeout(400),
                                 nav(page, "Play"), page.click("#btn-host-party"),
                                 page.wait_for_selector("#v-lobby.active"), page.wait_for_timeout(300))),
        ("reading question", lambda: start_drill(page, "Craft and Structure")),
        ("math question", lambda: start_drill(page, "Algebra")),
        ("calculator open", lambda: open_calc(page)),
        ("answer revealed", lambda: (page.click("#btn-calc-close"), page.wait_for_timeout(200), answer(page))),
        ("results", lambda: finish(page)),
        ("typed-answer question", lambda: (page.evaluate("startPractice({ ids: ['mth-0056'], count: 1 }, 'Audit')"),
                                           page.wait_for_selector("#v-match.active"), page.wait_for_timeout(500),
                                           page.fill("#spr-input", "5/6"), page.wait_for_timeout(200))),
        ("saved & mistakes, filled", lambda: nav(page, "Saved & Mistakes")),
        ("analytics, filled", lambda: nav(page, "Analytics")),
    ]


def audit_viewport(pw_browser, label, size, scheme="light"):
    findings = []
    ctx = pw_browser.new_context(viewport={"width": size[0], "height": size[1]},
                                 is_mobile=(label == "phone"), has_touch=(label == "phone"),
                                 color_scheme=scheme)

    def attach(page, state_ref):
        page.on("dialog", lambda d: d.accept())
        page.on("pageerror", lambda e: findings.append(
            (state_ref[0], {"kind": "page error", "severity": "error", "where": "script", "detail": str(e)[:160]})))
        page.on("console", lambda m: m.type == "error" and findings.append(
            (state_ref[0], {"kind": "console error", "severity": "error", "where": "console", "detail": m.text[:160]})))
        page.on("response", lambda r: r.status >= 400 and findings.append(
            (state_ref[0], {"kind": "failed request", "severity": "error", "where": r.url.replace(BASE, ""),
                            "detail": f"HTTP {r.status}"})))

    # First visit, before a nickname exists.
    state = ["name prompt"]
    page = ctx.new_page()
    attach(page, state)
    page.goto(BASE)
    page.wait_for_selector("#name-overlay:not(.hidden)")
    for f in page.evaluate(PROBE, label == "phone"):
        findings.append((state[0], f))
    # Every face of the account window: an error, sign in, guest, then signed in.
    import random as _r
    for name, step in [
        ("account: error", lambda: (page.click("#btn-save-name"), page.wait_for_timeout(200))),
        ("account: sign in tab", lambda: (page.click('[data-acct-tab="login"]'), page.wait_for_timeout(200))),
        ("account: guest tab", lambda: (page.click('[data-acct-tab="guest"]'), page.wait_for_timeout(200))),
        ("account: signed in", lambda: (
            page.click('[data-acct-tab="signup"]'),
            page.fill("#acct-username", f"audit{_r.randint(100000, 999999)}"),
            page.fill("#acct-password", "audit-password-1"),
            page.fill("#name-input", "Auditor"),
            page.click("#btn-save-name"),
            page.wait_for_selector("#name-overlay.hidden", state="attached"),
            page.click("#btn-user"),
            page.wait_for_selector("#acct-signed:not(.hidden)"),
            page.wait_for_timeout(300))),
    ]:
        state[0] = name
        try:
            step()
        except Exception as exc:
            findings.append((name, {"kind": "could not reach state", "severity": "error",
                                    "where": name, "detail": str(exc).splitlines()[0][:160]}))
            continue
        for f in page.evaluate(PROBE, label == "phone"):
            findings.append((name, f))
    page.close()

    page = ctx.new_page()
    attach(page, state)
    page.add_init_script("localStorage.setItem('lumo-profile', JSON.stringify({name:'Aneesh'}))")
    page.goto(BASE)
    page.wait_for_selector(".sb-item")
    for name, step in plan(page):
        state[0] = name
        try:
            step()
        except Exception as exc:  # a state we could not reach is itself a finding
            findings.append((name, {"kind": "could not reach state", "severity": "error",
                                    "where": name, "detail": str(exc).splitlines()[0][:160]}))
            continue
        for f in page.evaluate(PROBE, label == "phone"):
            findings.append((name, f))
    ctx.close()
    return findings


def main():
    total_errors = 0
    total = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for label, size in VIEWPORTS.items():
          for scheme in SCHEMES:
            found = audit_viewport(browser, label, size, scheme)
            seen = set()
            grouped = defaultdict(list)
            for state, f in found:
                key = (f["kind"], f["where"], f["detail"])
                if key in seen:
                    continue
                seen.add(key)
                grouped[state].append(f)
            count = sum(len(v) for v in grouped.values())
            errors = sum(1 for v in grouped.values() for f in v if f["severity"] == "error")
            total += count
            total_errors += errors
            print(f"\n{'=' * 70}\n{label.upper()} {size[0]}x{size[1]} {scheme.upper()} — "
                  f"{count} findings ({errors} errors)")
            for state, items in grouped.items():
                print(f"\n  [{state}]")
                for f in sorted(items, key=lambda x: (x["severity"] != "error", x["kind"])):
                    mark = "ERR " if f["severity"] == "error" else "warn"
                    print(f"    {mark} {f['kind']}: {f['where']}\n         {f['detail']}")
        browser.close()
    print(f"\n{'=' * 70}\n{total} findings, {total_errors} errors")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
