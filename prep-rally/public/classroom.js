/* Lumo — My Classes and Apply As A Tutor.

   Classes are server-side rooms keyed by a 5-letter code, the same shape as a
   party. Students push their own totals up after each session; the teacher sees
   a live roster and can set one assignment at a time. Identity is the browser's
   playerKey, so this is a classroom tool, not an authentication system. */

let currentClass = null;
let activeAssignment = null;   // {code, id} while an assignment set is being played

/* ================= My Classes ================= */
async function renderClasses() {
  $('class-detail').classList.add('hidden');
  $('class-list-wrap').classList.remove('hidden');
  const res = await api('class_list', { playerKey: profile.playerKey });
  const classes = res.classes || [];
  profile.classes = classes.map((c) => ({ code: c.code, name: c.name, isTeacher: c.isTeacher }));
  saveProfile();

  $('class-list').innerHTML = classes.length ? classes.map((c) => `
    <button class="class-card" data-class="${esc(c.code)}">
      <span class="cc-top">
        <span class="cc-name">${esc(c.name)}</span>
        <span class="cc-role ${c.isTeacher ? 'teacher' : ''}">${c.isTeacher ? 'Teacher' : 'Student'}</span>
      </span>
      <span class="cc-meta">${c.isTeacher ? `${c.size} student${c.size === 1 ? '' : 's'}` : `Taught by ${esc(c.teacherName || '—')}`}</span>
      <span class="cc-foot">
        <span class="cc-code">${esc(c.code)}</span>
        ${c.hasAssignment ? '<span class="cc-badge">Assignment set</span>' : ''}
      </span>
    </button>`).join('')
    : `<div class="empty-note">You are not in a class yet. Join one with a code, or start your own below.</div>`;

  $('class-list').querySelectorAll('[data-class]').forEach((b) => {
    b.onclick = () => openClass(b.dataset.class);
  });
}
RENDERERS['v-classes'] = renderClasses;

async function openClass(code) {
  const res = await api('class_get', { playerKey: profile.playerKey, code });
  if (res.error) return toast(res.error);
  currentClass = res.class;
  paintClass();
  $('class-list-wrap').classList.add('hidden');
  $('class-detail').classList.remove('hidden');
}

function paintClass() {
  const c = currentClass;
  $('cd-name').textContent = c.name;
  $('cd-code').textContent = c.code;
  $('cd-meta').textContent = c.isTeacher
    ? `You teach this class · ${c.students.length} student${c.students.length === 1 ? '' : 's'}`
    : `Taught by ${c.teacherName || '—'} · ${c.students.length} student${c.students.length === 1 ? '' : 's'}`;

  const a = c.assignment;
  $('cd-assign-title').textContent = a ? a.title : 'No assignment set';
  $('cd-assign-sub').textContent = a
    ? `${a.settings.count} questions · ${a.settings.domains.length ? a.settings.domains.join(', ') : SECTION_LABEL[a.settings.section] || 'Mixed'}`
    : (c.isTeacher ? 'Set one below and everyone will see it.' : 'Your teacher has not set one yet.');
  $('cd-assign-start').classList.toggle('hidden', !a);

  $('cd-teacher-tools').classList.toggle('hidden', !c.isTeacher);
  if (c.isTeacher) fillAssignDomains();
  $('cd-clear-assign').classList.toggle('hidden', !a);
  $('cd-leave').textContent = c.isTeacher ? 'Close this class' : 'Leave this class';

  $('cd-roster-count').textContent = `${c.students.length} joined`;
  $('cd-roster').innerHTML = c.students.length ? `
    <div class="roster-row head">
      <span class="rn">Student</span><span class="rv">Answered</span>
      <span class="rv">Accuracy</span><span class="rv">Points</span><span class="rv">Assignment</span>
    </div>
    ${c.students.map((st) => `
      <div class="roster-row ${st.isMe ? 'me' : ''}">
        <span class="rn">${esc(st.name || '—')}${st.isMe ? ' <span class="you-tag">you</span>' : ''}</span>
        <span class="rv tabnum">${st.attempted}</span>
        <span class="rv tabnum">${st.accuracy === null ? '—' : `${st.accuracy}%`}</span>
        <span class="rv tabnum">${st.points.toLocaleString()}</span>
        <span class="rv">${c.assignment ? (st.assignmentDone
          ? '<span class="tick done">Done</span>' : '<span class="tick">Not yet</span>') : '—'}</span>
      </div>`).join('')}`
    : '<div class="empty-note">No students yet. Share the class code above.</div>';
}

