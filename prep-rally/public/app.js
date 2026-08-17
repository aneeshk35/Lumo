/* Lumo — SAT prep app. Frontend for the "Lumo SAT Prep" design, wired to the
   Python SSE game server (solo rush, code parties, 1v1 duel matchmaking). */

const $ = (id) => document.getElementById(id);
const LETTERS = ['A', 'B', 'C', 'D'];
const SECTION_LABEL = { math: 'Math', rw: 'Reading & Writing', mixed: 'Mixed' };

/* ================= Profile (localStorage) ================= */
const DEFAULT_PROFILE = {
  name: '', elo: 1200, wins: 0, losses: 0, points: 0,
  attempted: 0, correct: 0, errors: 0, bestStreak: 0, dayStreak: 1,
  solved: { math: 0, rw: 0 }, sessions: [], testDate: '2026-10-03',
  promoEnd: 0, lastPlayed: 0,
  mistakes: [],        // [{id, question, passage, choices, domain, skill, difficulty, mine, correctIndex, explanation, when}]
  domainStats: {},     // { [domain]: {correct, total} }
  plan: null,          // { week, tasks: [{id, label, domain, section, count, done}] }
  vocabKnown: [],
  retryCorrect: 0, retryTotal: 0,
};
let profile = { ...DEFAULT_PROFILE, ...JSON.parse(localStorage.getItem('lumo-profile') || '{}') };
profile.solved = { ...DEFAULT_PROFILE.solved, ...(profile.solved || {}) };
profile.mistakes = profile.mistakes || [];
profile.domainStats = profile.domainStats || {};
profile.vocabKnown = profile.vocabKnown || [];
function saveProfile() { localStorage.setItem('lumo-profile', JSON.stringify(profile)); }

const DOMAIN_SECTION = {
  'Algebra': 'math', 'Advanced Math': 'math',
  'Problem-Solving and Data Analysis': 'math', 'Geometry and Trigonometry': 'math',
  'Information and Ideas': 'rw', 'Craft and Structure': 'rw',
  'Expression of Ideas': 'rw', 'Standard English Conventions': 'rw',
};
// Domains sorted worst-accuracy-first; unattempted domains count as neutral.
function weakestDomains(n) {
  const all = Object.keys(DOMAIN_SECTION).map((d) => {
    const s = profile.domainStats[d] || { correct: 0, total: 0 };
    const missed = s.total - s.correct;
    const acc = s.total ? s.correct / s.total : 0.5;
    return { domain: d, acc, total: s.total, missed };
  });
  all.sort((a, b) => (a.missed !== b.missed ? b.missed - a.missed : a.acc - b.acc));
  return all.slice(0, n);
}

/* ================= Nav / views ================= */
// Sidebar badge: how many of this week's plan tasks are still open.
function plannerBadge() {
  if (!profile.plan || profile.plan.week !== weekKey()) return '';
  const open = profile.plan.tasks.filter((t) => !t.done).length;
  return open ? String(open) : '';
}

const ICONS = {
  home: 'M3 10.5 12 3l9 7.5V21H3z',
  tutor: 'M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M4 21c0-3.3 3.6-6 8-6s8 2.7 8 6',
  ai: 'M12 3l1.9 4.8L18.7 9.7l-4.8 1.9L12 16.4l-1.9-4.8L5.3 9.7l4.8-1.9z',
  planner: 'M4 6h16v15H4zM4 10.5h16M8.5 3v4M15.5 3v4',
  reading: 'M4 5h6a2 2 0 0 1 2 2v13a2 2 0 0 0-2-2H4zM20 5h-6a2 2 0 0 0-2 2v13a2 2 0 0 1 2-2h6z',
  math: 'M6 5h12l-7 7 7 7H6',
  bank: 'M6 3h12v18l-6-4-6 4z',
  rush: 'M13 2 5 14h6l-1 8 8-12h-6z',
  target: 'M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6',
  tests: 'M6 3h8l4 4v14H6zM14 3v4h4M9 13h6M9 17h4',
  vocab: 'M4 5h16v11H9l-5 4z',
  saved: 'M12 4l2.4 5 5.6.8-4 3.9.9 5.5-4.9-2.6-4.9 2.6.9-5.5-4-3.9 5.6-.8z',
  analytics: 'M5 20V10M12 20V4M19 20v-7',
  classes: 'M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7M2 20c0-3 3.1-5 7-5s7 2 7 5M17 20c0-2.6-1-4-2.5-5 3 .2 5.5 1.9 5.5 5',
  play: 'M9 6.5v11l9-5.5z',
  gear: 'M12 9.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5M12 3v2.2M12 18.8V21M4.9 7.5l1.9 1.1M17.2 15.4l1.9 1.1M4.9 16.5l1.9-1.1M17.2 8.6l1.9-1.1',
};
const NAV = [
  { label: '', items: [
    { name: 'Home', icon: 'home', view: 'v-home' },
    { name: 'Apply As A Tutor', icon: 'tutor', view: 'soon' },
    { name: 'Ask Lumo AI', icon: 'ai', view: 'soon' },
    { name: 'Study Planner', icon: 'planner', view: 'v-planner', badge: plannerBadge },
  ]},
  { label: 'MASTERCLASS', items: [
    { name: 'Reading & Writing', icon: 'reading', view: 'soon', tag: 'New' },
    { name: 'Math & Desmos', icon: 'math', view: 'soon', tag: 'New' },
  ]},
  { label: 'PRACTICE', items: [
    { name: 'Question Bank', icon: 'bank', view: 'v-bank' },
    { name: 'Question Rush', icon: 'rush', view: 'v-rush' },
    { name: 'Challenge Questions', icon: 'target', view: 'challenge' },
    { name: 'Full-Length Tests', icon: 'tests', view: 'test' },
    { name: 'Vocab', icon: 'vocab', view: 'v-vocab' },
  ]},
  { label: 'MULTIPLAYER', items: [
    { name: 'Play', icon: 'play', view: 'v-play', tag: 'New' },
  ]},
  { label: 'PROGRESS', items: [
    { name: 'Saved & Mistakes', icon: 'saved', view: 'v-mistakes' },
    { name: 'Analytics', icon: 'analytics', view: 'v-analytics' },
  ]},
  { label: 'CLASSROOMS', items: [
    { name: 'My Classes', icon: 'classes', view: 'soon' },
  ]},
];
const BANNER_VIEWS = new Set(['v-home', 'v-rush']);

// Honest copy for the features that are not built yet, so each screen says what
// it will be and what to use in the meantime.
const ROADMAP = {
  'Apply As A Tutor': 'Tutor applications open once Lumo has enough active students to match them with. Until then, host a party and walk your friends through questions live.',
  'Ask Lumo AI': 'An AI explainer for any question you miss. Every question already ships with a written explanation on the reveal screen and in Saved & Mistakes.',
  'Reading & Writing': 'Video masterclass lessons for each Reading and Writing domain. The Question Bank already drills all four of those domains with explanations.',
  'Math & Desmos': 'Video masterclass lessons plus a built-in Desmos calculator. Math practice is live now in the Question Bank and Question Rush.',
  'My Classes': 'Teacher dashboards and class rosters, which need accounts. Party codes already work for a whole class at once, up to 20 players.',
};

