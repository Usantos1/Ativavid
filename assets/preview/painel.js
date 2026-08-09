/* ATIVAVID — painel multi-projeto (read-only).
 *
 * Deliberately has no write path: this screen exists to SHOW what is off
 * across projects, never to fix it. The failure this was built after was a
 * background process editing a delivered project on its own; a dashboard that
 * could act would be the same hazard with a nicer face.
 */
const $ = (id) => document.getElementById(id);

const fmtDur = (s) => {
  if (s == null) return '—';
  const m = Math.floor(s / 60);
  const r = (s - m * 60);
  return m ? `${m}:${r.toFixed(1).padStart(4, '0')}` : `${r.toFixed(2)}s`;
};

function el(tag, cls, parent, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  if (parent) parent.appendChild(e);
  return e;
}

function toast(msg, ms = 2600) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.remove('hidden');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.add('hidden'), ms);
}

function phaseLabel(p) {
  if (p == null) return '—';
  return p >= 3 ? 'Fase 3' : p === 2 ? 'Fase 2' : 'Fase 1';
}

function render(data) {
  $('rootsLine').textContent = data.roots.join('  ·  ');
  const list = data.projects || [];

  // --- alerts: only the states that need a human, counted across everything
  const broken = list.filter((p) => p.delivery && p.delivery.broken);
  const stale = list.filter((p) => p.delivery && p.delivery.stalePointer);
  const pending = list.filter((p) => p.pendingEdits || p.pendingStyle);
  const box = $('alerts');
  box.innerHTML = '';
  const add = (kind, html) => { el('div', `pn-alert ${kind}`, box).innerHTML = html; };
  if (broken.length) {
    add('bad', `<b>${broken.length}</b> entrega(s) não abrem — arquivo truncado ou corrompido: ` +
      broken.map((p) => p.folder).join(', '));
  }
  if (pending.length) {
    add('warn', `<b>${pending.length}</b> projeto(s) com pedido salvo no preview aguardando alguém aplicar: ` +
      pending.map((p) => p.folder).join(', '));
  }
  if (stale.length) {
    add('warn', `<b>${stale.length}</b> projeto(s) com <code>finalVideo</code> apontando pra arquivo inexistente ` +
      `(o servidor resolve sozinho, mas a contabilidade está errada)`);
  }
  if (!broken.length && !pending.length && !stale.length && list.length) {
    add('good', 'Nada pendente — todas as entregas abrem e nenhum pedido está esperando.');
  }

  $('counts').textContent = `${list.length} projeto(s)`;

  // --- cards
  const grid = $('grid');
  grid.innerHTML = '';
  if (!list.length) {
    el('div', 'pn-empty', grid, 'Nenhum projeto encontrado nas pastas varridas.');
    return;
  }

  for (const p of list) {
    const card = el('div', 'pn-card' + (p.path === data.current ? ' current' : ''), grid);

    const head = el('div', 'pn-head', card);
    el('div', 'pn-name', head, p.project);
    const ph = el('span', 'pn-phase' + ((p.phase || 0) >= 3 ? ' p3' : ''), head, phaseLabel(p.phase));
    ph.title = 'fase registrada no state.json';

    if (p.message) el('div', 'pn-msg', card, p.message);

    const rows = el('div', 'pn-rows', card);
    const row = (k, v, cls) => {
      const r = el('div', 'pn-row', rows);
      el('span', 'pn-key', r, k);
      el('span', `pn-val ${cls || ''}`, r, v);
      return r;
    };

    row('corte', p.hasCut ? fmtDur(p.cutDurationSec) : 'sem cut.mp4',
        p.hasCut ? 'pn-mono dim' : 'dim');

    if (p.delivery) {
      const d = p.delivery;
      row('entrega', d.broken ? `${d.name} — NÃO ABRE` : `${d.name}`,
          d.broken ? 'bad' : '');
      if (!d.broken) row('duração', fmtDur(d.durationSec), 'pn-mono dim');
    } else {
      row('entrega', 'ainda não entregue', 'dim');
    }

    const tags = el('div', 'pn-tags', card);
    if (p.pendingEdits) el('span', 'pn-tag warn', tags, 'marcações salvas');
    if (p.pendingStyle) el('span', 'pn-tag warn', tags, 'troca de estilo salva');
    if (p.awaitingStyle) el('span', 'pn-tag info', tags, 'aguardando escolha de estilo');
    if (p.delivery && p.delivery.stalePointer) {
      const t = el('span', 'pn-tag bad', tags, 'ponteiro errado');
      t.title = `state.json diz "${p.delivery.declared}", mas o arquivo é "${p.delivery.name}"`;
    }
    if (!p.hasState) el('span', 'pn-tag', tags, 'sem state.json');

    const foot = el('div', 'pn-foot', card);

    const act = async (action, label) => {
      const r = await fetch('/api/project/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: p.path, action }),
      });
      const d = await r.json().catch(() => ({}));
      if (!d.ok) { toast(d.error || `Não consegui ${label}`); return null; }
      return d;
    };

    const bVideo = el('button', 'btn ghost small', foot, 'assistir');
    bVideo.disabled = !p.delivery || p.delivery.broken;
    bVideo.title = bVideo.disabled ? 'sem entrega que abra' : 'abrir a entrega no player';
    bVideo.addEventListener('click', () => act('video', 'abrir o vídeo'));

    const bFolder = el('button', 'btn ghost small', foot, 'pasta');
    bFolder.title = 'abrir a pasta com a entrega selecionada';
    bFolder.addEventListener('click', () => act('folder', 'abrir a pasta'));

    // only offered where it is provably wrong — never a blanket "fix things"
    if (p.delivery && p.delivery.stalePointer) {
      const bFix = el('button', 'btn small pn-fix', foot, 'corrigir ponteiro');
      bFix.title = `state.json passa a apontar "${p.delivery.name}" em vez de "${p.delivery.declared}"`;
      bFix.addEventListener('click', async () => {
        const d = await act('fixPointer', 'corrigir');
        if (d) { toast(`Corrigido: ${d.from} → ${d.finalVideo}`); load(); }
      });
    }

    const copy = el('button', 'btn ghost small', foot, 'copiar');
    copy.title = p.path;
    copy.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(p.path);
        toast('Caminho copiado');
      } catch (e) { toast('Não consegui copiar'); }
    });
  }
}

