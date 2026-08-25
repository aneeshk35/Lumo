/* Lumo — friends, presence, and 2v2 queueing.

   Presence is a heartbeat: this browser tells the server its nickname and what
   it is doing, and gets back the status of the friend codes it asked about,
   plus any duel invitations waiting for it. Friend codes are the only handle —
   there are no accounts, so a code identifies a browser, not a person. */

const PRESENCE_EVERY = 12000;   // ms between heartbeats
let presenceTimer = null;
let friendRows = [];
let pendingInvite = null;

function currentActivity() {
  if (game.phase === 'question' || game.phase === 'reveal') return 'In a game';
  if (game.phase === 'queue') return 'In the queue';
  if (game.phase === 'lobby') return 'In a lobby';
  const view = document.querySelector('.view.active');
  const label = {
    'v-vocab': 'Studying vocab', 'v-bank': 'Browsing the bank',
    'v-masterclass': 'In a masterclass', 'v-lesson': 'Reading a lesson',
    'v-planner': 'On the study plan', 'v-mistakes': 'Reviewing mistakes',
    'v-analytics': 'Checking analytics', 'v-coach': 'Asking Lumo',
    'v-classes': 'In a classroom',
  }[view && view.id];
  return label || 'Online';
}

async function pingPresence() {
  try {
    const res = await api('presence', {
      playerKey: profile.playerKey,
      name: profile.name || 'Player',
      elo: profile.elo,
      activity: currentActivity(),
      friends: profile.friends.map((f) => f.code),
    });
    if (res.code && res.code !== profile.friendCode) {
      profile.friendCode = res.code;
      saveProfile();
    }
    friendRows = res.friends || [];
    if ($('my-friend-code')) $('my-friend-code').textContent = profile.friendCode || '—';
    if (document.querySelector('#v-play.active')) paintFriends();
    if (res.invites && res.invites.length) showInvite(res.invites[res.invites.length - 1]);
  } catch { /* offline is fine; the next tick retries */ }
}

function startPresence() {
  if (presenceTimer) return;
  pingPresence();
  presenceTimer = setInterval(pingPresence, PRESENCE_EVERY);
}

function paintFriends() {
  const list = $('friends-list');
  if (!list) return;
  if (!profile.friends.length) {
    list.innerHTML = `<div class="empty-note small">No friends yet. Share your code above, or add someone with theirs — you will see when they are online and can challenge them straight to a duel.</div>`;
    return;
  }
  const byCode = Object.fromEntries(friendRows.map((f) => [f.code, f]));
  list.innerHTML = profile.friends.map((f) => {
    const live = byCode[f.code] || {};
    const name = live.name || f.name || f.code;
    const online = !!live.online;
    const status = live.unknown ? 'Never seen online'
      : online ? `${live.activity || 'Online'}${live.elo ? ` · ${live.elo} ELO` : ''}`
      : live.lastSeen ? `Last online ${timeAgo(live.lastSeen)}` : 'Offline';
    return `<div class="friend">
      <span class="ava"><span class="circ"></span><span class="st" style="background:${online ? 'var(--green)' : 'var(--slate-3)'}"></span></span>
      <span class="body"><span class="n">${esc(name)}</span><span class="s">${esc(status)}</span></span>
      <button class="friend-btn ${online ? 'solid' : 'soft'}" data-challenge="${esc(f.code)}"
        ${online ? '' : 'disabled'}>${online ? 'Challenge' : 'Offline'}</button>
      <button class="friend-x" data-unfriend="${esc(f.code)}" title="Remove friend" aria-label="Remove ${esc(name)}">&times;</button>
    </div>`;
  }).join('');

  list.querySelectorAll('[data-challenge]').forEach((b) => {
    b.onclick = () => challengeFriend(b.dataset.challenge);
  });
  list.querySelectorAll('[data-unfriend]').forEach((b) => {
    b.onclick = () => {
      profile.friends = profile.friends.filter((f) => f.code !== b.dataset.unfriend);
      saveProfile();
      paintFriends();
      toast('Friend removed.');
    };
  });
}

async function addFriend() {
  const input = $('friend-code-input');
  const code = input.value.trim().toUpperCase();
  if (code.length !== 6) return toast('A friend code is 6 characters.');
  if (code === profile.friendCode) return toast('That is your own code.');
  if (profile.friends.some((f) => f.code === code)) return toast('They are already on your list.');
  const res = await api('friend_lookup', { code });
  if (!res.found) return toast('No player with that code has been online yet.');
  profile.friends.push({ code, name: res.name || code });
  saveProfile();
  input.value = '';
  paintFriends();
  pingPresence();
  toast(`Added ${res.name || code}.`);
}

/* Challenge: open a private party, then push an invite to the friend. */
async function challengeFriend(code) {
  if (!profile.name) return promptName(() => challengeFriend(code));
  const res = await api('create', {
    name: profile.name,
    settings: { section: duelSection, count: 10 },
  });
  if (res.error) return toast(res.error);
  ME.code = res.code;
  ME.playerId = res.playerId;
  await connectEvents();
  const sent = await api('invite', {
    playerKey: profile.playerKey, toCode: code, partyCode: res.code, mode: 'duel',
  });
  if (sent.error) {
    teardownGame();
    return toast(sent.error);
  }
  game.phase = 'lobby';
  game.isHost = true;
  renderLobby(res.state);
  switchView('v-lobby');
  toast('Invite sent — waiting for them to join.');
}

function showInvite(inv) {
  pendingInvite = inv;
  $('invite-title').textContent = `${inv.fromName || 'A friend'} challenged you`;
  $('invite-sub').textContent = 'A 10-question duel is waiting. Invites expire after 90 seconds.';
  $('invite-pop').classList.remove('hidden');
  clearTimeout(showInvite._t);
  showInvite._t = setTimeout(() => $('invite-pop').classList.add('hidden'), 90000);
}

$('invite-accept').onclick = async () => {
  if (!pendingInvite) return;
  $('invite-pop').classList.add('hidden');
  if (!profile.name) return promptName();
  const res = await api('join', { code: pendingInvite.partyCode, name: profile.name });
  pendingInvite = null;
  if (res.error) return toast(res.error);
  ME.code = res.code;
  ME.playerId = res.playerId;
  await connectEvents();
  game.phase = 'lobby';
  game.isHost = false;
  renderLobby(res.state);
  switchView('v-lobby');
};
$('invite-dismiss').onclick = () => {
  $('invite-pop').classList.add('hidden');
  pendingInvite = null;
};

$('btn-add-friend').onclick = addFriend;
$('friend-code-input').addEventListener('keydown', (e) => { if (e.key === 'Enter') addFriend(); });
$('btn-my-code').onclick = async () => {
  if (!profile.friendCode) return toast('Your code is still being assigned — try again in a moment.');
  try {
    await navigator.clipboard.writeText(profile.friendCode);
    toast(`Your friend code ${profile.friendCode} is copied.`);
  } catch { toast(`Your friend code is ${profile.friendCode}.`); }
};

/* ================= 2v2 ================= */
$('btn-find-2v2').onclick = () => findMatch('2v2');

startPresence();
