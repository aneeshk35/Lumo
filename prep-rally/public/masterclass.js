/* Lumo — Masterclass. Short written lessons per SAT domain, each ending in a
   worked example you actually answer, then a one-click drill into the bank.
   Lesson text lives in public/lessons.json. */

let LESSONS = null;
let mcSection = 'rw';
let currentLesson = null;

const MC_META = {
  rw: {
    title: 'Reading & Writing Masterclass',
    sub: 'The four Reading and Writing domains, one method each. Every lesson ends with a worked example and a drill.',
    icon: 'M4 5h6a2 2 0 0 1 2 2v13a2 2 0 0 0-2-2H4zM20 5h-6a2 2 0 0 0-2 2v13a2 2 0 0 1 2-2h6z',
  },
  math: {
    title: 'Math & Desmos Masterclass',
    sub: 'The four Math domains plus the four Desmos moves worth the most points on test day.',
    icon: 'M6 5h12l-7 7 7 7H6',
  },
};

// Desmos lessons sort last in the Math masterclass; otherwise keep bank order.
const MC_DOMAIN_ORDER = [
  'Information and Ideas', 'Craft and Structure', 'Expression of Ideas',
  'Standard English Conventions', 'Algebra', 'Advanced Math',
  'Problem-Solving and Data Analysis', 'Geometry and Trigonometry', 'Desmos',
];

async function loadLessons() {
  if (LESSONS) return LESSONS;
  const res = await fetch('lessons.json');
  LESSONS = await res.json();
  return LESSONS;
}

function lessonDone(id) {
  return profile.lessonsDone.includes(id);
}

function sectionLessons(section) {
  return (LESSONS || []).filter((l) => l.section === section);
}

async function renderMasterclass(item) {
  mcSection = (item && item.mcSection) || mcSection;
  const meta = MC_META[mcSection];
  $('mc-title').textContent = meta.title;
  $('mc-sub').textContent = meta.sub;
  $('mc-icon').setAttribute('d', meta.icon);

  $('mc-groups').innerHTML = '<div class="mc-loading">Loading lessons…</div>';
  await loadLessons();

  const mine = sectionLessons(mcSection);
  const done = mine.filter((l) => lessonDone(l.id)).length;
  const pct = mine.length ? Math.round((done / mine.length) * 100) : 0;
  $('mc-done-count').textContent = done;
  $('mc-total-count').textContent = mine.length;
  $('mc-ring-num').textContent = `${pct}%`;
  $('mc-ring').style.setProperty('--pct', `${pct * 3.6}deg`);

  const groups = [];
  for (const domain of MC_DOMAIN_ORDER) {
    const items = mine.filter((l) => l.domain === domain);
    if (items.length) groups.push({ domain, items });
  }

  $('mc-groups').innerHTML = groups.map((g) => {
    const gDone = g.items.filter((l) => lessonDone(l.id)).length;
    return `<div class="mc-group">
      <div class="mc-group-head">
        <span class="mc-domain">${esc(g.domain)}</span>
        <span class="mc-group-count">${gDone}/${g.items.length}</span>
      </div>
      <div class="mc-cards">
        ${g.items.map((l) => `
          <button class="mc-card ${lessonDone(l.id) ? 'done' : ''}" data-lesson="${esc(l.id)}">
            <span class="mc-card-top">
              <span class="mc-skill">${esc(l.skill)}</span>
              <span class="mc-check" aria-hidden="true">
                <svg class="ic" style="width:13px;height:13px;stroke-width:3" viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>
              </span>
            </span>
            <span class="mc-card-title">${esc(l.title)}</span>
            <span class="mc-card-sum">${esc(l.summary)}</span>
            <span class="mc-card-foot">
              <span class="mc-mins">${l.minutes} min read</span>
              <span class="mc-go">${lessonDone(l.id) ? 'Review' : 'Start'} &rsaquo;</span>
            </span>
          </button>`).join('')}
      </div>
    </div>`;
  }).join('');

  $('mc-groups').querySelectorAll('[data-lesson]').forEach((b) => {
    b.onclick = () => openLesson(b.dataset.lesson);
  });
}
RENDERERS['v-masterclass'] = renderMasterclass;