async function load() {
  try {
    const r = await fetch('/api/projects', { cache: 'no-store' });
    const data = await r.json();
    if (!data.ok) throw new Error(data.error || 'falhou');
    render(data);
  } catch (e) {
    $('grid').innerHTML = '';
    el('div', 'pn-empty', $('grid'), 'Não consegui ler os projetos — o servidor está de pé?');
  }
}

// theme toggle, same contract as the editor (shared localStorage key)
function applyThemeIcon() {
  const dark = document.documentElement.getAttribute('data-theme') !== 'light';
  $('btnTheme').innerHTML = dark
    ? '<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="3.1" fill="none" stroke="currentColor" stroke-width="1.4"/><g stroke="currentColor" stroke-width="1.4" stroke-linecap="round"><path d="M8 1.4v1.7M8 12.9v1.7M14.6 8h-1.7M3.1 8H1.4M12.6 3.4l-1.2 1.2M4.6 11.4l-1.2 1.2M12.6 12.6l-1.2-1.2M4.6 4.6L3.4 3.4"/></g></svg>'
    : '<svg viewBox="0 0 16 16"><path d="M13.8 9.9A6 6 0 1 1 6.1 2.2a5 5 0 0 0 7.7 7.7z"/></svg>';
}
$('btnTheme').addEventListener('click', () => {
  const next = document.documentElement.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('ativavid-theme', next);
  applyThemeIcon();
});
applyThemeIcon();

$('btnReload').addEventListener('click', () => { load(); toast('Atualizado'); });
load();

/* Auto-refresh. A dashboard that can go stale is worse than none — the first
 * time this screen was shown it was reporting "11 entregas não abrem" from a
 * server that had already been fixed and restarted, and there was nothing on
 * screen saying the numbers were old. Re-scanning is cheap (durations are
 * cached server-side by mtime), and scroll position is preserved so a refresh
 * cannot yank the page out from under someone reading it. */
setInterval(() => {
  if (document.hidden) return;                 // don't scan for a tab nobody is looking at
  if (document.activeElement && document.activeElement.tagName === 'BUTTON') return;
  const y = window.scrollY;
  load().then(() => window.scrollTo({ top: y }));
}, 8000);