function icon(k, size = 18, sw = 1.7) {
  return `<svg class="ic" style="width:${size}px;height:${size}px;stroke-width:${sw}" viewBox="0 0 24 24"><path d="${ICONS[k]}"/></svg>`;
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function buildSidebar() {
  const sb = $('sidebar');
  let html = `<div class="sb-brand"><span class="lumo"><span class="dot"></span></span><span class="name">Lumo</span></div><nav class="sb-nav">`;
  for (const group of NAV) {
    if (group.label) html += `<div class="sb-label">${group.label}</div>`;
    for (const it of group.items) {
      const badge = typeof it.badge === 'function' ? it.badge() : it.badge;
      html += `<button class="sb-item" data-navitem="${esc(it.name)}">
        ${icon(it.icon)}
        <span class="grow">${esc(it.name)}</span>
        ${it.tag ? `<span class="sb-tag">${it.tag}</span>` : ''}
        ${badge ? `<span class="sb-badge">${esc(badge)}</span>` : ''}
      </button>`;
    }
  }
  html += `</nav><div class="sb-foot"><button class="sb-user" id="btn-user">
    <span class="lumo"></span><span class="uname" id="sb-username"></span>${icon('gear')}
  </button></div>`;
  sb.innerHTML = html;
  sb.querySelectorAll('[data-navitem]').forEach((b) => {
    b.onclick = () => navTo(b.dataset.navitem);
  });
  $('btn-user').onclick = () => promptName();
}

// Keeps the Study Planner count in the sidebar in sync as tasks get checked off.
function refreshPlannerBadge() {
  const item = document.querySelector('.sb-item[data-navitem="Study Planner"]');
  if (!item) return;
  const count = plannerBadge();
  let badge = item.querySelector('.sb-badge');
  if (!count) { if (badge) badge.remove(); return; }
  if (!badge) {
    badge = document.createElement('span');
    badge.className = 'sb-badge';
    item.appendChild(badge);
  }
  badge.textContent = count;
}

let activeNav = 'Home';
function navTo(name) {
  const item = NAV.flatMap((g) => g.items).find((i) => i.name === name);
  if (!item) return;
  if (leaveGuard()) return;
  activeNav = name;
  document.querySelectorAll('.sb-item').forEach((b) =>
    b.classList.toggle('active', b.dataset.navitem === name));
  if (item.view === 'challenge') {
    // Challenge Questions = a hard-only mixed drill straight from the bank.
    startPractice({ section: 'mixed', difficulties: ['hard'], count: 10 }, 'Challenge');
    return;
  }
  if (item.view === 'test') {
    // Practice test: a longer mixed set that reports an estimated 400-1600 score.
    startPractice({ section: 'mixed', count: 20 }, 'Practice test');
    return;
  }
  if (item.view === 'soon') {
    $('soon-title').textContent = name;
    $('soon-desc').textContent = ROADMAP[name] || 'Lumo is still building this.';
    switchView('v-soon');
  } else {
    switchView(item.view);
    if (item.view === 'v-home') renderHome();
    if (item.view === 'v-rush') renderRush();
    if (item.view === 'v-play') renderPlay();
    if (item.view === 'v-analytics') renderAnalytics();
    if (item.view === 'v-bank') renderBank();
    if (item.view === 'v-mistakes') renderMistakes();
    if (item.view === 'v-planner') renderPlanner();
    if (item.view === 'v-vocab') renderVocab();
  }
}

function switchView(id) {
  document.querySelectorAll('.view').forEach((v) => v.classList.remove('active'));
  $(id).classList.add('active');
  const showBanners = BANNER_VIEWS.has(id);
  $('promo-bar').classList.toggle('hidden', !showBanners);
  $('announce-bar').classList.toggle('hidden', !showBanners);
  document.querySelector('.main').scrollTop = 0;
}

// Warn when navigating away from an active game.
function leaveGuard() {
  if (game.phase === 'question' || game.phase === 'reveal') {
    if (!confirm('Leave the current game? Your progress in this match will be lost.')) return true;
    teardownGame();
  } else if (game.phase === 'queue') {
    cancelQueue(true);
  } else if (game.phase === 'lobby') {
    teardownGame();
  }
  return false;
}

function toast(msg) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.remove('hidden');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.add('hidden'), 3200);
}

/* ================= Networking ================= */
const ME = { code: null, playerId: null };
async function api(action, extra = {}) {
  const res = await fetch(`/api/${action}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code: ME.code, player: ME.playerId, ...extra }),
  });
  return res.json();
}

let eventSource = null;
// Resolves once the stream is actually open. Starting a game before the server
// has registered this listener would drop the first question broadcast.
function connectEvents() {
  if (eventSource) eventSource.close();
  eventSource = new EventSource(`/api/events?code=${ME.code}&player=${ME.playerId}`);
  const on = (name, fn) => eventSource.addEventListener(name, (e) => fn(JSON.parse(e.data)));
  on('lobby_update', onLobbyUpdate);
  on('host_changed', ({ hostName }) => {
    if (hostName === game.myName) { game.isHost = true; toast('You are the host now'); }
    else toast(`${hostName} is the host now`);
  });
  on('question', onQuestion);
  on('answer_progress', ({ answered, total }) => {
    if (game.answered) $('locked-note').textContent = `Locked in — ${answered} / ${total} answered`;
  });
  on('reveal', onReveal);
  on('game_over', onGameOver);
  on('back_to_lobby', (lobby) => { game.phase = 'lobby'; renderLobby(lobby); switchView('v-lobby'); });
  eventSource.onerror = () => {};

  return new Promise((resolve) => {
    let settled = false;
    const done = () => { if (!settled) { settled = true; resolve(); } };
    eventSource.addEventListener('open', done);
    setTimeout(done, 2000); // fallback so a stalled stream never blocks the UI
  });
}

/* ================= Game state ================= */
const game = {
  phase: 'idle', // idle | queue | lobby | question | reveal | over
  mode: 'solo',  // solo | party | duel
  isHost: false,
  section: 'mixed',
  currentQ: null,
  selected: null,
  answered: false,
  results: [],     // per-question true/false for the track
  total: 0,
  myScore: 0,
  startedAt: 0,
  timerInterval: null,
  clockOffset: 0,
  queueTicket: null,
  myName: '',
  queueTimers: [],
  opponent: null,
  lastBoard: [],
};

function teardownGame() {
  if (eventSource) { eventSource.close(); eventSource = null; }
  clearInterval(game.timerInterval);
  game.queueTimers.forEach(clearInterval);
  game.queueTimers = [];
  game.phase = 'idle';
  ME.code = null; ME.playerId = null;
}

/* ================= Solo / party entry ================= */
// One entry point for every single-player drill: rush, bank domain, challenge,
// planner task, and mistake review all come through here.
async function startPractice(settings, label) {
  if (!profile.name) return promptName(() => startPractice(settings, label));
  const s = {
    section: settings.section || 'mixed',
    domains: settings.domains || [],
    difficulties: settings.difficulties || [],
    ids: settings.ids || [],
    count: settings.count || 10,
  };
  const res = await api('create', { name: profile.name, settings: s });
  if (res.error) return toast(res.error);
  ME.code = res.code; ME.playerId = res.playerId;
  game.myName = res.yourName || profile.name;
  game.mode = 'solo';
  game.isHost = true;
  game.section = s.section;
  game.label = label || null;
  game.reviewing = !!(s.ids && s.ids.length);
  await connectEvents();
  await api('start');
}

function startSolo(section) {
  return startPractice({ section, count: 10 });
}

async function hostParty() {
  if (!profile.name) return promptName(hostParty);
  const res = await api('create', {
    name: profile.name,
    settings: { section: 'mixed', domains: [], difficulties: [], count: 10 },
  });
  if (res.error) return toast(res.error);
  ME.code = res.code; ME.playerId = res.playerId;
  game.myName = res.yourName || profile.name;
  game.mode = 'party'; game.isHost = true; game.section = 'mixed'; game.phase = 'lobby';
  await connectEvents();
  renderLobby(res.state);
  switchView('v-lobby');
}

async function joinParty() {
  const code = $('code-input').value.trim().toUpperCase();
  if (code.length !== 5) return toast('Party codes are 5 letters.');
  if (!profile.name) return promptName(joinParty);
  const res = await api('join', { code, name: profile.name });
  if (res.error) return toast(res.error);
  ME.code = res.code; ME.playerId = res.playerId;
  game.myName = res.yourName || profile.name;
  game.mode = 'party'; game.isHost = false; game.phase = 'lobby';
  await connectEvents();
  renderLobby(res.state);
  switchView('v-lobby');
}

/* ================= Matchmaking ================= */
let duelSection = 'mixed';
async function findMatch() {
  if (!profile.name) return promptName(findMatch);
  game.phase = 'queue';
  game.mode = 'duel';
  game.section = duelSection;
  $('queue-mode-chip').textContent = `${SECTION_LABEL[duelSection]} · 10 questions`;
  $('queue-sub').textContent = `Matching you with someone near ${profile.elo.toLocaleString()} ELO`;
  switchView('v-queue');
  const started = Date.now();
  const tick = setInterval(() => {
    const s = Math.floor((Date.now() - started) / 1000);
    $('queue-elapsed').textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')} elapsed`;
  }, 500);
  game.queueTimers.push(tick);

  const res = await api('queue', { name: profile.name, section: duelSection, count: 10 });
  if (res.matched) return enterDuel(res);
  game.queueTicket = res.ticket;
  const poll = setInterval(async () => {
    if (game.phase !== 'queue') return clearInterval(poll);
    const st = await api('queue_status', { ticket: game.queueTicket });
    if (st.matched) { clearInterval(poll); enterDuel(st); }
    else if (st.expired) { clearInterval(poll); cancelQueue(); toast('Queue timed out — try again.'); }
  }, 1500);
  game.queueTimers.push(poll);
}

