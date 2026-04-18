<script>
  import { onMount } from 'svelte';
  import { t } from '../lib/i18n.js';
  import { api } from '../lib/api.js';
  import { showToast } from '../lib/store.js';

  let { listId, categories = [], onApply, onClose } = $props();

  let proposals = $state([]);
  let loading = $state(true);
  let applying = $state(false);
  let error = $state('');

  onMount(async () => {
    if (categories.length === 0) {
      error = $t('sort.auto.no.categories');
      loading = false;
      return;
    }
    try {
      const result = await api.post('/lists/' + listId + '/auto-sort');
      proposals = result.assignments;
      if (proposals.length === 0) {
        error = $t('sort.auto.no.items');
      }
    } catch (err) {
      error = err.message;
    } finally {
      loading = false;
    }
  });

  function toggleProposal(idx) {
    proposals[idx] = { ...proposals[idx], _excluded: !proposals[idx]._excluded };
  }

  async function applySort() {
    applying = true;
    const assignments = proposals
      .filter(p => !p._excluded)
      .map(p => ({ item_id: p.item_id, category_id: p.category_id }));
    try {
      await api.post('/lists/' + listId + '/auto-sort/apply', { assignments });
      onApply(assignments);
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      applying = false;
    }
  }
</script>

<div class="fixed inset-0 bg-black/50 z-50 flex items-end sm:items-center justify-center" onclick={onClose}>
  <div class="bg-white rounded-t-2xl sm:rounded-2xl w-full max-w-md p-6 max-h-[80vh] overflow-y-auto" onclick={(e) => e.stopPropagation()}>
    <div class="flex justify-between items-center mb-4">
      <h2 class="text-lg font-bold flex items-center gap-2">
        <span class="text-purple-500">&#10024;</span> {$t('sort.auto')}
      </h2>
      <button onclick={onClose} class="btn-icon">&times;</button>
    </div>

    <p class="text-sm text-gray-500 mb-4">{$t('sort.auto.description')}</p>

    {#if loading}
      <div class="text-center py-8 text-gray-400">
        <div class="animate-spin inline-block w-6 h-6 border-2 border-purple-500 border-t-transparent rounded-full mb-2"></div>
        <div>{$t('sort.auto.loading')}</div>
      </div>
    {:else if error}
      <div class="text-center py-8 text-gray-400">{error}</div>
    {:else}
      <div class="space-y-2 mb-6">
        {#each proposals as p, i (p.item_id)}
          <button
            onclick={() => toggleProposal(i)}
            class="w-full text-left px-3 py-2 rounded-lg border transition-all
              {p._excluded ? 'border-gray-200 opacity-40' : 'border-purple-200 bg-purple-50'}"
          >
            <div class="flex items-center justify-between">
              <div>
                <span class="font-medium">{p.item_name}</span>
                <span class="text-gray-400 mx-1">&rarr;</span>
                <span class="text-purple-600">{p.category_name}</span>
              </div>
              <span class="text-xs text-gray-400">
                {Math.round(p.confidence * 100)}%
              </span>
            </div>
          </button>
        {/each}
      </div>

      <div class="flex gap-2">
        <button onclick={onClose} class="btn-secondary flex-1">{$t('sort.auto.cancel')}</button>
        <button onclick={applySort} disabled={applying} class="btn-primary flex-1 bg-purple-500 hover:bg-purple-600">
          {applying ? '...' : $t('sort.auto.apply')}
        </button>
      </div>
    {/if}
  </div>
</div>
