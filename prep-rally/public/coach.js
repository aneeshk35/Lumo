/* Lumo — Ask Lumo. A coach that answers from what Lumo actually has: the
   lesson library, the question bank, the vocab deck, and your own stats.

   It is deliberately not a chatbot. Everything it says is retrieved from real
   content in this app, so it works offline and cannot invent a fact. When it
   has nothing good, it says so instead of guessing. */

let coachVocab = null;
let coachBooted = false;

const STOPWORDS = new Set(['a', 'an', 'the', 'is', 'are', 'was', 'were', 'do', 'does', 'did',
  'how', 'what', 'why', 'when', 'which', 'who', 'i', 'me', 'my', 'you', 'your', 'to', 'of',
  'in', 'on', 'for', 'with', 'and', 'or', 'but', 'that', 'this', 'it', 'be', 'can', 'should',
  'would', 'about', 'at', 'as', 'from', 'get', 'got', 'help', 'please', 'explain', 'tell']);

// Words students use that do not literally appear in the lesson text.
const SYNONYMS = {
  comma: ['punctuation', 'boundaries', 'commas'],
  semicolon: ['punctuation', 'boundaries'],
  colon: ['punctuation', 'boundaries'],
  grammar: ['conventions', 'punctuation', 'verbs', 'modifiers'],
  graph: ['desmos', 'graphing', 'parabola'],
  calculator: ['desmos'],
  parabola: ['quadratic', 'vertex'],
  slope: ['linear', 'rate'],
  percent: ['percentage', 'ratios'],
  probability: ['two-way', 'table'],
  average: ['mean', 'median', 'statistics'],
  trig: ['trigonometry', 'sine', 'cosine'],
  vocab: ['words', 'context'],
  evidence: ['command', 'support', 'claim'],
  transition: ['transitions', 'however', 'therefore'],
  main: ['central', 'idea'],
};

function tokenize(text) {
  const raw = String(text).toLowerCase().replace(/[^a-z0-9\s]/g, ' ').split(/\s+/)
    .filter((w) => w && w.length > 1 && !STOPWORDS.has(w));
  const out = new Set(raw);
  for (const w of raw) (SYNONYMS[w] || []).forEach((s) => out.add(s));
  return [...out];
}

const TOOL_TERMS = ['desmos', 'graph', 'graphing', 'calculator', 'plot'];

function scoreLesson(lesson, terms, wantsTool) {
  const strong = `${lesson.title} ${lesson.skill} ${lesson.domain}`.toLowerCase();
  const body = `${lesson.summary} ${lesson.blocks.map((b) =>
    `${b.heading || ''} ${b.body || ''} ${(b.items || []).join(' ')} ${b.question || ''}`).join(' ')}`.toLowerCase();
  let score = 0;
  for (const t of terms) {
    if (strong.includes(t)) score += 6;
    else if (body.includes(t)) score += 1;
  }
  // Desmos lessons teach the tool, not the concept. They mention every math term,
  // so without this they would win concept questions like "explain the vertex".
  // Asking about the calculator explicitly lifts the penalty.
  if (lesson.domain === 'Desmos' && !wantsTool) score -= 6;
  return score;
}

async function coachBoot() {
  if (coachBooted) return;
  await loadLessons();
  if (!coachVocab) coachVocab = await (await fetch('vocab.json')).json();
  coachBooted = true;
}

/* ---------------- answer builders ---------------- */
function answerStudyPlan() {
  const weak = weakestDomains(3).filter((d) => d.total > 0);
  if (!weak.length) {
    return {
      title: 'Not enough data yet — start here',
      body: ['I build this answer from the questions you have actually answered, and you have not '
        + 'answered enough yet for the numbers to mean anything. Do one 10-question mixed set and '
        + 'ask me again; I will point at your real weak spots rather than guessing.'],
      actions: [{ label: 'Start a 10-question mixed set', practice: { section: 'mixed', count: 10 } }],
    };
  }
  const lines = weak.map((d) => {
    const pct = d.total ? Math.round((d.acc) * 100) : 0;
    return `${d.domain} — ${pct}% on ${d.total} question${d.total === 1 ? '' : 's'}${d.missed ? `, ${d.missed} missed` : ''}`;
  });
  const target = weak[0];
  const lesson = (LESSONS || []).find((l) => l.domain === target.domain);
  return {
    title: 'Study these next, worst first',
    body: [`Ranked by how many you have actually missed:`, ...lines.map((l) => `• ${l}`),
      `Start with ${target.domain}. Read the lesson, then drill five questions in it while the method is fresh.`],
    actions: [
      lesson ? { label: `Open the ${target.domain} lesson`, lesson: lesson.id } : null,
      { label: `Drill ${target.domain}`, practice: { section: DOMAIN_SECTION[target.domain], domains: [target.domain], count: 5 } },
    ].filter(Boolean),
  };
}

