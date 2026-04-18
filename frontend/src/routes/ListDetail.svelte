<script>
  import { onMount, onDestroy } from 'svelte';
  import { t } from '../lib/i18n.js';
  import { api } from '../lib/api.js';
  import { getProfile } from '../lib/auth.js';
  import { showToast, user } from '../lib/store.js';
  import { createListSocket } from '../lib/ws.js';
  import Navbar from '../components/Navbar.svelte';
  import ShareDialog from '../components/ShareDialog.svelte';
  import AutoSortDialog from '../components/AutoSortDialog.svelte';

  let { params } = $props();

  let list = $state(null);
  let items = $state([]);
  let categories = $state([]);
  let shares = $state([]);
  let loading = $state(true);
  let newItemName = $state('');
  let newItemQty = $state('');
  let newCatName = $state('');
  let showShare = $state(false);
  let showAutoSort = $state(false);
  let addingItem = $state(false);
  let addingCat = $state(false);
  let socket = null;
  let currentUser = $state(null);
  let userColorMap = $state({});

  onMount(async () => {
    try {
      currentUser = await getProfile();
      user.set(currentUser);

      const [listData, itemsData, catsData, sharesData] = await Promise.all([
        api.get('/lists/' + params.id),
        api.get('/lists/' + params.id + '/items'),
        api.get('/lists/' + params.id + '/categories'),
        api.get('/lists/' + params.id + '/shares').catch(() => []),
      ]);

      list = listData;
      items = itemsData;
      categories = catsData;
      shares = sharesData;
      buildColorMap();

      const token = localStorage.getItem('access_token');
      socket = createListSocket(params.id, token, {
        onMessage: handleWsMessage,
      });
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      loading = false;
    }
  });

  onDestroy(() => {
    socket?.close();
  });

  function buildColorMap() {
    const map = {};
    if (currentUser) map[currentUser.id] = { name: currentUser.display_name, color: currentUser.color };
    shares.forEach(s => { map[s.user_id] = { name: s.user_display_name, color: s.user_color }; });
    userColorMap = map;
  }

  function handleWsMessage(msg) {
    switch (msg.type) {
      case 'item_added':
        items = [...items, msg.item];
        break;
      case 'item_updated':
        items = items.map(i => i.id === msg.item.id ? msg.item : i);
        break;
      case 'item_checked':
        items = items.map(i => i.id === msg.item_id ? { ...i, checked: msg.checked } : i);
        break;
      case 'item_removed':
        items = items.filter(i => i.id !== msg.item_id);
        break;
      case 'items_reordered': {
        const orderMap = {};
        msg.item_ids.forEach((id, idx) => { orderMap[id] = (idx + 1) * 10; });
        items = items.map(i => orderMap[i.id] !== undefined ? { ...i, sort_order: orderMap[i.id] } : i)
                     .sort((a, b) => a.sort_order - b.sort_order);
        break;
      }
      case 'category_added':
        categories = [...categories, msg.category];
        break;
      case 'category_updated':
        categories = categories.map(c => c.id === msg.category.id ? { ...c, ...msg.category } : c);
        break;
      case 'category_removed':
        categories = categories.filter(c => c.id !== msg.category_id);
        items = items.map(i => i.category_id === msg.category_id ? { ...i, category_id: null } : i);
        break;
      case 'categories_reordered': {
        const catOrder = {};
        msg.category_ids.forEach((id, idx) => { catOrder[id] = (idx + 1) * 10; });
        categories = categories.map(c => catOrder[c.id] !== undefined ? { ...c, sort_order: catOrder[c.id] } : c)
                               .sort((a, b) => a.sort_order - b.sort_order);
        break;
      }
    }
  }

  function getGroupedItems() {
    const sorted = [...categories].sort((a, b) => a.sort_order - b.sort_order);
    const groups = [];
    const uncategorized = items.filter(i => !i.category_id).sort((a, b) => a.sort_order - b.sort_order);
    if (uncategorized.length > 0) {
      groups.push({ category: null, items: uncategorized });
    }
    for (const cat of sorted) {
      const catItems = items.filter(i => i.category_id === cat.id).sort((a, b) => a.sort_order - b.sort_order);
      groups.push({ category: cat, items: catItems });
    }
    return groups;
  }

  async function addItem(e) {
    e.preventDefault();
    if (!newItemName.trim()) return;
    addingItem = true;
    try {
      const item = await api.post('/lists/' + params.id + '/items', {
        name: newItemName.trim(),
        quantity: newItemQty.trim() || null,
      });
      items = [...items, item];
      newItemName = '';
      newItemQty = '';
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      addingItem = false;
    }
  }

  async function toggleCheck(item) {
    try {
      const updated = await api.patch('/lists/' + params.id + '/items/' + item.id + '/check');
      items = items.map(i => i.id === updated.id ? updated : i);
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  async function deleteItem(itemId) {
    try {
      await api.delete('/lists/' + params.id + '/items/' + itemId);
      items = items.filter(i => i.id !== itemId);
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  async function moveItem(itemId, direction) {
    const idx = items.findIndex(i => i.id === itemId);
    if (idx < 0) return;
    const swapIdx = direction === 'up' ? idx - 1 : idx + 1;
    if (swapIdx < 0 || swapIdx >= items.length) return;
    const newItems = [...items];
    [newItems[idx], newItems[swapIdx]] = [newItems[swapIdx], newItems[idx]];
    items = newItems;
    try {
      await api.patch('/lists/' + params.id + '/items/reorder', {
        item_ids: newItems.map(i => i.id),
      });
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  async function addCategory(e) {
    e.preventDefault();
    if (!newCatName.trim()) return;
    addingCat = true;
    try {
      const cat = await api.post('/lists/' + params.id + '/categories', { name: newCatName.trim() });
      categories = [...categories, cat];
      newCatName = '';
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      addingCat = false;
    }
  }

  async function deleteCategory(catId) {
    if (!confirm($t('category.delete.confirm'))) return;
    try {
      await api.delete('/lists/' + params.id + '/categories/' + catId);
      categories = categories.filter(c => c.id !== catId);
      items = items.map(i => i.category_id === catId ? { ...i, category_id: null } : i);
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  async function moveCategory(catId, direction) {
    const sorted = [...categories].sort((a, b) => a.sort_order - b.sort_order);
    const idx = sorted.findIndex(c => c.id === catId);
    if (idx < 0) return;
    const swapIdx = direction === 'up' ? idx - 1 : idx + 1;
    if (swapIdx < 0 || swapIdx >= sorted.length) return;
    [sorted[idx], sorted[swapIdx]] = [sorted[swapIdx], sorted[idx]];
    categories = sorted.map((c, i) => ({ ...c, sort_order: (i + 1) * 10 }));
    try {
      await api.patch('/lists/' + params.id + '/categories/reorder', {
        category_ids: sorted.map(c => c.id),
      });
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  function handleAutoSortApplied(assignments) {
    for (const a of assignments) {
      items = items.map(i =>
        i.id === a.item_id ? { ...i, category_id: a.category_id } : i
      );
    }
    showAutoSort = false;
    showToast('Items sorted!', 'success');
  }

  let grouped = $derived(getGroupedItems());
</script>

<Navbar />

{#if loading}
  <div class="text-center text-gray-400 py-12">Loading...</div>
{:else if list}
  <main class="max-w-lg mx-auto px-4 py-4 pb-32">
    <div class="flex items-center justify-between mb-4">
      <div class="flex items-center gap-2">
        <a href="#/" class="btn-icon">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M9.707 16.707a1 1 0 01-1.414 0l-6-6a1 1 0 010-1.414l6-6a1 1 0 011.414 1.414L5.414 9H17a1 1 0 110 2H5.414l4.293 4.293a1 1 0 010 1.414z" clip-rule="evenodd" />
          </svg>
        </a>
        <h1 class="text-xl font-bold">{list.name}</h1>
      </div>
      <div class="flex items-center gap-1">
        <button onclick={() => showAutoSort = true} class="btn-icon text-purple-500" title={$t('sort.auto')}>
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
            <path d="M5 12a1 1 0 102 0V6.414l1.293 1.293a1 1 0 001.414-1.414l-3-3a1 1 0 00-1.414 0l-3 3a1 1 0 001.414 1.414L5 6.414V12zM15 8a1 1 0 10-2 0v5.586l-1.293-1.293a1 1 0 00-1.414 1.414l3 3a1 1 0 001.414 0l3-3a1 1 0 00-1.414-1.414L15 13.586V8z" />
          </svg>
        </button>
        {#if list.is_owner}
          <button onclick={() => showShare = true} class="btn-icon text-blue-500" title={$t('list.share')}>
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path d="M15 8a3 3 0 10-2.977-2.63l-4.94 2.47a3 3 0 100 4.319l4.94 2.47a3 3 0 10.895-1.789l-4.94-2.47a3.027 3.027 0 000-.74l4.94-2.47C13.456 7.68 14.19 8 15 8z" />
            </svg>
          </button>
        {/if}
      </div>
    </div>

    {#if shares.length > 0}
      <div class="flex flex-wrap gap-2 mb-4 text-xs">
        {#if currentUser}
          <span class="flex items-center gap-1">
            <span class="w-3 h-3 rounded-full inline-block" style="background-color: {currentUser.color}"></span>
            {currentUser.display_name}
          </span>
        {/if}
        {#each shares as share}
          <span class="flex items-center gap-1">
            <span class="w-3 h-3 rounded-full inline-block" style="background-color: {share.user_color}"></span>
            {share.user_display_name}
          </span>
        {/each}
      </div>
    {/if}

    <form onsubmit={addCategory} class="flex gap-2 mb-3">
      <input type="text" bind:value={newCatName} placeholder={$t('category.new.placeholder')} class="input-field flex-1 text-sm" />
      <button type="submit" disabled={addingCat} class="btn-secondary text-sm whitespace-nowrap">+ {$t('category.new')}</button>
    </form>

    <form onsubmit={addItem} class="flex gap-2 mb-6">
      <input type="text" bind:value={newItemName} placeholder={$t('item.add.placeholder')} class="input-field flex-1" />
      <input type="text" bind:value={newItemQty} placeholder={$t('item.quantity.placeholder')} class="input-field w-20" />
      <button type="submit" disabled={addingItem} class="btn-primary whitespace-nowrap">+</button>
    </form>

    {#each grouped as group (group.category?.id || '__uncategorized')}
      <div class="mb-4">
        <div class="flex items-center justify-between mb-2 px-1">
          {#if group.category}
            <h3 class="text-sm font-semibold text-gray-600 uppercase tracking-wide">
              {group.category.name}
              <span class="text-gray-300 font-normal">({group.items.length})</span>
            </h3>
            <div class="flex items-center gap-0.5">
              <button onclick={() => moveCategory(group.category.id, 'up')} class="btn-icon p-1">
                <svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M14.707 12.707a1 1 0 01-1.414 0L10 9.414l-3.293 3.293a1 1 0 01-1.414-1.414l4-4a1 1 0 011.414 0l4 4a1 1 0 010 1.414z" clip-rule="evenodd" /></svg>
              </button>
              <button onclick={() => moveCategory(group.category.id, 'down')} class="btn-icon p-1">
                <svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd" /></svg>
              </button>
              <button onclick={() => deleteCategory(group.category.id)} class="btn-icon p-1 text-red-400">
                <svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" /></svg>
              </button>
            </div>
          {:else}
            <h3 class="text-sm font-semibold text-gray-400 italic">{$t('item.uncategorized')}</h3>
          {/if}
        </div>

        {#each group.items as item (item.id)}
          <div
            class="card mb-2 flex items-center gap-3 py-3 {item.checked ? 'opacity-60' : ''}"
            style="border-left: 4px solid {item.added_by_color}"
          >
            <button onclick={() => toggleCheck(item)} class="flex-shrink-0">
              <div class="w-6 h-6 rounded-full border-2 flex items-center justify-center transition-colors
                {item.checked ? 'bg-green-500 border-green-500' : 'border-gray-300 hover:border-green-400'}">
                {#if item.checked}
                  <svg class="h-4 w-4 text-white" viewBox="0 0 20 20" fill="currentColor">
                    <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd" />
                  </svg>
                {/if}
              </div>
            </button>

            <div class="flex-1 min-w-0">
              <span class={item.checked ? 'checked-item' : ''}>{item.name}</span>
              {#if item.quantity}
                <span class="text-xs text-gray-400 ml-2">({item.quantity})</span>
              {/if}
            </div>

            <div class="flex items-center gap-0.5 flex-shrink-0">
              <button onclick={() => moveItem(item.id, 'up')} class="btn-icon p-1">
                <svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M14.707 12.707a1 1 0 01-1.414 0L10 9.414l-3.293 3.293a1 1 0 01-1.414-1.414l4-4a1 1 0 011.414 0l4 4a1 1 0 010 1.414z" clip-rule="evenodd" /></svg>
              </button>
              <button onclick={() => moveItem(item.id, 'down')} class="btn-icon p-1">
                <svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd" /></svg>
              </button>
              <button onclick={() => deleteItem(item.id)} class="btn-icon p-1 text-red-400">
                <svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" /></svg>
              </button>
            </div>
          </div>
        {/each}

        {#if group.items.length === 0 && group.category}
          <div class="text-center text-gray-300 text-sm py-3 border border-dashed border-gray-200 rounded-lg">—</div>
        {/if}
      </div>
    {/each}

    {#if items.length === 0}
      <div class="text-center text-gray-400 py-12">{$t('sort.auto.no.items')}</div>
    {/if}
  </main>

  {#if showShare}
    <ShareDialog
      listId={params.id}
      bind:shares
      onClose={() => { showShare = false; buildColorMap(); }}
    />
  {/if}

  {#if showAutoSort}
    <AutoSortDialog
      listId={params.id}
      {categories}
      onApply={handleAutoSortApplied}
      onClose={() => showAutoSort = false}
    />
  {/if}
{/if}