async function enterDuel(res) {
  game.queueTimers.forEach(clearInterval);
  game.queueTimers = [];
  ME.code = res.code; ME.playerId = res.playerId;
  game.myName = res.yourName || profile.name;
  game.phase = 'lobby';
  switchView('v-lobby');
  await connectEvents();  // server pushes lobby_update on connect
}

function cancelQueue(silent) {
  game.queueTimers.forEach(clearInterval);
  game.queueTimers = [];
  if (game.queueTicket) api('queue_cancel', { ticket: game.queueTicket });
  game.queueTicket = null;
  game.phase = 'idle';
  if (!silent) { navTo('Play'); }
}

/* ================= Lobby ================= */
function onLobbyUpdate(lobby) {
  if (game.phase === 'lobby') renderLobby(lobby);
}

function renderLobby(lobby) {
  const isDuel = lobby.mode === 'duel';
  game.mode = isDuel ? 'duel' : game.mode;
  $('lobby-eyebrow').textContent = isDuel ? 'MATCH FOUND' : 'PARTY LOBBY';
  $('lobby-title').textContent = isDuel
    ? `1v1 Duel · ${SECTION_LABEL[lobby.settings.section]} · ${lobby.questionCount} questions`
    : `Party · ${SECTION_LABEL[lobby.settings.section]} · ${lobby.questionCount} questions`;
  $('lobby-sub').textContent = isDuel
    ? 'Same questions for both players · speed and streaks decide it · Ranked'
    : `${lobby.players.length} player${lobby.players.length === 1 ? '' : 's'} in — up to 20 can join`;
  $('lobby-code-wrap').classList.toggle('hidden', isDuel);
  if (!isDuel) $('lobby-code').textContent = lobby.code;

  const mine = lobby.players.find((p) => p.name === game.myName);
  const others = lobby.players.filter((p) => p.name !== game.myName);
  game.opponent = others[0] ? others[0].name : null;

  const cardFor = (p, them) => `
    <div class="player-card">
      <span class="lumo round ${them ? 'pink' : 'lilac'}"></span>
      <span class="n">${esc(p.name)}</span>
      <span class="s">${p.isHost ? 'Host · ' : ''}${them ? '' : `${profile.elo.toLocaleString()} ELO · `}${p.connected ? 'connected' : 'disconnected'}</span>
      <span class="ready-pill ${p.ready || (!isDuel && p.isHost) ? 'yes' : 'no'}">
        <span class="${p.ready || (!isDuel && p.isHost) ? 'dot-g' : 'dot-a'}"></span>
        ${p.ready ? 'Ready' : (isDuel ? 'Getting ready…' : (p.isHost ? 'Host' : 'Joined'))}
      </span>
    </div>`;

  let html = '';
  if (isDuel && mine && others.length === 1) {
    html = cardFor(mine, false)
      + `<div class="vs-block"><span class="vs">VS</span><span class="in">${others[0].ready && mine.ready ? 'starting…' : 'waiting for ready'}</span></div>`
      + cardFor(others[0], true);
  } else {
    html = lobby.players.map((p) => cardFor(p, p.name !== game.myName)).join('');
  }
  $('lobby-players').innerHTML = html;

  const btn = $('btn-ready');
  if (isDuel) {
    btn.textContent = mine && mine.ready ? 'Ready — waiting…' : 'Ready up';
    btn.disabled = !!(mine && mine.ready);
    btn.classList.remove('hidden');
  } else if (game.isHost) {
    btn.textContent = 'Start game';
    btn.disabled = false;
    btn.classList.remove('hidden');
  } else {
    btn.textContent = 'Waiting for the host…';
    btn.disabled = true;
  }
}

$('btn-ready').onclick = async () => {
  if (game.mode === 'duel') await api('ready');
  else await api('start');
};
$('btn-leave-lobby').onclick = () => { teardownGame(); navTo('Play'); };

/* ================= Match ================= */
function onQuestion(q) {
  game.phase = 'question';
  game.currentQ = q;
  game.selected = null;
  game.answered = false;
  game.total = q.total;
  game.clockOffset = q.serverNow - Date.now();
  if (q.index === 0) { game.startedAt = Date.now(); game.results = []; game.myScore = 0; game.lastBoard = []; }

  const modeLbl = game.mode === 'duel' ? '1V1 DUEL'
    : game.mode === 'party' ? 'PARTY'
    : (game.label ? game.label.toUpperCase() : 'SOLO RUSH');
  $('match-mode').textContent = `${modeLbl} · ${q.domain.toUpperCase()}`;
  $('match-progress').textContent = `Question ${q.index + 1} of ${q.total}`;
  $('q-kicker').textContent = `${q.domain} · ${q.difficulty}`;
  const passage = $('q-passage');
  if (q.passage) { passage.textContent = q.passage; passage.classList.remove('hidden'); }
  else passage.classList.add('hidden');
  $('q-text').textContent = q.question;

  const stack = !!q.passage || q.choices.some((c) => c.length > 55);
  const grid = $('choice-grid');
  grid.className = `choice-grid${stack ? ' stack' : ''}`;
  grid.innerHTML = q.choices.map((c, i) => `
    <button class="mchoice" data-i="${i}">
      <span class="key">${LETTERS[i]}</span>
      <span class="val">${esc(c)}</span>
    </button>`).join('');
  grid.querySelectorAll('.mchoice').forEach((b) => {
    b.onclick = () => {
      if (game.answered) return;
      game.selected = parseInt(b.dataset.i, 10);
      grid.querySelectorAll('.mchoice').forEach((x) => x.classList.toggle('sel', x === b));
      $('btn-lock').disabled = false;
    };
  });

  $('btn-lock').disabled = true;
  $('btn-lock').classList.remove('hidden');
  $('locked-note').classList.add('hidden');
  $('match-actions').classList.remove('hidden');
  $('reveal-card').classList.add('hidden');
  $('speed-note').textContent = `Base ${q.basePoints} pts. Answer fast for up to 2×; streaks add up to +500.`;
  $('tip-text').textContent = game.mode === 'duel'
    ? 'Hints are off in ranked duels. Lumo explains every question at the reveal.'
    : 'Lumo will explain the answer as soon as the question closes.';

  // tools reset per question; calculator is math-only, like the real test
  setHighlightMode(false);
  openCalc(false);
  $('btn-calc').classList.toggle('hidden', q.section !== 'math');
  $('btn-highlight').classList.toggle('hidden', !q.passage);

  renderTrack(q.index);
  renderBars();
  startTimer(q.endsAt, q.durationMs);
  switchView('v-match');
}

$('btn-lock').onclick = async () => {
  if (game.selected === null || game.answered) return;
  game.answered = true;
  $('btn-lock').disabled = true;
  document.querySelectorAll('#choice-grid .mchoice').forEach((b) => (b.disabled = true));
  $('locked-note').textContent = `Locked in ${LETTERS[game.selected]} — waiting…`;
  $('locked-note').classList.remove('hidden');
  await api('answer', { choice: game.selected });
};

function startTimer(endsAt, durationMs) {
  clearInterval(game.timerInterval);
  const tick = () => {
    const remaining = Math.max(0, endsAt - (Date.now() + game.clockOffset));
    const secs = Math.ceil(remaining / 1000);
    $('match-timer-txt').textContent = `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, '0')}`;
    $('match-timer').classList.toggle('low', secs <= 10);
    $('speed-fill').style.width = `${(remaining / durationMs) * 100}%`;
    if (remaining <= 0) clearInterval(game.timerInterval);
  };
  tick();
  game.timerInterval = setInterval(tick, 200);
}