function answerMistakes() {
  const n = profile.mistakes.length;
  if (!n) {
    return {
      title: 'No saved mistakes right now',
      body: ['Every question you miss is saved automatically with its full explanation. '
        + 'You have none saved, which means either a clean run or no sessions yet.'],
      actions: [{ label: 'Play a session', practice: { section: 'mixed', count: 10 } }],
    };
  }
  const byDomain = {};
  profile.mistakes.forEach((m) => { byDomain[m.domain] = (byDomain[m.domain] || 0) + 1; });
  const ranked = Object.entries(byDomain).sort((a, b) => b[1] - a[1]);
  return {
    title: `You have ${n} saved mistake${n === 1 ? '' : 's'}`,
    body: [
      'They cluster like this:',
      ...ranked.map(([d, c]) => `• ${d} — ${c}`),
      'Answering one correctly in a review session retires it from the list.',
    ],
    actions: [{ label: 'Review them all', nav: 'Saved & Mistakes' }],
  };
}

function answerVocab(hit) {
  return {
    title: `${hit.word} — ${hit.pos}`,
    body: [hit.def, `Example: ${hit.ex}`],
    actions: [{ label: 'Open the vocab deck', nav: 'Vocab' }],
  };
}

function answerLesson(lesson) {
  const steps = lesson.blocks.find((b) => b.type === 'steps' || b.type === 'desmos');
  const concept = lesson.blocks.find((b) => b.type === 'concept');
  const body = [];
  if (concept) body.push(concept.body);
  if (steps) {
    body.push(steps.heading ? `${steps.heading}:` : 'The method:');
    steps.items.forEach((it, i) => body.push(`${i + 1}. ${it}`));
  }
  return {
    title: lesson.title,
    kicker: `${lesson.domain} · ${lesson.skill}`,
    body,
    actions: [
      { label: `Read the full lesson (${lesson.minutes} min)`, lesson: lesson.id },
      { label: 'Drill this skill', practice: { ...lesson.drill } },
    ],
  };
}

async function answerQuestions(query) {
  const res = await api('search', { q: query });
  const hits = (res.results || []).slice(0, 3);
  if (!hits.length) return null;
  return {
    title: `${res.results.length} question${res.results.length === 1 ? '' : 's'} in the bank match that`,
    body: ['I could not find a lesson on it, but these bank questions cover it. '
      + 'Practising one shows the full explanation after you answer.',
      ...hits.map((h) => `• ${h.domain} · ${h.difficulty} — ${h.question}`)],
    actions: [{ label: 'Practise these', search: query }],
  };
}

function answerFallback() {
  return {
    title: "I don't have anything solid on that",
    body: ['I only answer from Lumo\'s own lessons, question bank, vocab deck, and your stats, '
      + 'so when none of them match I would rather say so than make something up.',
      'Try naming a skill (transitions, quadratics, two-way tables), a vocab word, or ask what to study next.'],
    actions: [{ label: 'What should I study next?', ask: 'What should I study next?' }],
  };
}

async function coachAnswer(query) {
  await coachBoot();
  const q = query.toLowerCase();
  const terms = tokenize(query);

  if (/what.*(study|practice|work on|next)|weak|worst|improve|where.*start|plan/.test(q)) {
    return answerStudyPlan();
  }
  if (/mistake|missed|wrong|got it wrong|review/.test(q)) return answerMistakes();
  if (/score|elo|how am i|my stats|progress/.test(q)) {
    const acc = profile.attempted ? Math.round((profile.correct / profile.attempted) * 100) : 0;
    return {
      title: 'Where you stand',
      body: [
        `${profile.attempted} question${profile.attempted === 1 ? '' : 's'} answered, ${acc}% correct.`,
        `Best streak ${profile.bestStreak}. Duel record ${profile.wins}–${profile.losses}, ${profile.elo} ELO.`,
        `${profile.lessonsDone.length} of ${(LESSONS || []).length} masterclass lessons finished.`,
      ],
      actions: [{ label: 'Open Analytics', nav: 'Analytics' }],
    };
  }

  // an exact vocab word beats everything else
  const vhit = (coachVocab || []).find((v) => new RegExp(`\\b${v.word}\\b`, 'i').test(q));
  if (vhit) return answerVocab(vhit);

  const wantsTool = terms.some((t) => TOOL_TERMS.includes(t));
  const scored = (LESSONS || []).map((l) => ({ l, s: scoreLesson(l, terms, wantsTool) }))
    .sort((a, b) => b.s - a.s);
  if (scored.length && scored[0].s >= 6) return answerLesson(scored[0].l);

  const fromBank = await answerQuestions(query);
  if (fromBank) return fromBank;
  if (scored.length && scored[0].s > 0) return answerLesson(scored[0].l);
  return answerFallback();
}