// Teacher assignment controls
function fillAssignDomains() {
  const sel = $('cd-assign-domain');
  if (sel.options.length) return;
  sel.innerHTML = `<option value="">Mixed — all domains</option>`
    + Object.keys(DOMAIN_SECTION).map((d) => `<option value="${esc(d)}">${esc(d)}</option>`).join('');
}

$('cd-assign-save').onclick = async () => {
  fillAssignDomains();
  const domain = $('cd-assign-domain').value;
  const count = Number($('cd-assign-count').value);
  const title = $('cd-assign-name').value.trim() || (domain ? `${domain} set` : 'Mixed practice');
  const settings = domain
    ? { section: DOMAIN_SECTION[domain], domains: [domain], count }
    : { section: 'mixed', count };
  const res = await api('class_assign', {
    playerKey: profile.playerKey, code: currentClass.code,
    assignment: { title, settings },
  });
  if (res.error) return toast(res.error);
  currentClass = res.class;
  paintClass();
  $('cd-assign-name').value = '';
  toast('Assignment set for the class.');
};

$('cd-clear-assign').onclick = async () => {
  const res = await api('class_assign', {
    playerKey: profile.playerKey, code: currentClass.code, assignment: null,
  });
  if (res.error) return toast(res.error);
  currentClass = res.class;
  paintClass();
  toast('Assignment cleared.');
};

$('cd-assign-start').onclick = () => {
  const a = currentClass && currentClass.assignment;
  if (!a) return;
  activeAssignment = { code: currentClass.code, id: a.id };
  startPractice({ ...a.settings }, 'Assignment');
};

$('cd-copy').onclick = async () => {
  try {
    await navigator.clipboard.writeText(currentClass.code);
    toast(`Class code ${currentClass.code} copied.`);
  } catch { toast(`Class code: ${currentClass.code}`); }
};

$('class-back').onclick = () => renderClasses();

$('cd-leave').onclick = async () => {
  const teacher = currentClass.isTeacher;
  const msg = teacher
    ? `Close "${currentClass.name}"? Students will lose access and the roster is deleted. This cannot be undone.`
    : `Leave "${currentClass.name}"? Your progress stays on this device.`;
  if (!confirm(msg)) return;
  await api('class_leave', { playerKey: profile.playerKey, code: currentClass.code });
  toast(teacher ? 'Class closed.' : 'You left the class.');
  renderClasses();
};

$('btn-class-join').onclick = async () => {
  const code = $('class-join-code').value.trim().toUpperCase();
  if (code.length !== 5) return toast('A class code is 5 letters.');
  if (!profile.name) return promptName(() => $('btn-class-join').click());
  const res = await api('class_join', { playerKey: profile.playerKey, name: profile.name, code });
  if (res.error) return toast(res.error);
  $('class-join-code').value = '';
  currentClass = res.class;
  reportToClasses();
  paintClass();
  $('class-list-wrap').classList.add('hidden');
  $('class-detail').classList.remove('hidden');
  toast(`Joined ${res.class.name}.`);
};

$('btn-class-create').onclick = async () => {
  const className = $('class-new-name').value.trim();
  if (className.length < 2) return toast('Give the class a name first.');
  if (!profile.name) return promptName(() => $('btn-class-create').click());
  const res = await api('class_create', {
    playerKey: profile.playerKey, name: profile.name, className,
  });
  if (res.error) return toast(res.error);
  $('class-new-name').value = '';
  currentClass = res.class;
  fillAssignDomains();
  paintClass();
  $('class-list-wrap').classList.add('hidden');
  $('class-detail').classList.remove('hidden');
  toast(`Class created — code ${res.class.code}.`);
};

/* Students push their own totals after a session so the roster stays live. */
async function reportToClasses(finishedAssignment) {
  if (!profile.classes.length) return;
  const weak = weakestDomains(1)[0];
  const stats = {
    attempted: profile.attempted, correct: profile.correct, points: profile.points,
    weakest: weak && weak.total ? weak.domain : '',
    assignmentDone: finishedAssignment || '',
  };
  await Promise.all(profile.classes.filter((c) => !c.isTeacher).map((c) =>
    api('class_report', { playerKey: profile.playerKey, name: profile.name, code: c.code, stats })
      .catch(() => {})));
}