function renderBars() {
  const hth = $('hth');
  const board = game.lastBoard;
  const meRow = board.find((p) => p.name === game.myName) || { score: game.myScore };
  // Before the first reveal there is no leaderboard yet, so show the opponent
  // at zero rather than hiding their bar for a whole question.
  const oppRow = game.opponent
    ? (board.find((p) => p.name === game.opponent) || { name: game.opponent, score: 0 })
    : null;
  const max = Math.max(meRow.score || 0, oppRow ? oppRow.score : 0, 1);
  const others = board.filter((p) => p.name !== game.myName && (!oppRow || p.name !== oppRow.name)).length;

  let html = `
    <div class="hth-side">
      <div class="r"><span class="ava lumo round lilac"></span><span class="n">${esc(game.myName || 'You')}</span><span class="grow"></span><span class="pts tabnum">${meRow.score || 0} pts</span></div>
      <div class="hth-track"><div class="hth-fill" style="width:${Math.round(((meRow.score || 0) / max) * 100)}%"></div></div>
    </div>`;
  if (oppRow) {
    html += `
    <div class="hth-side them">
      <div class="r"><span class="ava lumo round pink"></span><span class="n">${esc(oppRow.name)}${others ? ` <span class="muted" style="font-weight:500;font-size:12px">+${others} more</span>` : ''}</span><span class="grow"></span><span class="pts tabnum">${oppRow.score} pts</span></div>
      <div class="hth-track"><div class="hth-fill" style="width:${Math.round((oppRow.score / max) * 100)}%"></div></div>
    </div>`;
  }
  hth.className = `hth${oppRow ? '' : ' solo'}`;
  hth.innerHTML = html;
}

function renderTrack(currentIndex) {
  const cells = [];
  for (let i = 0; i < game.total; i++) {
    let cls = '';
    if (i < game.results.length) cls = game.results[i] ? 'me' : 'them';
    else if (i === currentIndex && game.phase === 'question') cls = 'now';
    cells.push(`<div class="q ${cls}">${i + 1}</div>`);
  }
  $('qtrack').innerHTML = cells.join('');
}


/* ================= Question tools: highlighter + calculator ================= */
let highlightOn = false;

function setHighlightMode(on) {
  highlightOn = on;
  $('btn-highlight').classList.toggle('on', on);
  $('q-passage').classList.toggle('marking', on);
  $('q-text').classList.toggle('marking', on);
  if (on) toast('Select text in the question to highlight it.');
}

// Wraps the current selection in <mark>, or unwraps if it is already highlighted.
function applyHighlight() {
  if (!highlightOn) return;
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed) return;
  const range = sel.getRangeAt(0);
  const host = range.commonAncestorContainer.parentElement;
  if (!host || !host.closest('#q-passage, #q-text')) return;

  const existing = host.closest('mark');
  if (existing) {                        // click inside a highlight removes it
    const text = document.createTextNode(existing.textContent);
    existing.replaceWith(text);
    sel.removeAllRanges();
    return;
  }
  try {
    const mark = document.createElement('mark');
    mark.appendChild(range.extractContents());
    range.insertNode(mark);
    sel.removeAllRanges();
  } catch {
    toast('That selection spans too much to highlight — try a smaller piece.');
  }
}

document.addEventListener('mouseup', applyHighlight);
$('btn-highlight').onclick = () => setHighlightMode(!highlightOn);

/* ---- calculator ---- */
const calc = { range: 10, expr: '' };

function openCalc(open) {
  $('calc-panel').classList.toggle('hidden', !open);
  $('btn-calc').classList.toggle('on', open);
  if (open) { $('calc-input').focus(); drawGraph(); }
}
$('btn-calc').onclick = () => openCalc($('calc-panel').classList.contains('hidden'));
$('btn-calc-close').onclick = () => openCalc(false);

function runCalc() {
  const raw = $('calc-input').value.trim();
  calc.expr = raw;
  const out = $('calc-out');
  if (!raw) {
    out.textContent = 'Type an expression. Use x to graph it.';
    out.className = 'calc-out';
    drawGraph();
    return;
  }
  try {
    const { fn, usesX } = LumoCalc.compile(raw);
    if (usesX) {
      out.textContent = `y = ${raw.replace(/^\s*y\s*=/i, '').trim()}  ·  graphed below`;
      out.className = 'calc-out';
    } else {
      const v = fn(0);
      out.textContent = Number.isFinite(v)
        ? String(Math.round(v * 1e10) / 1e10)
        : 'undefined';
      out.className = 'calc-out val';
    }
  } catch (e) {
    out.textContent = e.message;
    out.className = 'calc-out err';
  }
  drawGraph();
}
$('calc-input').addEventListener('input', runCalc);

function drawGraph() {
  const cv = $('calc-graph');
  const ctx = cv.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const w = cv.clientWidth || 300, h = 200;
  if (cv.width !== w * dpr) { cv.width = w * dpr; cv.height = h * dpr; }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);

  const R = calc.range;
  const sx = (x) => ((x + R) / (2 * R)) * w;
  const sy = (y) => h - ((y + R) / (2 * R)) * h;

  // grid
  ctx.strokeStyle = '#EEF2F6';
  ctx.lineWidth = 1;
  const step = R <= 5 ? 1 : R <= 20 ? 5 : 10;
  for (let g = -R; g <= R; g += step) {
    ctx.beginPath(); ctx.moveTo(sx(g), 0); ctx.lineTo(sx(g), h); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(0, sy(g)); ctx.lineTo(w, sy(g)); ctx.stroke();
  }
  // axes
  ctx.strokeStyle = '#CBD5E1';
  ctx.lineWidth = 1.2;
  ctx.beginPath(); ctx.moveTo(0, sy(0)); ctx.lineTo(w, sy(0)); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(sx(0), 0); ctx.lineTo(sx(0), h); ctx.stroke();

  $('calc-range').textContent = `x: −${R} to ${R}`;
  if (!calc.expr) return;

  let f;
  try {
    const c = LumoCalc.compile(calc.expr);
    if (!c.usesX) return;
    f = c.fn;
  } catch { return; }

  ctx.strokeStyle = '#6D28D9';
  ctx.lineWidth = 2;
  ctx.beginPath();
  let drawing = false;
  for (let px = 0; px <= w; px++) {
    const x = (px / w) * 2 * R - R;
    let y;
    try { y = f(x); } catch { y = NaN; }
    if (!Number.isFinite(y) || Math.abs(y) > R * 6) { drawing = false; continue; }
    const py = sy(y);
    if (!drawing) { ctx.moveTo(px, py); drawing = true; }
    else ctx.lineTo(px, py);
  }
  ctx.stroke();
}

$('calc-zoom-in').onclick = () => { calc.range = Math.max(1, calc.range / 2); drawGraph(); };
$('calc-zoom-out').onclick = () => { calc.range = Math.min(1000, calc.range * 2); drawGraph(); };
window.addEventListener('resize', () => { if (!$('calc-panel').classList.contains('hidden')) drawGraph(); });

/* ================= Reveal ================= */
function onReveal(data) {
  game.phase = 'reveal';
  clearInterval(game.timerInterval);
  const q = game.currentQ;
  const mine = game.selected !== null && game.answered ? game.selected : null;
  const correct = mine === data.correctIndex;

  document.querySelectorAll('#choice-grid .mchoice').forEach((b) => {
    const i = parseInt(b.dataset.i, 10);
    b.disabled = true;
    if (i === data.correctIndex) b.classList.add('correct');
    else if (i === mine) b.classList.add('wrong');
  });

  $('match-actions').classList.add('hidden');
  const card = $('reveal-card');
  card.classList.remove('hidden');
  const title = $('reveal-title');
  if (mine === null) { title.innerHTML = `${icon('planner', 16, 2)} Time's up — no answer`; title.className = 't bad'; }
  else if (correct) { title.textContent = 'Correct'; title.className = 't good'; }
  else { title.textContent = `Not quite — the answer was ${LETTERS[data.correctIndex]}`; title.className = 't bad'; }
  $('reveal-ex').textContent = data.explanation;
  $('reveal-counts').innerHTML = data.counts
    .map((n, i) => `<span class="count-pill ${i === data.correctIndex ? 'correct' : ''}">${LETTERS[i]}: ${n}</span>`)
    .join('');

  game.results.push(correct);
  game.lastBoard = data.leaderboard;
  const meRow = data.leaderboard.find((p) => p.name === game.myName);
  if (meRow) game.myScore = meRow.score;
  renderBars();
  renderTrack(-1);

  // ---- stats, mistake log, domain mastery ----
  profile.attempted += 1;
  if (correct) { profile.correct += 1; profile.solved[q.section] = (profile.solved[q.section] || 0) + 1; }
  else profile.errors += 1;
  if (meRow) profile.bestStreak = Math.max(profile.bestStreak, meRow.streak || 0);

  const ds = profile.domainStats[q.domain] || { correct: 0, total: 0 };
  ds.total += 1;
  if (correct) ds.correct += 1;
  profile.domainStats[q.domain] = ds;

  if (game.reviewing) {
    profile.retryTotal += 1;
    if (correct) profile.retryCorrect += 1;
  }

  if (q.id) {
    const idx = profile.mistakes.findIndex((m) => m.id === q.id);
    if (correct) {
      // Answering it right retires it from the review list.
      if (idx !== -1) profile.mistakes.splice(idx, 1);
    } else {
      const entry = {
        id: q.id, question: q.question, passage: q.passage || null, choices: q.choices,
        domain: q.domain, skill: q.skill, difficulty: q.difficulty,
        mine, correctIndex: data.correctIndex, explanation: data.explanation, when: Date.now(),
      };
      if (idx !== -1) profile.mistakes[idx] = entry;
      else profile.mistakes.unshift(entry);
      profile.mistakes = profile.mistakes.slice(0, 60);
    }
  }
  saveProfile();

  const nextBtn = $('btn-next');
  const note = $('reveal-note');
  if (game.mode === 'duel') {
    nextBtn.classList.add('hidden');
    let secs = data.autoAdvanceSecs || 7;
    note.textContent = data.isLast ? `Results in ${secs}s…` : `Next question in ${secs}s…`;
    const iv = setInterval(() => {
      secs -= 1;
      if (secs <= 0 || game.phase !== 'reveal') return clearInterval(iv);
      note.textContent = data.isLast ? `Results in ${secs}s…` : `Next question in ${secs}s…`;
    }, 1000);
  } else if (game.isHost) {
    nextBtn.textContent = data.isLast ? 'See results' : 'Next question';
    nextBtn.classList.remove('hidden');
    note.textContent = '';
  } else {
    nextBtn.classList.add('hidden');
    note.textContent = 'Waiting for the host…';
  }
}