/* ================= Lesson reader ================= */
function lessonBlockHtml(b, lessonId) {
  if (b.type === 'concept') {
    return `<div class="lb lb-concept">
      <span class="lb-h">${esc(b.heading || 'The idea')}</span>
      <p>${esc(b.body)}</p>
    </div>`;
  }
  if (b.type === 'steps' || b.type === 'desmos') {
    const desmos = b.type === 'desmos';
    return `<div class="lb ${desmos ? 'lb-desmos' : 'lb-steps'}">
      <span class="lb-h">${esc(b.heading || (desmos ? 'Type this in' : 'The method'))}</span>
      <ol class="lb-list">${b.items.map((it) => `<li>${esc(it)}</li>`).join('')}</ol>
      ${desmos ? '<button class="btn-outline lb-calc" data-open-calc="1">Open the calculator and try it</button>' : ''}
    </div>`;
  }
  if (b.type === 'tip') {
    return `<div class="lb lb-tip"><span class="lb-tag">Tip</span><p>${esc(b.body)}</p></div>`;
  }
  if (b.type === 'trap') {
    return `<div class="lb lb-trap"><span class="lb-tag">Common trap</span><p>${esc(b.body)}</p></div>`;
  }
  if (b.type === 'example') {
    return `<div class="lb lb-example" id="lb-ex">
      <span class="lb-h">Worked example</span>
      ${b.passage ? `<div class="lb-passage">${esc(b.passage).replace(/\n/g, '<br>')}</div>` : ''}
      <p class="lb-q">${esc(b.question)}</p>
      <div class="lb-choices" id="lb-choices">
        ${b.choices.map((c, i) => `
          <button class="lb-choice" data-ex-choice="${i}">
            <span class="ltr">${LETTERS[i]}</span><span class="txt">${esc(c)}</span>
          </button>`).join('')}
      </div>
      <div class="lb-walk hidden" id="lb-walk">
        <span class="lb-walk-h" id="lb-walk-h"></span>
        <p>${esc(b.walkthrough)}</p>
      </div>
    </div>`;
  }
  return '';
}

async function openLesson(id) {
  await loadLessons();
  const lesson = LESSONS.find((l) => l.id === id);
  if (!lesson) return;
  currentLesson = lesson;

  $('lesson-kicker').textContent = `${lesson.domain} · ${lesson.skill}`;
  $('lesson-title').textContent = lesson.title;
  $('lesson-summary').textContent = lesson.summary;
  $('lesson-back-lbl').textContent = MC_META[lesson.section].title.replace(' Masterclass', '');
  $('lesson-body').innerHTML = lesson.blocks.map((b) => lessonBlockHtml(b, lesson.id)).join('');

  const ex = lesson.blocks.find((b) => b.type === 'example');
  if (ex) {
    $('lesson-body').querySelectorAll('[data-ex-choice]').forEach((btn) => {
      btn.onclick = () => {
        const picked = Number(btn.dataset.exChoice);
        const right = picked === ex.answer;
        $('lesson-body').querySelectorAll('[data-ex-choice]').forEach((b2) => {
          const i = Number(b2.dataset.exChoice);
          b2.disabled = true;
          if (i === ex.answer) b2.classList.add('correct');
          else if (i === picked) b2.classList.add('wrong');
        });
        $('lb-walk-h').textContent = right
          ? 'Correct — here is why'
          : `Not quite. The answer is ${LETTERS[ex.answer]}`;
        $('lb-walk').classList.remove('hidden');
        $('lb-walk').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      };
    });
  }
  const calcBtn = $('lesson-body').querySelector('[data-open-calc]');
  if (calcBtn) calcBtn.onclick = () => openCalc(true);

  syncLessonFoot();
  switchView('v-lesson');
}

function syncLessonFoot() {
  const done = lessonDone(currentLesson.id);
  $('lesson-complete').textContent = done ? 'Completed ✓' : 'Mark complete';
  $('lesson-complete').classList.toggle('btn-primary', !done);
  $('lesson-complete').classList.toggle('btn-done', done);
  const rest = sectionLessons(currentLesson.section);
  const idx = rest.findIndex((l) => l.id === currentLesson.id);
  $('lesson-next').classList.toggle('hidden', idx < 0 || idx >= rest.length - 1);
}

$('lesson-back').onclick = () => {
  navTo(currentLesson && currentLesson.section === 'math' ? 'Math & Desmos' : 'Reading & Writing');
};
$('lesson-complete').onclick = () => {
  if (!currentLesson) return;
  const i = profile.lessonsDone.indexOf(currentLesson.id);
  if (i >= 0) profile.lessonsDone.splice(i, 1);
  else profile.lessonsDone.push(currentLesson.id);
  saveProfile();
  syncLessonFoot();
  toast(lessonDone(currentLesson.id) ? 'Lesson marked complete.' : 'Marked as not done.');
};
$('lesson-drill').onclick = () => {
  if (!currentLesson) return;
  startPractice({ ...currentLesson.drill }, 'Lesson');
};
$('lesson-next').onclick = () => {
  const rest = sectionLessons(currentLesson.section);
  const idx = rest.findIndex((l) => l.id === currentLesson.id);
  if (idx >= 0 && idx < rest.length - 1) openLesson(rest[idx + 1].id);
};
