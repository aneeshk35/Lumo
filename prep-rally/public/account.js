/* Lumo — accounts. A guest's progress lives in this browser only. Signing up
   uploads it to an account; after that every saveProfile() also saves to the
   server, so progress follows the player to any device.

   Sync is last-good-write: each save carries the revision it was based on, and
   the server refuses a save from a stale copy (a tab left open on another
   device) and hands back the newer profile instead of letting it be
   overwritten. */

const ACCOUNT_KEY = 'lumo-account';
let account = loadAccount();      // {token, username, rev, dirty} or null
let accountsDurable = true;       // false when the server would lose accounts on restart
let acctTab = 'signup';
let nameCallback = null;
let saveTimer = null;
let saveInFlight = false;
let changedDuringSave = false;
let retryTimer = null;

function loadAccount() {
  try {
    const a = JSON.parse(localStorage.getItem(ACCOUNT_KEY) || 'null');
    return a && a.token ? a : null;
  } catch (e) { return null; }
}
function storeAccount() {
  if (account) localStorage.setItem(ACCOUNT_KEY, JSON.stringify(account));
  else localStorage.removeItem(ACCOUNT_KEY);
}

// Account calls never throw: a network failure comes back as {offline: true}.
async function accountCall(action, body) {
  try {
    const res = await fetch(`${API_BASE}/api/${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    return await res.json();
  } catch (e) {
    return { offline: true, error: 'Can’t reach the server. Check your connection and try again.' };
  }
}

/* ---------- sync ---------- */
function setSyncState(state) {
  const text = { saved: 'All progress saved', saving: 'Saving…',
    offline: 'Offline — your progress is kept here and saves when you reconnect' }[state];
  if ($('acct-sync')) $('acct-sync').textContent = text;
  if ($('acct-sync-dot')) $('acct-sync-dot').dataset.state = state;
}

// Called by saveProfile(). Batches bursts of changes into one request.
function queueCloudSave() {
  if (!account) return;
  account.dirty = true;
  storeAccount();
  if (saveInFlight) changedDuringSave = true;
  setSyncState('saving');
  clearTimeout(saveTimer);
  saveTimer = setTimeout(pushProfile, 1200);
}

async function pushProfile() {
  if (!account) return;
  if (saveInFlight) { changedDuringSave = true; return; }
  saveInFlight = true;
  changedDuringSave = false;
  clearTimeout(retryTimer);
  const res = await accountCall('save', { token: account.token, profile, rev: account.rev });
  saveInFlight = false;
  if (!account) return;
  if (res.ok) {
    account.rev = res.rev;
    account.dirty = changedDuringSave;
    storeAccount();
    if (changedDuringSave) return pushProfile();
    setSyncState('saved');
  } else if (res.conflict) {
    adoptProfile(res.profile, res.rev);
    toast('Loaded newer progress saved from another device.');
  } else if (res.signedOut) {
    signedOutElsewhere();
  } else {
    setSyncState('offline');
    retryTimer = setTimeout(pushProfile, 20000);
  }
}

// Take the account's copy as the truth for this device.
function adoptProfile(remote, rev) {
  replaceProfile(remote);
  account.rev = rev;
  account.dirty = false;
  storeAccount();
  setSyncState('saved');
  updateIdentityUI();
  refreshPlannerBadge();
  // Redraw the screen with the new numbers, but never yank someone out of a game.
  const playing = ['queue', 'lobby', 'question', 'reveal'].includes(game.phase);
  if (!playing && !$('v-results').classList.contains('active')) {
    const here = findNav(activeNav);
    const view = here && here.item.view;
    navTo(view && view.startsWith('v-') ? activeNav : 'Home');
  }
}

// Pull the account's latest copy (on load, and when the tab comes back into view).
async function pullProfile() {
  if (!account || saveInFlight) return;
  const res = await accountCall('me', { token: account.token });
  if (!account) return;
  if (res.signedOut) return signedOutElsewhere();
  if (res.offline || res.error) { if (account.dirty) setSyncState('offline'); return; }
  if (account.dirty && res.rev === account.rev) return pushProfile();   // our unsent changes win
  if (res.rev !== account.rev) adoptProfile(res.profile, res.rev);
  else setSyncState('saved');
}

function signedOutElsewhere() {
  account = null;
  storeAccount();
  updateIdentityUI();
  toast('You’re signed out. Sign in again to keep saving progress to your account.');
}

// Last chance to save when the page is closed or hidden. keepalive requests
// are capped at 64 KB; anything bigger is still marked dirty and goes on next load.
function flushOnLeave() {
  if (!account || !account.dirty) return;
  const body = JSON.stringify({ token: account.token, profile, rev: account.rev });
  if (body.length > 60000) return;
  try {
    fetch(`${API_BASE}/api/save`, {
      method: 'POST', keepalive: true, headers: { 'Content-Type': 'application/json' }, body,
    });
  } catch (e) { /* the dirty flag covers it */ }
}
window.addEventListener('pagehide', flushOnLeave);
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') flushOnLeave();
  else pullProfile();
});

/* ---------- the modal ---------- */
// Kept under its old name: every "you need a name first" path calls this.
function promptName(cb) {
  nameCallback = cb || null;
  showError('');
  $('acct-guest').classList.toggle('hidden', !!account);
  $('acct-signed').classList.toggle('hidden', !account);
  // First visit has to pick something; after that the modal can be dismissed.
  $('btn-acct-close').classList.toggle('hidden', !profile.name);
  if (account) {
    $('acct-title').textContent = 'Your account';
    $('acct-desc').textContent = `Signed in as @${account.username}. Progress saves automatically.`;
    $('acct-nick').value = profile.name || '';
    setSyncState(account.dirty ? 'saving' : 'saved');
  } else {
    $('acct-title').textContent = profile.name ? 'Save your progress' : 'Welcome to Lumo';
    $('acct-desc').textContent = 'Make an account and your progress, ratings, and mistake list follow you to any device.';
    $('name-input').value = profile.name || '';
    setAcctTab(acctTab);
  }
  $('name-overlay').classList.remove('hidden');
  const first = account ? $('acct-nick') : ($('acct-username').closest('.hidden') ? $('name-input') : $('acct-username'));
  first.focus();
}

function closeAccountModal() {
  $('name-overlay').classList.add('hidden');
  nameCallback = null;
}

function setAcctTab(tab) {
  acctTab = tab;
  document.querySelectorAll('[data-acct-tab]').forEach((b) => {
    const on = b.dataset.acctTab === tab;
    b.classList.toggle('active', on);
    b.setAttribute('aria-selected', String(on));
  });
  const isGuest = tab === 'guest';
  $('acct-user-row').classList.toggle('hidden', isGuest);
  $('acct-pass-row').classList.toggle('hidden', isGuest);
  $('acct-nick-row').classList.toggle('hidden', tab === 'login');
  $('acct-password').setAttribute('autocomplete', tab === 'login' ? 'current-password' : 'new-password');
  $('btn-save-name').textContent = { signup: 'Create account', login: 'Sign in', guest: 'Play as guest' }[tab];

  const hasProgress = (profile.attempted || 0) > 0;
  let note = '';
  if (tab === 'signup') {
    note = hasProgress ? 'Everything you’ve done on this device comes with you.'
      : 'Passwords need at least 8 characters. There’s no email, so don’t forget it.';
  } else if (tab === 'login') {
    note = hasProgress ? 'Signing in replaces this device’s guest progress with your account’s.' : '';
  } else {
    note = 'Progress stays in this browser only. You can make an account any time.';
  }
  if (tab !== 'guest' && !accountsDurable) {
    note = 'Heads up: account storage isn’t set up on this server yet, so accounts are wiped when it restarts.';
  }
  $('acct-note').textContent = note;
  $('acct-note').classList.toggle('warn', tab !== 'guest' && !accountsDurable);
  showError('');
}

function showError(msg) {
  $('acct-error').textContent = msg;
  $('acct-error').classList.toggle('hidden', !msg);
}

function finishIdentity(message) {
  updateIdentityUI();
  $('name-overlay').classList.add('hidden');
  if (message) toast(message);
  const cb = nameCallback; nameCallback = null;
  if (cb) cb();
}

async function submitAccountForm() {
  const btn = $('btn-save-name');
  if (btn.disabled) return;
  const nick = $('name-input').value.trim().slice(0, 16);
  if (acctTab === 'guest') {
    if (!nick) return showError('Pick a nickname first.');
    profile.name = nick;
    saveProfile();
    return finishIdentity();
  }
  const username = $('acct-username').value.trim();
  const password = $('acct-password').value;
  if (!username) return showError('Enter a username.');
  if (!password) return showError('Enter a password.');

  btn.disabled = true;
  const label = btn.textContent;
  btn.textContent = acctTab === 'signup' ? 'Creating…' : 'Signing in…';
  let res;
  if (acctTab === 'signup') {
    if (!/^[A-Za-z0-9_.-]{3,20}$/.test(username)) {
      btn.disabled = false; btn.textContent = label;
      return showError('Usernames are 3–20 letters, numbers, dots, dashes, or underscores.');
    }
    if (password.length < 8) {
      btn.disabled = false; btn.textContent = label;
      return showError('Use a password of at least 8 characters.');
    }
    profile.name = nick || profile.name || username.slice(0, 16);
    localStorage.setItem('lumo-profile', JSON.stringify(profile));
    res = await accountCall('signup', { username, password, profile });
  } else {
    res = await accountCall('login', { username, password });
  }
  btn.disabled = false;
  btn.textContent = label;
  if (!res.token) return showError(res.error || 'Something went wrong. Try again.');

  $('acct-password').value = '';
  account = { token: res.token, username: res.username, rev: res.rev, dirty: false };
  storeAccount();
  if (acctTab === 'login') {
    adoptProfile(res.profile, res.rev);
    if (!profile.name) { profile.name = res.username.slice(0, 16); saveProfile(); }
    finishIdentity(`Signed in as ${res.username}. Welcome back!`);
  } else {
    setSyncState('saved');
    finishIdentity('Account created — your progress now saves to it.');
  }
}

async function signOut() {
  if (!account) return;
  // Get any last changes in before the session goes away.
  if (account.dirty) { clearTimeout(saveTimer); await pushProfile(); }
  await accountCall('logout', { token: account.token });
  account = null;
  storeAccount();
  // Leave nothing of this player behind on a shared computer.
  localStorage.removeItem('lumo-profile');
  location.reload();
}

$('acct-form').addEventListener('submit', (e) => { e.preventDefault(); submitAccountForm(); });
$('acct-nick-form').addEventListener('submit', (e) => {
  e.preventDefault();
  const n = $('acct-nick').value.trim().slice(0, 16);
  if (!n) return;
  profile.name = n;
  saveProfile();
  finishIdentity('Nickname saved.');
});
document.querySelectorAll('[data-acct-tab]').forEach((b) => {
  b.onclick = () => { setAcctTab(b.dataset.acctTab); (b.dataset.acctTab === 'guest' ? $('name-input') : $('acct-username')).focus(); };
});
$('btn-signout').onclick = signOut;
$('btn-acct-close').onclick = closeAccountModal;
$('name-overlay').addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && profile.name) closeAccountModal();
});

/* ---------- boot ---------- */
updateIdentityUI();
if (!profile.name && !account) promptName();
accountCall('config', {}).then((cfg) => {
  if (cfg && cfg.accountsDurable === false) {
    accountsDurable = false;
    if (!$('name-overlay').classList.contains('hidden') && !account) setAcctTab(acctTab);
  }
});
if (account) pullProfile();