$('btn-next').onclick = () => api('next');

/* ================= Game over ================= */
function onGameOver(data) {
  game.phase = 'over';
  const board = data.leaderboard;
  const meRow = board.find((p) => p.name === game.myName) || { score: 0, correct: 0 };
  const myRank = board.indexOf(board.find((p) => p.name === game.myName)) + 1;
  const secs = Math.round((Date.now() - game.startedAt) / 1000);

  // profile updates
  profile.points += meRow.score || 0;
  profile.lastPlayed = Date.now();
  profile.sessions.unshift({
    qs: data.total, correct: meRow.correct || 0, secs, when: Date.now(),
    section: game.section, bestStreak: profile.bestStreak,
  });
  profile.sessions = profile.sessions.slice(0, 12);

  let sub = `${meRow.correct || 0}/${data.total} correct · ${fmtDur(secs)}`;
  if (game.mode === 'duel' && game.opponent) {
    const opp = board.find((p) => p.name === game.opponent) || { score: 0 };
    const won = (meRow.score || 0) > opp.score;
    const tie = (meRow.score || 0) === opp.score;
    const delta = won ? 24 : tie ? 0 : -18;
    profile.elo = Math.max(100, profile.elo + delta);
    if (won) profile.wins += 1; else if (!tie) profile.losses += 1;
    $('result-hero').textContent = won ? 'Victory' : tie ? 'Tie game' : 'Defeat';
    sub += ` · ${delta >= 0 ? '+' : ''}${delta} ELO → ${profile.elo.toLocaleString()}`;
  } else if (game.label === 'Practice test') {
    const acc = data.total ? (meRow.correct || 0) / data.total : 0;
    const est = Math.round((400 + acc * 1200) / 10) * 10;
    $('result-hero').textContent = `Estimated score ${est.toLocaleString()}`;
    sub += ' · rough estimate from 20 questions, not an official score';
  } else {
    $('result-hero').textContent = game.mode === 'solo' ? 'Session complete'
      : myRank === 1 ? 'You win' : `You placed ${ordinal(myRank)}`;
  }
  saveProfile();
  $('result-sub').textContent = sub;

  $('result-rows').innerHTML = board.map((p, i) => `
    <div class="result-row ${p.name === game.myName ? 'me' : ''}">
      <span class="rank">${i + 1}</span>
      <span class="grow">${esc(p.name)} <span class="detail">· ${p.correct}/${data.total} correct</span></span>
      <span class="sc tabnum">${p.score}</span>
    </div>`).join('');

  const myBd = data.breakdowns[game.myName] || {};
  const rows = Object.entries(myBd);
  $('result-bd').innerHTML = rows.length ? rows.map(([domain, r]) => {
    const pct = Math.round((r.correct / r.total) * 100);
    return `<div class="bd-row">
      <span class="lbl">${esc(domain)}</span>
      <span class="track"><span class="fill" style="width:${pct}%;background:var(--purple)"></span></span>
      <span class="val">${r.correct}/${r.total}</span>
    </div>`;
  }).join('') : '<span class="muted" style="font-size:13px">No answers recorded.</span>';

  $('btn-play-again').classList.toggle('hidden', !(game.mode === 'party' && game.isHost) && game.mode !== 'solo');
  switchView('v-results');
}

$('btn-play-again').onclick = async () => {
  if (game.mode === 'solo') {
    const section = game.section;
    teardownGame();
    startSolo(section);
  } else {
    await api('play_again');
  }
};
$('btn-back-play').onclick = () => { teardownGame(); navTo('Play'); };

/* ================= Home ================= */
function renderHome() {
  const h = new Date().getHours();
  $('greet-word').textContent = h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
  $('greet-name').textContent = profile.name || 'friend';
  $('stat-streak').textContent = profile.dayStreak;
  $('stat-points').textContent = profile.points.toLocaleString();
  $('an-attempted').textContent = profile.attempted.toLocaleString();
  $('an-accuracy').textContent = profile.attempted ? `${Math.round((profile.correct / profile.attempted) * 100)}%` : '—';
  $('an-sessions').textContent = profile.sessions.length;
  $('an-errors').textContent = profile.errors;

  api('bank').then((res) => {
    if (res && res.total) $('home-bank-count').textContent = res.total.toLocaleString();
  }).catch(() => {});

  const today = new Date();
  $('plan-sub').textContent = `Today · ${today.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}`;

  // Home shows the first few tasks of the same weekly plan the Planner owns, so
  // checking one off here is the same action as checking it off there.
  if (!profile.plan || profile.plan.week !== weekKey()) buildPlan();
  const tasks = profile.plan.tasks.slice(0, 3);
  $('plan-tasks').innerHTML = tasks.map((t) => `
    <div class="task">
      <div class="row1">
        <button class="chk" data-home-check="${t.id}" style="${t.done ? 'background:var(--purple);border-color:var(--purple)' : ''}" aria-label="Mark ${esc(t.label)} done">${t.done ? icon('play', 11, 3) : ''}</button>
        <span class="name" style="${t.done ? 'color:var(--slate-4);text-decoration:line-through' : ''}">${esc(t.label)}</span>
        ${t.section === 'review' && !profile.mistakes.length ? '<span class="tag tag-overdue">nothing to review</span>' : ''}
      </div>
      <div class="row2">
        <span class="tag-subject">${t.domain ? esc(t.domain) : (t.section === 'review' ? 'Mistakes' : 'Mixed')}</span>
        <span class="time">${icon('planner', 13, 2)}${t.count} questions</span>
        <span class="spacer"></span>
        <button class="btn-soft" data-home-start="${t.id}">Start ${icon('play', 12, 2.2)}</button>
      </div>
    </div>`).join('');

  document.querySelectorAll('[data-home-check]').forEach((b) => {
    b.onclick = () => {
      const t = profile.plan.tasks.find((x) => x.id === b.dataset.homeCheck);
      t.done = !t.done;
      saveProfile();
      renderHome();
      refreshPlannerBadge();
    };
  });
  document.querySelectorAll('[data-home-start]').forEach((b) => {
    b.onclick = () => startPlanTask(b.dataset.homeStart);
  });

  bindSoloButtons();
  renderExamCountdown();
}

function renderExamCountdown(numsId = 'exam-nums', dateId = 'exam-date') {
  const target = new Date(profile.testDate + 'T08:00:00');
  const diff = Math.max(0, target - Date.now());
  const days = Math.floor(diff / 86400000);
  const hrs = Math.floor((diff % 86400000) / 3600000);
  const min = Math.floor((diff % 3600000) / 60000);
  $(numsId).innerHTML = `
    <span class="grp"><span class="n tabnum">${days}</span><span class="u">days</span></span>
    <span class="grp"><span class="n tabnum">${String(hrs).padStart(2, '0')}</span><span class="u">hrs</span></span>
    <span class="grp"><span class="n tabnum">${String(min).padStart(2, '0')}</span><span class="u">min</span></span>`;
  $(dateId).textContent = target.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });
}

