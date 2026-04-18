<script>
  import { onMount } from 'svelte';
  import { t, locale } from '../lib/i18n.js';
  import { api } from '../lib/api.js';
  import { getProfile, logout } from '../lib/auth.js';
  import { user, showToast, voiceContext } from '../lib/store.js';
  import { push } from 'svelte-spa-router';
  import Navbar from '../components/Navbar.svelte';

  voiceContext.set({ route: 'list_overview', list_id: null, list_name: null, items: [], items_full: [] });

  let lists = $state([]);
  let newListName = $state('');
  let loading = $state(true);
  let creating = $state(false);
  let ollamaEnabled = $state(false);

  // Scan flow state
  let scanning = $state(false);
  let scanResult = $state(null); // { categories: [], items: [{name, quantity, category, include}] }
  let scanListName = $state('');
  let savingScan = $state(false);

  onMount(async () => {
    try {
      const profile = await getProfile();
      user.set(profile);
      const [listsData, health] = await Promise.all([
        api.get('/lists'),
        api.get('/health').catch(() => ({ ollama_enabled: false })),
      ]);
      lists = listsData;
      ollamaEnabled = !!health?.ollama_enabled;
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

  async function leaveList(id) {
    if (!confirm($t('list.leave.confirm'))) return;
    try {
      await api.delete(`/lists/${id}/shares/me`);
      lists = lists.filter(l => l.id !== id);
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  async function compressImage(file, maxWidth = 1280, quality = 0.85) {
    return new Promise((resolve) => {
      const img = new Image();
      img.onload = () => {
        const ratio = Math.min(1, maxWidth / img.width);
        const canvas = document.createElement('canvas');
        canvas.width = img.width * ratio;
        canvas.height = img.height * ratio;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        canvas.toBlob((blob) => resolve(blob), 'image/jpeg', quality);
      };
      img.src = URL.createObjectURL(file);
    });
  }

  function startScan() {
    const name = newListName.trim();
    if (!name) {
      showToast($t('scan.name.required'), 'error');
      return;
    }
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.capture = 'environment';
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      scanning = true;
      try {
        const compressed = await compressImage(file);
        const token = localStorage.getItem('access_token') || sessionStorage.getItem('access_token');
        const fd = new FormData();
        fd.append('file', compressed, 'list.jpg');
        fd.append('language', $locale === 'de' ? 'German' : 'English');
        const res = await fetch('/api/v1/lists/scan', {
          method: 'POST',
          headers: { 'Authorization': 'Bearer ' + token },
          body: fd,
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: 'Scan failed' }));
          throw new Error(err.detail || 'Scan failed');
        }
        const data = await res.json();
        scanResult = {
          categories: data.categories || [],
          items: (data.items || []).map(it => ({ ...it, include: true })),
        };
        scanListName = name;
      } catch (err) {
        showToast(err.message, 'error');
      } finally {
        scanning = false;
      }
    };
    input.click();
  }

  function toggleAllItems(value) {
    if (!scanResult) return;
    scanResult = { ...scanResult, items: scanResult.items.map(it => ({ ...it, include: value })) };
  }

  function cancelScan() {
    scanResult = null;
    scanListName = '';
  }

  async function saveScan() {
    if (!scanResult) return;
    savingScan = true;
    try {
      const accepted = scanResult.items.filter(it => it.include);
      const list = await api.post('/lists', { name: scanListName.trim() });

      // Create categories that are actually used by at least one accepted item
      const usedCatNames = [];
      const seen = new Set();
      for (const it of accepted) {
        const c = (it.category || '').trim();
        if (c && !seen.has(c.toLowerCase())) {
          seen.add(c.toLowerCase());
          usedCatNames.push(c);
        }
      }

      const catIdByName = {};
      for (const catName of usedCatNames) {
        const cat = await api.post('/lists/' + list.id + '/categories', { name: catName });
        catIdByName[catName.toLowerCase()] = cat.id;
      }

      for (const it of accepted) {
        const body = { name: it.name };
        if (it.quantity) body.quantity = it.quantity;
        const catKey = (it.category || '').trim().toLowerCase();
        if (catKey && catIdByName[catKey]) body.category_id = catIdByName[catKey];
        await api.post('/lists/' + list.id + '/items', body);
      }

      lists = [list, ...lists];
      scanResult = null;
      scanListName = '';
      newListName = '';
      showToast($t('scan.saved'), 'success');
      push('/list/' + list.id);
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      savingScan = false;
    }
  }

  // Grouped view of scan items by category
  let groupedScan = $derived.by(() => {
    if (!scanResult) return [];
    const buckets = new Map();
    const order = [];
    for (const cat of scanResult.categories) {
      buckets.set(cat.toLowerCase(), { name: cat, items: [] });
      order.push(cat.toLowerCase());
    }
    for (const it of scanResult.items) {
      const key = (it.category || $t('item.uncategorized')).trim().toLowerCase();
      if (!buckets.has(key)) {
        buckets.set(key, { name: it.category || $t('item.uncategorized'), items: [] });
        order.push(key);
      }
      buckets.get(key).items.push(it);
    }
    return order.map(k => buckets.get(k));
  });
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
    {#if ollamaEnabled}
      <button
        type="button"
        onclick={startScan}
        disabled={scanning}
        class="btn-icon border border-gray-200 rounded-lg px-3"
        title={$t('scan.tooltip')}
        aria-label={$t('scan.tooltip')}
      >
        {#if scanning}
          <svg class="h-5 w-5 animate-spin text-gray-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 12a9 9 0 11-9-9" stroke-linecap="round" />
          </svg>
        {:else}
          <svg class="h-5 w-5 text-gray-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z" />
            <circle cx="12" cy="13" r="4" />
          </svg>
        {/if}
      </button>
    {/if}
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
          {:else}
            <button onclick={() => leaveList(list.id)} class="btn-icon text-gray-400 hover:text-red-500 ml-2" title={$t('list.leave')}>
              <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M3 3a1 1 0 011 1v12a1 1 0 11-2 0V4a1 1 0 011-1zm7.707 3.293a1 1 0 010 1.414L9.414 9H17a1 1 0 110 2H9.414l1.293 1.293a1 1 0 01-1.414 1.414l-3-3a1 1 0 010-1.414l3-3a1 1 0 011.414 0z" clip-rule="evenodd" />
              </svg>
            </button>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</main>

{#if scanning && !scanResult}
  <div class="fixed inset-0 bg-black/40 z-50 flex items-center justify-center" role="status">
    <div class="bg-white rounded-xl p-6 max-w-xs text-center space-y-3">
      <svg class="h-8 w-8 mx-auto animate-spin text-blue-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 12a9 9 0 11-9-9" stroke-linecap="round" />
      </svg>
      <div class="text-sm text-gray-600">{$t('scan.processing')}</div>
    </div>
  </div>
{/if}

{#if scanResult}
  <div class="fixed inset-0 bg-black/40 z-50 flex items-end sm:items-center justify-center" role="dialog">
    <div class="bg-white rounded-t-2xl sm:rounded-2xl w-full max-w-md max-h-[90vh] flex flex-col">
      <div class="px-5 pt-5 pb-3 flex items-center justify-between">
        <h2 class="text-lg font-bold">{$t('scan.preview.title')}</h2>
        <button onclick={cancelScan} class="btn-icon" aria-label={$t('btn.close')}>&times;</button>
      </div>
      <div class="px-5 text-xs text-gray-500 flex items-center gap-3 pb-2">
        <span>{scanListName}</span>
        <span class="ml-auto flex gap-2">
          <button onclick={() => toggleAllItems(true)} class="underline hover:text-gray-700">{$t('scan.all')}</button>
          <button onclick={() => toggleAllItems(false)} class="underline hover:text-gray-700">{$t('scan.none')}</button>
        </span>
      </div>
      <div class="flex-1 overflow-y-auto px-5 py-2">
        {#if scanResult.items.length === 0}
          <p class="text-sm text-gray-400 text-center py-6">{$t('scan.empty')}</p>
        {:else}
          {#each groupedScan as group}
            {#if group.items.length > 0}
              <div class="mb-4">
                <h3 class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">{group.name}</h3>
                <div class="space-y-1">
                  {#each group.items as it}
                    <label class="flex items-center gap-2 py-1 cursor-pointer">
                      <input type="checkbox" bind:checked={it.include} class="accent-blue-500" />
                      <span class="text-sm text-gray-800 flex-1">{it.name}</span>
                      {#if it.quantity}<span class="text-xs text-gray-400">{it.quantity}</span>{/if}
                    </label>
                  {/each}
                </div>
              </div>
            {/if}
          {/each}
        {/if}
      </div>
      <div class="border-t border-gray-100 px-5 py-3 flex gap-2">
        <button onclick={cancelScan} class="flex-1 py-2 rounded-lg border border-gray-200 text-sm">{$t('btn.cancel')}</button>
        <button
          onclick={saveScan}
          disabled={savingScan || scanResult.items.filter(it => it.include).length === 0}
          class="flex-1 btn-primary text-sm"
        >{savingScan ? '…' : $t('scan.save')}</button>
      </div>
    </div>
  </div>
{/if}