/* ---------------- thread rendering ---------------- */
const COACH_CHIPS = [
  'What should I study next?',
  'How do transitions work?',
  'Explain quadratic vertex',
  'How do I use Desmos?',
  'What are my mistakes?',
];

function coachPush(role, payload) {
  const thread = $('coach-thread');
  const wrap = document.createElement('div');
  if (role === 'you') {
    wrap.className = 'coach-msg you';
    wrap.innerHTML = `<span class="bubble">${esc(payload)}</span>`;
  } else {
    wrap.className = 'coach-msg lumo-msg';
    const a = payload;
    wrap.innerHTML = `
      <span class="lumo round lilac" aria-hidden="true"></span>
      <div class="coach-card">
        ${a.kicker ? `<span class="ck">${esc(a.kicker)}</span>` : ''}
        <span class="t">${esc(a.title)}</span>
        ${a.body.map((p) => `<p>${esc(p)}</p>`).join('')}
        ${a.actions && a.actions.length ? `<div class="coach-actions">${a.actions.map((act, i) =>
          `<button class="btn-outline" data-act="${i}">${esc(act.label)}</button>`).join('')}</div>` : ''}
      </div>`;
    if (a.actions) {
      wrap.querySelectorAll('[data-act]').forEach((b) => {
        b.onclick = () => runCoachAction(a.actions[Number(b.dataset.act)]);
      });
    }
  }
  thread.appendChild(wrap);
  thread.scrollTop = thread.scrollHeight;
  return wrap;
}

function runCoachAction(act) {
  if (!act) return;
  if (act.nav) return navTo(act.nav);
  if (act.lesson) return openLesson(act.lesson);
  if (act.practice) return startPractice(act.practice, 'Coach');
  if (act.search) { $('search-input').value = act.search; return runSearch(act.search); }
  if (act.ask) { $('coach-input').value = act.ask; return coachSubmit(); }
}

let coachBusy = false;
async function coachSubmit() {
  const input = $('coach-input');
  const q = input.value.trim();
  if (!q || coachBusy) return;
  coachBusy = true;
  input.value = '';
  coachPush('you', q);
  const pending = coachPush('lumo', { title: 'Looking through the library…', body: [] });
  try {
    const answer = await coachAnswer(q);
    pending.remove();
    coachPush('lumo', answer);
  } catch (err) {
    pending.remove();
    coachPush('lumo', {
      title: 'Something went wrong looking that up',
      body: [String(err && err.message ? err.message : err)],
      actions: [],
    });
  }
  coachBusy = false;
}

function renderCoach() {
  if (!$('coach-thread').childElementCount) {
    coachPush('lumo', {
      title: `Hi ${profile.name || 'there'} — ask me about any SAT skill`,
      body: ['I answer from Lumo\'s 27 masterclass lessons, the question bank, the vocab deck, '
        + 'and your own results. I will tell you when I do not have something rather than guess.'],
      actions: [{ label: 'What should I study next?', ask: 'What should I study next?' }],
    });
  }
  $('coach-chips').innerHTML = COACH_CHIPS.map((c) =>
    `<button class="coach-chip">${esc(c)}</button>`).join('');
  $('coach-chips').querySelectorAll('.coach-chip').forEach((b) => {
    b.onclick = () => { $('coach-input').value = b.textContent; coachSubmit(); };
  });
  coachBoot();
}
RENDERERS['v-coach'] = renderCoach;

$('coach-form').addEventListener('submit', (e) => { e.preventDefault(); coachSubmit(); });