function switchTestDate() {
  const d = prompt('When is your SAT? (YYYY-MM-DD)', profile.testDate);
  if (!d) return;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(d) || isNaN(new Date(d + 'T08:00:00'))) {
    return toast('Use the format YYYY-MM-DD, for example 2026-10-03');
  }
  profile.testDate = d;
  saveProfile();
  renderExamCountdown();
  if ($('v-planner').classList.contains('active')) renderExamCountdown('planner-exam-nums', 'planner-exam-date');
  toast('Test date updated');
}

$('btn-switch-date').onclick = (e) => { e.preventDefault(); switchTestDate(); };
$('btn-review-errors').onclick = () => {
  const ids = profile.mistakes.slice(0, 10).map((m) => m.id);
  if (ids.length) return startPractice({ ids, count: ids.length }, 'Review');
  navTo('Saved & Mistakes');
};

/* Banner countdown — ticks down to the user's own test date, not a fake sale. */
function tickPromo() {
  const el = $('promo-count');
  const paint = () => {
    const diff = Math.max(0, new Date(profile.testDate + 'T08:00:00') - Date.now());
    const d = Math.floor(diff / 86400000);
    const h = Math.floor((diff % 86400000) / 3600000);
    const m = Math.floor((diff % 3600000) / 60000);
    const s = Math.floor((diff % 60000) / 1000);
    el.innerHTML = `${d}<span>d</span> ${String(h).padStart(2, '0')}<span>h</span> ${String(m).padStart(2, '0')}<span>m</span> ${String(s).padStart(2, '0')}<span>s</span>`;
  };
  paint();
  setInterval(paint, 1000);
}
$('btn-promo-cta').onclick = () => navTo('Study Planner');

/* ================= Rush ================= */
let bankStats = { math: 32, rw: 32 };
async function renderRush() {
  try {
    const res = await api('stats');
    if (res.bank) bankStats = res.bank;
  } catch {}
  const rwSolved = Math.min(profile.solved.rw || 0, bankStats.rw);
  const mathSolved = Math.min(profile.solved.math || 0, bankStats.math);
  $('rw-solved').textContent = `${rwSolved} of ${bankStats.rw} solved`;
  $('math-solved').textContent = `${mathSolved} of ${bankStats.math} solved`;
  const rwPct = Math.round((rwSolved / bankStats.rw) * 100);
  const mathPct = Math.round((mathSolved / bankStats.math) * 100);
  $('rw-pct').textContent = `${rwPct}%`;
  $('math-pct').textContent = `${mathPct}%`;
  $('rw-fill').style.width = `${rwPct}%`;
  $('math-fill').style.width = `${mathPct}%`;

  const list = $('session-list');
  if (!profile.sessions.length) {
    list.innerHTML = `<div class="session-row"><div class="body"><span class="cnt">No sessions yet</span><span class="ago" style="font-size:13px">Hit Continue on a subject above to play your first rush.</span></div></div>`;
  } else {
    list.innerHTML = profile.sessions.map((s) => {
      const pct = Math.round((s.correct / s.qs) * 100);
      return `<div class="session-row">
        <div class="body">
          <div class="l1"><span class="cnt">${s.qs} questions</span><span class="ago">${timeAgo(s.when)}</span></div>
          <div class="l2">
            <span class="m"><svg class="ic" style="width:13px;height:13px;color:#0EA5E9;stroke-width:2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5"/><path d="M12 8v4.4l3 1.6"/></svg>${fmtDur(s.secs)}</span>
            <span class="m"><svg class="ic" style="width:13px;height:13px;color:#6D28D9;stroke-width:2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5"/><path d="M12 12l4-3"/></svg>${s.correct}/${s.qs} (${pct}%)</span>
            <span class="m"><svg class="ic ic-fill" style="width:13px;height:13px;color:#F97316" viewBox="0 0 24 24"><path d="M13 2c1 4-3 5-3 8a3 3 0 0 0 6 0c2 2 3 4 3 6a7 7 0 0 1-14 0c0-6 8-8 8-14z"/></svg>${s.bestStreak} streak</span>
            <span class="m">${SECTION_LABEL[s.section] || 'Mixed'}</span>
          </div>
        </div>
        <button class="btn-soft" data-solo="${s.section}">Replay ${icon('play', 12, 2.2)}</button>
      </div>`;
    }).join('');
  }
  bindSoloButtons();
}

/* ================= Play ================= */
const SAMPLE_FRIENDS = [
  { name: 'Priya M.', status: 'In a duel · Math', dot: '#F59E0B', btn: 'Spectate', solid: false },
  { name: 'Dev K.', status: 'Online', dot: '#22C55E', btn: 'Challenge', solid: true },
  { name: 'Sofia R.', status: 'Online · 1,410 ELO', dot: '#22C55E', btn: 'Challenge', solid: true },
  { name: 'Marcus T.', status: 'Studying Vocab', dot: '#22C55E', btn: 'Challenge', solid: true },
  { name: 'Hana L.', status: 'Last online 2h ago', dot: '#CBD5E1', btn: 'Invite', solid: false },
  { name: 'Owen B.', status: 'Last online yesterday', dot: '#CBD5E1', btn: 'Invite', solid: false },
];
async function renderPlay() {
  $('elo-pill').textContent = `${profile.elo.toLocaleString()} ELO`;
  const wins = profile.wins % 10;
  $('ladder-fill').style.width = `${wins * 10}%`;
  $('ladder-lbl').textContent = `${wins} / 10 wins`;
  $('ladder-note').textContent = profile.wins
    ? `Win ${10 - wins} more duel${10 - wins === 1 ? '' : 's'} to climb a tier.`
    : 'Win duels to climb the ladder.';
  $('friends-list').innerHTML = SAMPLE_FRIENDS.map((f) => `
    <div class="friend">
      <span class="ava"><span class="circ"></span><span class="st" style="background:${f.dot}"></span></span>
      <span class="body"><span class="n">${f.name}</span><span class="s">${f.status}</span></span>
      <button class="friend-btn ${f.solid ? 'solid' : 'soft'}" data-soon="Friend accounts">${f.btn}</button>
    </div>`).join('');
  bindSoonButtons();
  try {
    const res = await api('stats');
    $('online-count').textContent = Math.max(1, res.online || 0).toLocaleString();
  } catch { $('online-count').textContent = '1'; }
}

document.querySelectorAll('#duel-modes .duel-mode').forEach((b) => {
  b.onclick = () => {
    duelSection = b.dataset.sec;
    document.querySelectorAll('#duel-modes .duel-mode').forEach((x) => x.classList.toggle('sel', x === b));
  };
});
$('btn-find-match').onclick = findMatch;
$('btn-host-party').onclick = hostParty;
$('btn-join-party').onclick = joinParty;
$('btn-squad').onclick = hostParty;
$('btn-queue-cancel').onclick = () => cancelQueue();
$('btn-queue-practice').onclick = () => { cancelQueue(true); startSolo(duelSection); };

/* ================= Search ================= */
let searchHits = [];

async function runSearch(q) {
  const res = await api('search', { q });
  searchHits = res.results || [];
  $('search-summary').textContent = searchHits.length
    ? `${searchHits.length} question${searchHits.length === 1 ? '' : 's'} matching "${q}"`
    : `No questions match "${q}"`;
  $('btn-practice-results').classList.toggle('hidden', !searchHits.length);
  $('search-results').innerHTML = searchHits.length
    ? searchHits.map((r) => `
      <div class="mistake">
        <div class="top">
          <span class="kicker">${esc(r.domain)} · ${esc(r.difficulty)}</span>
          <span class="tag-subject">${esc(r.skill)}</span>
        </div>
        <div class="qt">${esc(r.question)}</div>
        <div class="acts"><button class="btn-soft" data-search-id="${esc(r.id)}">Practice this one</button></div>
      </div>`).join('')
    : `<div class="empty-note">
        <span class="lumo"><span class="dot"></span></span>
        <span class="t">Nothing found</span>
        <span class="d">Try a domain ("algebra"), a skill ("transitions"), a difficulty ("hard"), or a word from a question ("triangle").</span>
      </div>`;
  document.querySelectorAll('[data-search-id]').forEach((b) => {
    b.onclick = () => startPractice({ ids: [b.dataset.searchId], count: 1 }, 'Search');
  });
  // keep the sidebar from highlighting a stale page
  document.querySelectorAll('.sb-item').forEach((b) => b.classList.remove('active'));
  switchView('v-search');
}

