import { get } from 'svelte/store';
import { push } from 'svelte-spa-router';
import { api } from './api.js';
import { voiceContext, showToast } from './store.js';

/** Simple fuzzy item lookup by name against an array of {id, name, checked}. */
function findItemByName(items, query) {
  if (!items || !items.length || !query) return null;
  const q = query.toLowerCase().trim();
  // Exact match first
  let match = items.find((it) => it.name.toLowerCase().trim() === q);
  if (match) return match;
  // Substring either direction
  match = items.find(
    (it) => q.includes(it.name.toLowerCase().trim()) ||
            it.name.toLowerCase().trim().includes(q),
  );
  return match || null;
}

/** Call the backend to parse a transcript into a structured intent. */
export async function parseIntent(transcript) {
  const ctx = get(voiceContext);
  return api.post('/voice/intent', {
    transcript,
    context: {
      route: ctx.route || 'unknown',
      list_id: ctx.list_id,
      list_name: ctx.list_name,
      items: ctx.items || [],
      locale: localStorage.getItem('locale') || 'en',
    },
  });
}

/** Execute an intent using the current voiceContext for list state. */
export async function executeIntent(intent) {
  const ctx = get(voiceContext);
  const fullItems = ctx.items_full || [];

  switch (intent.action) {
    case 'create_list': {
      const name = (intent.list_name || '').trim();
      if (!name) {
        showToast('Kein Listenname erkannt / No list name recognised', 'error');
        return;
      }
      const list = await api.post('/lists', { name });
      showToast(intent.message || `✓ ${name}`, 'success');
      push(`/list/${list.id}`);
      return;
    }
    case 'add_items': {
      if (!ctx.list_id) {
        showToast(intent.message || 'Open a list first', 'error');
        return;
      }
      const items = intent.items || [];
      if (!items.length) {
        showToast('Nothing to add', 'info');
        return;
      }
      const added = [];
      const failed = [];
      for (const it of items) {
        const body = { name: it.name };
        if (it.quantity) body.quantity = it.quantity;
        try {
          await api.post(`/lists/${ctx.list_id}/items`, body);
          added.push(it);
        } catch (err) {
          failed.push({ name: it.name, reason: err.message });
        }
      }
      if (added.length) {
        showToast(
          intent.message ||
            `+ ${added.map((i) => (i.quantity ? i.quantity + ' ' : '') + i.name).join(', ')}`,
          'success',
        );
      }
      if (failed.length) {
        // Don't bury skipped duplicates — show them separately.
        showToast(
          `${failed.length === 1 ? 'Skipped' : 'Skipped ' + failed.length + ':'} ` +
            failed.map((f) => f.name).join(', '),
          'info',
        );
      }
      return;
    }
    case 'check_item':
    case 'uncheck_item':
    case 'delete_item': {
      if (!ctx.list_id) {
        showToast(intent.message || 'Open a list first', 'error');
        return;
      }
      const name = (intent.item_name || '').trim();
      const match = findItemByName(fullItems, name);
      if (!match) {
        showToast(`"${name}" nicht gefunden / not found`, 'error');
        return;
      }
      try {
        if (intent.action === 'delete_item') {
          await api.delete(`/lists/${ctx.list_id}/items/${match.id}`);
        } else {
          const checked = intent.action === 'check_item';
          await api.patch(`/lists/${ctx.list_id}/items/${match.id}/check`, { checked });
        }
        showToast(intent.message || '✓', 'success');
      } catch (err) {
        showToast(err.message || 'Action failed', 'error');
      }
      return;
    }
    case 'clear_list': {
      if (!ctx.list_id) {
        showToast(intent.message || 'Open a list first', 'error');
        return;
      }
      try {
        await api.delete(`/lists/${ctx.list_id}/items`);
        showToast(intent.message || 'Cleared', 'success');
      } catch (err) {
        showToast(err.message || 'Clear failed', 'error');
      }
      return;
    }
    case 'unknown':
    default:
      showToast(intent.message || 'Nicht verstanden / not understood', 'info');
      return;
  }
}
