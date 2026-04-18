<script>
  import { onMount } from 'svelte';
  import { t } from '../lib/i18n.js';
  import { api } from '../lib/api.js';
  import { getProfile, logout } from '../lib/auth.js';
  import { user, showToast } from '../lib/store.js';
  import { push } from 'svelte-spa-router';
  import Navbar from '../components/Navbar.svelte';

  let lists = $state([]);
  let newListName = $state('');
  let loading = $state(true);
  let creating = $state(false);

  onMount(async () => {
    try {
      const profile = await getProfile();
      user.set(profile);
      lists = await api.get('/lists');
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      loading = false;
    }
  });

  async function createList(e) {
    e.preventDefault();
    if (!newListName.trim()) return;
    creating = true;
    try {
      const newList = await api.post('/lists', { name: newListName.trim() });
      lists = [newList, ...lists];
      newListName = '';
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      creating = false;
    }
  }

  async function deleteList(id) {
    if (!confirm($t('list.delete.confirm'))) return;
    try {
      await api.delete(`/lists/${id}`);
      lists = lists.filter(l => l.id !== id);
    } catch (err) {
      showToast(err.message, 'error');
    }
  }
</script>

<Navbar />

<main class="max-w-lg mx-auto px-4 py-6">
  <form onsubmit={createList} class="flex gap-2 mb-6">
    <input
      type="text"
      bind:value={newListName}
      placeholder={$t('list.new.placeholder')}
      class="input-field flex-1"
    />
    <button type="submit" disabled={creating} class="btn-primary whitespace-nowrap">
      + {$t('list.new')}
    </button>
  </form>

  {#if loading}
    <div class="text-center text-gray-400 py-12">Loading...</div>
  {:else if lists.length === 0}
    <div class="text-center text-gray-400 py-12">{$t('list.empty')}</div>
  {:else}
    <div class="space-y-3">
      {#each lists as list (list.id)}
        <div class="card flex items-center justify-between">
          <button onclick={() => push(`/list/${list.id}`)} class="flex-1 text-left">
            <div class="font-medium text-gray-900">{list.name}</div>
            <div class="text-xs text-gray-400 mt-0.5">
              {list.item_count || 0} {$t('list.items')}
              {#if !list.is_owner}
                <span class="ml-2 text-blue-400">({$t('list.shared.with.you')})</span>
              {/if}
            </div>
          </button>
          {#if list.is_owner}
            <button onclick={() => deleteList(list.id)} class="btn-icon text-red-400 hover:text-red-600 ml-2" title={$t('btn.delete')}>
              <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clip-rule="evenodd" />
              </svg>
            </button>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</main>