$('search-input').addEventListener('keydown', (e) => {
  if (e.key !== 'Enter') return;
  const q = e.target.value.trim();
  if (q.length < 2) return toast('Type at least two characters to search.');
  runSearch(q);
});
$('btn-practice-results').onclick = () => {
  const ids = searchHits.slice(0, 20).map((r) => r.id);
  if (!ids.length) return;
  startPractice({ ids, count: ids.length }, 'Search');
};

/* ================= Question Bank ================= */
const bankFilter = { difficulty: '', count: 10 };
let bankData = null;

async function renderBank() {
  if (!bankData) {
    const res = await api('bank');
    bankData = res.domains || [];
    $('bank-total').textContent = (res.total || 0).toLocaleString();
  }
  const card = (d) => {
    const st = profile.domainStats[d.domain] || { correct: 0, total: 0 };
    const pct = st.total ? Math.round((st.correct / st.total) * 100) : 0;
    const topSkills = d.skills.slice(0, 3).map((s) => s.skill).join(' · ');
    return `<div class="bank-card">
      <div class="top">
        <span class="name">${esc(d.domain)}</span>
        <span class="count">${d.total} questions</span>
      </div>
      <div class="diff-chips">
        <span class="diff-chip e">${d.easy} easy</span>
        <span class="diff-chip m">${d.medium} medium</span>
        <span class="diff-chip h">${d.hard} hard</span>
      </div>
      <div class="skills">${esc(topSkills)}${d.skills.length > 3 ? ` and ${d.skills.length - 3} more` : ''}</div>
      <div class="foot">
        <span class="mastery">
          ${st.total ? `${pct}% correct` : 'Not attempted'}
          <span class="track"><span class="fill" style="width:${pct}%"></span></span>
        </span>
        <button class="btn-soft" data-bank-domain="${esc(d.domain)}">Practice ${icon('play', 12, 2.2)}</button>
      </div>
    </div>`;
  };
  $('bank-rw').innerHTML = bankData.filter((d) => d.section === 'rw').map(card).join('');
  $('bank-math').innerHTML = bankData.filter((d) => d.section === 'math').map(card).join('');
  document.querySelectorAll('[data-bank-domain]').forEach((b) => {
    b.onclick = () => {
      const domain = b.dataset.bankDomain;
      startPractice({
        section: DOMAIN_SECTION[domain] || 'mixed',
        domains: [domain],
        difficulties: bankFilter.difficulty ? [bankFilter.difficulty] : [],
        count: bankFilter.count,
      }, 'Bank');
    };
  });
}

document.querySelectorAll('#bank-diff .seg-btn').forEach((b) => {
  b.onclick = () => {
    bankFilter.difficulty = b.dataset.diff;
    document.querySelectorAll('#bank-diff .seg-btn').forEach((x) => x.classList.toggle('active', x === b));
  };
});
document.querySelectorAll('#bank-count .seg-btn').forEach((b) => {
  b.onclick = () => {
    bankFilter.count = parseInt(b.dataset.count, 10);
    document.querySelectorAll('#bank-count .seg-btn').forEach((x) => x.classList.toggle('active', x === b));
  };
});

/* ================= Saved & Mistakes ================= */
function renderMistakes() {
  const list = profile.mistakes;
  $('mk-count').textContent = list.length;
  $('mk-retry').textContent = profile.retryTotal
    ? `${Math.round((profile.retryCorrect / profile.retryTotal) * 100)}%` : '—';

  const attempted = Object.entries(profile.domainStats).filter(([, s]) => s.total >= 2);
  if (attempted.length) {
    attempted.sort((a, b) => (a[1].correct / a[1].total) - (b[1].correct / b[1].total));
    $('mk-weak').textContent = attempted[0][0];
  } else {
    $('mk-weak').textContent = '—';
  }

  $('btn-review-all').disabled = !list.length;
  const el = $('mistake-list');
  if (!list.length) {
    el.innerHTML = `<div class="empty-note">
      <span class="lumo"><span class="dot"></span></span>
      <span class="t">Nothing missed yet</span>
      <span class="d">Questions you get wrong land here with the full explanation. Answer one correctly on review and it drops off the list.</span>
      <button class="btn btn-primary" style="font-size:13px;padding:9px 18px" data-nav="Question Rush">Start a rush</button>
    </div>`;
    bindNavButtons();
    return;
  }
  el.innerHTML = list.map((m) => `
    <div class="mistake">
      <div class="top">
        <span class="kicker">${esc(m.domain)} · ${esc(m.difficulty)}</span>
        <span class="tag-subject">${esc(m.skill)}</span>
      </div>
      ${m.passage ? `<div class="why" style="border-left-color:var(--border)">${esc(m.passage.slice(0, 220))}${m.passage.length > 220 ? '…' : ''}</div>` : ''}
      <div class="qt">${esc(m.question)}</div>
      <div class="answers">
        <span class="ans-chip mine">You: ${m.mine === null || m.mine === undefined ? 'no answer' : `${LETTERS[m.mine]}. ${esc(String(m.choices[m.mine]).slice(0, 40))}`}</span>
        <span class="ans-chip right">Correct: ${LETTERS[m.correctIndex]}. ${esc(String(m.choices[m.correctIndex]).slice(0, 40))}</span>
      </div>
      <div class="why">${esc(m.explanation)}</div>
      <div class="acts">
        <button class="btn-soft" data-retry-id="${esc(m.id)}">Retry this one</button>
        <button class="btn-soft" data-forget-id="${esc(m.id)}">Remove</button>
      </div>
    </div>`).join('');

  document.querySelectorAll('[data-retry-id]').forEach((b) => {
    b.onclick = () => startPractice({ ids: [b.dataset.retryId], count: 1 }, 'Review');
  });
  document.querySelectorAll('[data-forget-id]').forEach((b) => {
    b.onclick = () => {
      profile.mistakes = profile.mistakes.filter((m) => m.id !== b.dataset.forgetId);
      saveProfile();
      renderMistakes();
    };
  });
}

$('btn-review-all').onclick = () => {
  const ids = profile.mistakes.slice(0, 20).map((m) => m.id);
  if (!ids.length) return toast('No missed questions to review yet.');
  startPractice({ ids, count: ids.length }, 'Review');
};
$('btn-clear-mistakes').onclick = () => {
  if (!profile.mistakes.length) return;
  if (!confirm(`Clear all ${profile.mistakes.length} saved mistakes?`)) return;
  profile.mistakes = [];
  saveProfile();
  renderMistakes();
};

/* ================= Study Planner ================= */
function weekKey() {
  const d = new Date();
  const onejan = new Date(d.getFullYear(), 0, 1);
  return `${d.getFullYear()}-W${Math.ceil(((d - onejan) / 86400000 + onejan.getDay() + 1) / 7)}`;
}

function buildPlan() {
  const weak = weakestDomains(3);
  const tasks = weak.map((w, i) => ({
    id: `d${i}`,
    label: `${w.domain} drill`,
    domain: w.domain,
    section: DOMAIN_SECTION[w.domain],
    count: 10,
    done: false,
  }));
  tasks.push({ id: 'mixed', label: 'Mixed set: all domains', domain: null, section: 'mixed', count: 10, done: false });
  tasks.push({ id: 'review', label: 'Review your missed questions', domain: null, section: 'review', count: 10, done: false });
  profile.plan = { week: weekKey(), tasks };
  saveProfile();
}

// Launching a plan task marks it done and routes to the right kind of session.
function startPlanTask(id) {
  const t = profile.plan.tasks.find((x) => x.id === id);
  if (!t) return;
  if (t.section === 'review') {
    const ids = profile.mistakes.slice(0, 10).map((m) => m.id);
    if (!ids.length) return toast('No missed questions saved yet — play a session first.');
    t.done = true; saveProfile();
    return startPractice({ ids, count: ids.length }, 'Review');
  }
  t.done = true;
  saveProfile();
  startPractice({
    section: t.section,
    domains: t.domain ? [t.domain] : [],
    count: t.count,
  }, 'Plan');
}