/* ================= Apply As A Tutor ================= */
const TUTOR_SUBJECTS = ['Reading & Writing', 'Math', 'Desmos technique', 'Test-day strategy'];
const ELIGIBILITY = [
  { id: 'answered', label: 'Answer 50 questions', get: () => profile.attempted, need: 50 },
  { id: 'accuracy', label: 'Reach 80% accuracy', need: 80,
    get: () => (profile.attempted ? Math.round((profile.correct / profile.attempted) * 100) : 0) },
  { id: 'lessons', label: 'Finish 3 masterclass lessons', get: () => profile.lessonsDone.length, need: 3 },
];

function eligibilityState() {
  const rows = ELIGIBILITY.map((e) => {
    const have = e.get();
    return { ...e, have, ok: have >= e.need };
  });
  return { rows, eligible: rows.every((r) => r.ok) };
}

async function renderTutor() {
  const { rows, eligible } = eligibilityState();
  const res = await api('tutor_status', { playerKey: profile.playerKey });
  const app = res.application;

  $('tutor-status-card').classList.toggle('hidden', !app);
  $('tutor-form-wrap').classList.toggle('hidden', !!app);

  if (app) {
    $('ts-title').textContent = 'Your application is in review';
    $('ts-sub').textContent = `Submitted ${timeAgo(app.submitted)} as ${app.name}. `
      + 'Applications are reviewed by hand, so there is nothing more to do right now.';
    $('ts-grid').innerHTML = [
      ['Email', app.email], ['Grade', app.grade || '—'],
      ['SAT score', app.score || 'Not given'], ['Availability', app.availability || '—'],
      ['Subjects', app.subjects.join(', ')],
      ['Record at apply time', `${app.stats.attempted} answered · ${app.stats.accuracy}%`],
    ].map(([k, v]) => `<div class="ts-cell"><span class="k">${esc(k)}</span><span class="v">${esc(v)}</span></div>`).join('');
    return;
  }

  $('elig-list').innerHTML = rows.map((r) => `
    <div class="elig ${r.ok ? 'ok' : ''}">
      <span class="dot">${r.ok ? `<svg class="ic" style="width:12px;height:12px;stroke-width:3.2" viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>` : ''}</span>
      <span class="lbl">${esc(r.label)}</span>
      <span class="val tabnum">${r.have}${r.id === 'accuracy' ? '%' : ''} / ${r.need}${r.id === 'accuracy' ? '%' : ''}</span>
    </div>`).join('');
  $('elig-note').textContent = eligible
    ? 'You meet the bar. Fill in the form below and we will take a look.'
    : 'You can still apply, but meeting these first makes a much stronger application.';

  if (!$('tf-subjects').childElementCount) {
    $('tf-subjects').innerHTML = TUTOR_SUBJECTS.map((sub) => `
      <label class="chip-check"><input type="checkbox" value="${esc(sub)}"><span>${esc(sub)}</span></label>`).join('');
  }
  if (!$('tf-name').value) $('tf-name').value = profile.name || '';
}
RENDERERS['v-tutor'] = renderTutor;

$('tf-about').addEventListener('input', () => {
  $('tf-about-count').textContent = $('tf-about').value.length;
});

$('tutor-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const err = $('tf-error');
  err.textContent = '';
  const subjects = [...$('tf-subjects').querySelectorAll('input:checked')].map((i) => i.value);
  const about = $('tf-about').value.trim();

  if ($('tf-name').value.trim().length < 2) { err.textContent = 'Enter your full name.'; return; }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test($('tf-email').value.trim())) {
    err.textContent = 'Enter a valid email address.'; return;
  }
  if (!subjects.length) { err.textContent = 'Pick at least one subject you can tutor.'; return; }
  if (about.length < 40) {
    err.textContent = `Tell us a bit more — ${40 - about.length} more character${40 - about.length === 1 ? '' : 's'}.`;
    return;
  }

  const { rows } = eligibilityState();
  const acc = rows.find((r) => r.id === 'accuracy');
  const res = await api('tutor_apply', {
    playerKey: profile.playerKey,
    applicantName: $('tf-name').value.trim(),
    email: $('tf-email').value.trim(),
    grade: $('tf-grade').value,
    score: $('tf-score').value.trim(),
    availability: $('tf-avail').value,
    subjects, about,
    attempted: profile.attempted, accuracy: acc ? acc.have : 0,
  });
  if (res.error) { err.textContent = res.error; return; }
  toast('Application submitted.');
  renderTutor();
});

$('btn-tutor-withdraw').onclick = async () => {
  if (!confirm('Withdraw your tutor application? You can apply again later.')) return;
  await api('tutor_withdraw', { playerKey: profile.playerKey });
  toast('Application withdrawn.');
  renderTutor();
};