function renderPlanner() {
  if (!profile.plan || profile.plan.week !== weekKey()) buildPlan();
  const tasks = profile.plan.tasks;
  const done = tasks.filter((t) => t.done).length;
  $('planner-fill').style.width = `${Math.round((done / tasks.length) * 100)}%`;
  $('planner-lbl').textContent = `${done} / ${tasks.length} done`;
  $('planner-note').textContent = Object.keys(profile.domainStats).length
    ? 'Ordered by the domains you miss most.'
    : 'Play a session and the plan will retarget your weak spots.';

  $('planner-tasks').innerHTML = tasks.map((t) => `
    <div class="task">
      <div class="row1">
        <button class="chk" data-plan-check="${t.id}" style="${t.done ? 'background:var(--purple);border-color:var(--purple)' : ''}" aria-label="Mark done">${t.done ? icon('play', 11, 3) : ''}</button>
        <span class="name" style="${t.done ? 'color:var(--slate-4);text-decoration:line-through' : ''}">${esc(t.label)}</span>
        ${t.section === 'review' && !profile.mistakes.length ? '<span class="tag tag-overdue">nothing to review</span>' : ''}
      </div>
      <div class="row2">
        <span class="tag-subject">${t.domain ? esc(t.domain) : (t.section === 'review' ? 'Mistakes' : 'Mixed')}</span>
        <span class="time">${icon('planner', 13, 2)}${t.count} questions</span>
        <span class="spacer"></span>
        <button class="btn-soft" data-plan-start="${t.id}">Start ${icon('play', 12, 2.2)}</button>
      </div>
    </div>`).join('');

  document.querySelectorAll('[data-plan-check]').forEach((b) => {
    b.onclick = () => {
      const t = profile.plan.tasks.find((x) => x.id === b.dataset.planCheck);
      t.done = !t.done;
      saveProfile();
      renderPlanner();
    };
  });
  document.querySelectorAll('[data-plan-start]').forEach((b) => {
    b.onclick = () => startPlanTask(b.dataset.planStart);
  });

  renderExamCountdown('planner-exam-nums', 'planner-exam-date');
  refreshPlannerBadge();
}

$('btn-regen-plan').onclick = () => { buildPlan(); renderPlanner(); toast('Plan rebuilt around your weakest domains.'); };
$('btn-reset-plan').onclick = () => {
  if (!profile.plan) return;
  profile.plan.tasks.forEach((t) => (t.done = false));
  saveProfile();
  renderPlanner();
};
$('btn-switch-date-2').onclick = (e) => { e.preventDefault(); switchTestDate(); };

/* ================= Vocab ================= */
let vocab = null;
let vocabIdx = 0;
let vocabFlipped = false;

async function renderVocab() {
  if (!vocab) {
    try { vocab = await (await fetch('vocab.json')).json(); }
    catch { vocab = []; }
  }
  const remaining = vocab.filter((w) => !profile.vocabKnown.includes(w.word));
  const deck = remaining.length ? remaining : vocab;
  if (vocabIdx >= deck.length) vocabIdx = 0;
  const w = deck[vocabIdx];
  if (!w) return;

  $('vc-word').textContent = w.word;
  $('vc-pos').textContent = w.pos;
  $('vc-def').textContent = w.def;
  $('vc-ex').textContent = `"${w.ex}"`;
  $('vc-progress').textContent = remaining.length
    ? `${vocabIdx + 1} / ${deck.length} left to learn`
    : `All ${vocab.length} marked known`;
  setVocabFace(false);
}

function setVocabFace(flipped) {
  vocabFlipped = flipped;
  $('vocab-card').classList.toggle('flipped', flipped);
  $('vocab-front').classList.toggle('hidden', flipped);
  $('vocab-back').classList.toggle('hidden', !flipped);
}

$('vocab-card').onclick = () => setVocabFace(!vocabFlipped);
$('vc-next').onclick = () => { vocabIdx += 1; renderVocab(); };
$('vc-prev').onclick = () => { vocabIdx = Math.max(0, vocabIdx - 1); renderVocab(); };
$('vc-known').onclick = () => {
  const word = $('vc-word').textContent;
  if (word && !profile.vocabKnown.includes(word)) profile.vocabKnown.push(word);
  saveProfile();
  renderVocab();
  toast(`"${word}" marked as known`);
};
$('vc-reset').onclick = () => { profile.vocabKnown = []; vocabIdx = 0; saveProfile(); renderVocab(); };

/* ================= Analytics ================= */
async function renderAnalytics() {
  $('an2-attempted').textContent = profile.attempted.toLocaleString();
  $('an2-accuracy').textContent = profile.attempted ? `${Math.round((profile.correct / profile.attempted) * 100)}%` : '—';
  $('an2-wins').textContent = profile.wins;
  $('an2-streak').textContent = profile.bestStreak;

  const doms = Object.keys(DOMAIN_SECTION)
    .map((d) => ({ domain: d, ...(profile.domainStats[d] || { correct: 0, total: 0 }) }))
    .filter((d) => d.total > 0)
    .sort((a, b) => (b.correct / b.total) - (a.correct / a.total));
  $('an2-domains').innerHTML = doms.length ? doms.map((d) => {
    const pct = Math.round((d.correct / d.total) * 100);
    return `<div class="bd-row">
      <span class="lbl">${esc(d.domain)}</span>
      <span class="track"><span class="fill" style="width:${pct}%;background:var(--purple)"></span></span>
      <span class="val">${d.correct}/${d.total}</span>
    </div>`;
  }).join('') : '<span class="muted" style="font-size:13px">Play a session to see accuracy by domain.</span>';
  const res = await api('highscores');
  const list = res.scores || [];
  $('hs-list').innerHTML = list.length ? list.map((h2, i) => `
    <div class="result-row ${h2.name === profile.name ? 'me' : ''}">
      <span class="rank">${i + 1}</span>
      <span class="grow">${esc(h2.name)} <span class="detail">· ${SECTION_LABEL[h2.section] || h2.section} · ${h2.date}</span></span>
      <span class="sc tabnum">${h2.score}</span>
    </div>`).join('')
    : '<span class="muted" style="font-size:13px">No scores yet — play a rush or a duel to get on the board.</span>';
}

/* ================= Shared helpers ================= */
function bindSoloButtons() {
  document.querySelectorAll('[data-solo]').forEach((b) => {
    b.onclick = () => startSolo(b.dataset.solo);
  });
}
function bindSoonButtons() {
  document.querySelectorAll('[data-soon]').forEach((b) => {
    b.onclick = () => toast(`${b.dataset.soon} is coming soon — duels and parties are live today.`);
  });
}
function bindNavButtons() {
  document.querySelectorAll('[data-nav]').forEach((b) => {
    b.onclick = (e) => { e.preventDefault(); navTo(b.dataset.nav); };
  });
}
bindNavButtons();

function fmtDur(secs) {
  if (secs < 60) return `${secs}s`;
  const m = Math.floor(secs / 60), s = secs % 60;
  return `${m}m ${s}s`;
}
function timeAgo(ts) {
  const d = Date.now() - ts;
  if (d < 60000) return 'just now';
  if (d < 3600000) return `${Math.floor(d / 60000)}m ago`;
  if (d < 86400000) return `${Math.floor(d / 3600000)}h ago`;
  return `${Math.floor(d / 86400000)}d ago`;
}
function ordinal(n) {
  const s = ['th', 'st', 'nd', 'rd'], v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

/* ================= Name modal ================= */
let nameCallback = null;
function promptName(cb) {
  nameCallback = cb || null;
  $('name-input').value = profile.name || '';
  $('name-overlay').classList.remove('hidden');
  $('name-input').focus();
}
$('btn-save-name').onclick = () => {
  const n = $('name-input').value.trim().slice(0, 16);
  if (!n) return;
  profile.name = n;
  saveProfile();
  $('name-overlay').classList.add('hidden');
  $('sb-username').textContent = n;
  $('greet-name').textContent = n;
  const cb = nameCallback; nameCallback = null;
  if (cb) cb();
};
$('name-input').addEventListener('keydown', (e) => { if (e.key === 'Enter') $('btn-save-name').click(); });

/* ================= Boot ================= */
buildSidebar();
if (profile.plan && profile.plan.week !== weekKey()) buildPlan(); // fresh week, fresh plan
refreshPlannerBadge();
$('sb-username').textContent = profile.name || 'Set nickname';
document.querySelector('.sb-item[data-navitem="Home"]').classList.add('active');
renderHome();
tickPromo();
if (!profile.name) promptName();
