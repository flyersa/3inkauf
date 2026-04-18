<script>
  import { onMount, onDestroy } from 'svelte';
  import { t } from '../lib/i18n.js';
  import { api } from '../lib/api.js';
  import { getProfile } from '../lib/auth.js';
  import { showToast, user, voiceContext } from '../lib/store.js';
  import { createListSocket } from '../lib/ws.js';
  import { dndzone } from 'svelte-dnd-action';
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
  let showAddCategory = $state(false);

  // Keep the voice-control context in sync with this route's state.
  $effect(() => {
    voiceContext.set({
      route: 'list',
      list_id: list?.id || params.id,
      list_name: list?.name || null,
      items: items.map((it) => it.name),
      items_full: items.map((it) => ({ id: it.id, name: it.name, checked: it.checked })),
    });
  });
  let addingItem = $state(false);
  let addingCat = $state(false);
  let socket = null;
  let currentUser = $state(null);
  let catInput = $state(null);
  let savingHints = $state(false);
  let photoMenuItemId = $state(null);
  let viewingImage = $state(null);
  let categoryPickerItemId = $state(null);

  // Category rename
  let renamingCatId = $state(null);
  let renameCatValue = $state('');
  let renameInput = $state(null);

  // DnD data (mutable, not $derived)
  let sortedCats = $state([]);
  let itemGroups = $state({});
  let uncatItems = $state([]);

  const flipDurationMs = 200;

  function rebuildGroups() {
    sortedCats = [...categories].sort((a, b) => a.sort_order - b.sort_order);
    const groups = {};
    for (const cat of sortedCats) {
      groups[cat.id] = items.filter(i => i.category_id === cat.id).sort((a, b) => a.sort_order - b.sort_order);
    }
    itemGroups = groups;
    uncatItems = items.filter(i => !i.category_id).sort((a, b) => a.sort_order - b.sort_order);
  }

  let originalCategoryMap = {};
  function snapshotCategoryMap() {
    originalCategoryMap = {};
    for (const item of items) originalCategoryMap[item.id] = item.category_id;
  }

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
      list = listData; items = itemsData; categories = catsData; shares = sharesData;
      rebuildGroups(); snapshotCategoryMap();
      const token = localStorage.getItem('access_token');
      socket = createListSocket(params.id, token, { onMessage: handleWsMessage });
    } catch (err) { showToast(err.message, 'error'); }
    finally { loading = false; }
  });

  onDestroy(() => { socket?.close(); });

  function handleWsMessage(msg) {
    switch (msg.type) {
      case 'item_added':
        // The backend now broadcasts to everyone including the originator, so
        // the manual optimistic-add path and the voice/SW-push path both land
        // here. Dedup by id to avoid double rendering.
        if (!items.some((i) => i.id === msg.item.id)) items = [...items, msg.item];
        rebuildGroups();
        break;
      case 'item_updated':
        items = items.map(i => i.id === msg.item.id ? msg.item : i);
        rebuildGroups();
        break;
      case 'item_checked':
        items = items.map(i => i.id === msg.item_id ? { ...i, checked: msg.checked } : i);
        rebuildGroups();
        break;
      case 'item_removed':
        items = items.filter(i => i.id !== msg.item_id);
        rebuildGroups();
        break;
      case 'items_cleared':
        items = [];
        rebuildGroups();
        break;
      case 'items_reordered': {
        const m = {}; msg.item_ids.forEach((id, idx) => { m[id] = (idx+1)*10; });
        items = items.map(i => m[i.id] !== undefined ? { ...i, sort_order: m[i.id] } : i).sort((a,b) => a.sort_order - b.sort_order);
        break;
      }
      case 'category_added': categories = [...categories, msg.category]; break;
      case 'category_updated': categories = categories.map(c => c.id === msg.category.id ? { ...c, ...msg.category } : c); break;
      case 'category_removed':
        categories = categories.filter(c => c.id !== msg.category_id);
        items = items.map(i => i.category_id === msg.category_id ? { ...i, category_id: null } : i); break;
      case 'categories_reordered': {
        const m = {}; msg.category_ids.forEach((id, idx) => { m[id] = (idx+1)*10; });
        categories = categories.map(c => m[c.id] !== undefined ? { ...c, sort_order: m[c.id] } : c).sort((a,b) => a.sort_order - b.sort_order);
        break;
      }
    }
    rebuildGroups(); snapshotCategoryMap();
  }

  // === Category DnD ===
  function handleCatConsider(e) { sortedCats = e.detail.items; }
  async function handleCatFinalize(e) {
    sortedCats = e.detail.items;
    categories = sortedCats.map((c, i) => ({ ...c, sort_order: (i+1)*10 }));
    try { await api.patch('/lists/' + params.id + '/categories/reorder', { category_ids: sortedCats.map(c => c.id) }); }
    catch (err) { showToast(err.message, 'error'); }
  }

  // === Item DnD ===
  function handleItemConsider(catId, e) { itemGroups[catId] = e.detail.items; }
  async function handleItemFinalize(catId, e) {
    snapshotCategoryMap();
    const grp = e.detail.items; itemGroups[catId] = grp;
    const all = [];
    for (const cat of sortedCats) { const g = cat.id === catId ? grp : (itemGroups[cat.id]||[]); g.forEach((it,i) => all.push({...it, category_id: cat.id, sort_order:(i+1)*10})); }
    uncatItems.forEach((it,i) => all.push({...it, category_id: null, sort_order:(i+1)*10}));
    items = all;
    try {
      for (const item of grp) { if (originalCategoryMap[item.id] !== catId) await api.patch('/lists/'+params.id+'/items/'+item.id, { category_id: catId||'' }); }
      await api.patch('/lists/'+params.id+'/items/reorder', { item_ids: grp.map(i=>i.id) });
    } catch (err) { showToast(err.message, 'error'); }
    snapshotCategoryMap();
  }
  function handleUncatConsider(e) { uncatItems = e.detail.items; }
  async function handleUncatFinalize(e) {
    snapshotCategoryMap();
    const grp = e.detail.items; uncatItems = grp;
    const all = [];
    for (const cat of sortedCats) { (itemGroups[cat.id]||[]).forEach((it,i) => all.push({...it, category_id: cat.id, sort_order:(i+1)*10})); }
    grp.forEach((it,i) => all.push({...it, category_id: null, sort_order:(i+1)*10}));
    items = all;
    try {
      for (const item of grp) { if (originalCategoryMap[item.id]) await api.patch('/lists/'+params.id+'/items/'+item.id, { category_id: '' }); }
      await api.patch('/lists/'+params.id+'/items/reorder', { item_ids: grp.map(i=>i.id) });
    } catch (err) { showToast(err.message, 'error'); }
    snapshotCategoryMap();
  }

  // === Actions ===
  async function addItem(e) {
    e.preventDefault(); if (!newItemName.trim()) return; addingItem = true;
    try {
      const item = await api.post('/lists/'+params.id+'/items', { name: newItemName.trim(), quantity: newItemQty.trim()||null });
      items = [...items, item]; rebuildGroups(); snapshotCategoryMap(); newItemName = ''; newItemQty = '';
    } catch (err) { showToast(err.message, 'error'); } finally { addingItem = false; }
  }
  async function toggleCheck(item) {
    try { const u = await api.patch('/lists/'+params.id+'/items/'+item.id+'/check'); items = items.map(i => i.id===u.id?u:i); rebuildGroups(); }
    catch (err) { showToast(err.message, 'error'); }
  }
  async function deleteItem(itemId) {
    try { await api.delete('/lists/'+params.id+'/items/'+itemId); items = items.filter(i=>i.id!==itemId); rebuildGroups(); snapshotCategoryMap(); }
    catch (err) { showToast(err.message, 'error'); }
  }
  async function clearAllItems() {
    if (!confirm($t('list.clear.items.confirm'))) return;
    try { await api.delete('/lists/'+params.id+'/items'); items=[]; rebuildGroups(); snapshotCategoryMap(); showToast($t('list.clear.items'),'success'); }
    catch (err) { showToast(err.message, 'error'); }
  }
  function openAddCategory() { showAddCategory = true; newCatName = ''; setTimeout(() => catInput?.focus(), 50); }
  async function addCategory(e) {
    e.preventDefault(); if (!newCatName.trim()) return; addingCat = true;
    try { const cat = await api.post('/lists/'+params.id+'/categories', { name: newCatName.trim() }); categories=[...categories,cat]; rebuildGroups(); newCatName=''; showAddCategory=false; }
    catch (err) { showToast(err.message, 'error'); } finally { addingCat = false; }
  }
  async function deleteCategory(catId) {
    if (!confirm($t('category.delete.confirm'))) return;
    try { await api.delete('/lists/'+params.id+'/categories/'+catId); categories=categories.filter(c=>c.id!==catId); items=items.map(i=>i.category_id===catId?{...i,category_id:null}:i); rebuildGroups(); snapshotCategoryMap(); }
    catch (err) { showToast(err.message, 'error'); }
  }
  function startRenameCategory(cat) { renamingCatId = cat.id; renameCatValue = cat.name; setTimeout(() => renameInput?.focus(), 50); }
  async function submitRenameCategory(e) {
    e.preventDefault(); if (!renameCatValue.trim()||!renamingCatId) return;
    try { const u = await api.patch('/lists/'+params.id+'/categories/'+renamingCatId, { name: renameCatValue.trim() }); categories=categories.map(c=>c.id===renamingCatId?{...c,name:u.name}:c); rebuildGroups(); renamingCatId=null; }
    catch (err) { showToast(err.message, 'error'); }
  }
  function cancelRename() { renamingCatId = null; }

  // === Category picker for items ===
  async function changeCategory(itemId, newCatId) {
    categoryPickerItemId = null;
    try {
      await api.patch('/lists/'+params.id+'/items/'+itemId, { category_id: newCatId||'' });
      items = items.map(i => i.id===itemId ? {...i, category_id: newCatId||null} : i);
      rebuildGroups(); snapshotCategoryMap();
    } catch (err) { showToast(err.message, 'error'); }
  }

  // === Photo ===
  async function compressImage(file, maxWidth = 800, quality = 0.7) {
    return new Promise((resolve) => {
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement('canvas');
        let w = img.width, h = img.height;
        if (w > maxWidth) { h = Math.round(h * maxWidth / w); w = maxWidth; }
        canvas.width = w; canvas.height = h;
        canvas.getContext('2d').drawImage(img, 0, 0, w, h);
        canvas.toBlob((blob) => resolve(blob), 'image/jpeg', quality);
      };
      img.src = URL.createObjectURL(file);
    });
  }
  function openPhotoMenu(itemId) { photoMenuItemId = itemId; }
  async function doUpload(useCamera) {
    const itemId = photoMenuItemId; photoMenuItemId = null;
    const input = document.createElement('input');
    input.type = 'file'; input.accept = 'image/*';
    if (useCamera) input.capture = 'environment';
    input.onchange = async () => {
      const file = input.files[0]; if (!file) return;
      const compressed = await compressImage(file);
      const formData = new FormData(); formData.append('file', compressed, 'photo.jpg');
      try {
        const token = localStorage.getItem('access_token');
        const res = await fetch('/api/v1/lists/'+params.id+'/items/'+itemId+'/image', { method:'POST', headers:{'Authorization':'Bearer '+token}, body:formData });
        if (!res.ok) throw new Error('Upload failed');
        const data = await res.json();
        items = items.map(i => i.id===itemId ? {...i, image_url: data.image_url} : i); rebuildGroups();
      } catch (err) { showToast(err.message, 'error'); }
    };
    input.click();
  }
  async function removePhoto(itemId) {
    viewingImage = null;
    try { await api.delete('/lists/'+params.id+'/items/'+itemId+'/image'); items=items.map(i=>i.id===itemId?{...i,image_url:null}:i); rebuildGroups(); }
    catch (err) { showToast(err.message, 'error'); }
  }

  // === AI hints ===
  async function saveHints() {
    savingHints = true;
    try { await api.post('/lists/'+params.id+'/save-hints'); showToast($t('sort.save.hints.done'),'success'); }
    catch (err) { showToast(err.message, 'error'); } finally { savingHints = false; }
  }


  // Svelte action: blocks dndzone from capturing non-handle pointer events
  function dndHandleOnly(node) {
    function guard(e) {
      if (!e.target.closest('.drag-handle')) {
        e.stopImmediatePropagation();
        e.stopPropagation();
      }
    }
    // Block ALL event types that DnD libraries might use
    node.addEventListener('pointerdown', guard, { capture: true });
    node.addEventListener('touchstart', guard, { capture: true });
    node.addEventListener('mousedown', guard, { capture: true });
    return {
      destroy() {
        node.removeEventListener('pointerdown', guard, { capture: true });
        node.removeEventListener('touchstart', guard, { capture: true });
        node.removeEventListener('mousedown', guard, { capture: true });
      }
    };
  }
  function handleAutoSortApplied(assignments) {
    for (const a of assignments) items = items.map(i => i.id===a.item_id ? {...i, category_id:a.category_id} : i);
    rebuildGroups(); snapshotCategoryMap(); showAutoSort = false; showToast('Items sorted!','success');
  }
</script>

<svelte:head>
  <style>
    .drag-handle { touch-action: none; cursor: grab; padding: 8px 4px; user-select: none; }
  </style>
</svelte:head>

<Navbar />

{#if loading}
  <div class="text-center text-gray-400 py-12">Loading...</div>
{:else if list}
  <main class="max-w-lg mx-auto px-4 py-4 pb-32">
    <!-- Header -->
    <div class="flex items-center justify-between mb-4">
      <div class="flex items-center gap-2">
        <a href="#/" class="btn-icon" aria-label="Back">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M9.707 16.707a1 1 0 01-1.414 0l-6-6a1 1 0 010-1.414l6-6a1 1 0 011.414 1.414L5.414 9H17a1 1 0 110 2H5.414l4.293 4.293a1 1 0 010 1.414z" clip-rule="evenodd" /></svg>
        </a>
        <h1 class="text-xl font-bold">{list.name}</h1>
      </div>
      <div class="flex items-center gap-1">
        {#if items.length > 0}
          <button onclick={clearAllItems} class="btn-icon text-red-400" title={$t('list.clear.items')}>
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clip-rule="evenodd" /></svg>
          </button>
        {/if}
        <button onclick={openAddCategory} class="btn-icon text-green-500" title={$t('category.new')}>
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" /><path stroke="white" stroke-width="1.5" stroke-linecap="round" d="M10 9v4M8 11h4" /></svg>
        </button>
        <button onclick={saveHints} disabled={savingHints} class="btn-icon text-amber-500" title={$t('sort.save.hints')}>
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" /></svg>
        </button>
        <button onclick={() => showAutoSort = true} class="btn-icon text-purple-500" title={$t('sort.auto')}>
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path d="M5 12a1 1 0 102 0V6.414l1.293 1.293a1 1 0 001.414-1.414l-3-3a1 1 0 00-1.414 0l-3 3a1 1 0 001.414 1.414L5 6.414V12zM15 8a1 1 0 10-2 0v5.586l-1.293-1.293a1 1 0 00-1.414 1.414l3 3a1 1 0 001.414 0l3-3a1 1 0 00-1.414-1.414L15 13.586V8z" /></svg>
        </button>
        {#if list.is_owner}
          <button onclick={() => showShare = true} class="btn-icon text-blue-500" title={$t('list.share')}>
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path d="M15 8a3 3 0 10-2.977-2.63l-4.94 2.47a3 3 0 100 4.319l4.94 2.47a3 3 0 10.895-1.789l-4.94-2.47a3.027 3.027 0 000-.74l4.94-2.47C13.456 7.68 14.19 8 15 8z" /></svg>
          </button>
        {/if}
      </div>
    </div>

    {#if showAddCategory}
      <form onsubmit={addCategory} class="card mb-4 flex gap-2 items-center border-green-200 border-2">
        <input bind:this={catInput} type="text" bind:value={newCatName} placeholder={$t('category.new.placeholder')} class="input-field flex-1 text-sm" />
        <button type="submit" disabled={addingCat} class="btn-primary text-sm px-3 py-1.5">OK</button>
        <button type="button" onclick={() => showAddCategory = false} class="btn-icon p-1 text-gray-400" aria-label="Cancel">
          <svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" /></svg>
        </button>
      </form>
    {/if}

    {#if shares.length > 0}
      <div class="flex flex-wrap gap-2 mb-4 text-xs">
        {#if currentUser}<span class="flex items-center gap-1"><span class="w-3 h-3 rounded-full inline-block" style="background-color: {currentUser.color}"></span>{currentUser.display_name}</span>{/if}
        {#if list && !list.is_owner && list.owner_display_name}<span class="flex items-center gap-1"><span class="w-3 h-3 rounded-full inline-block" style="background-color: {list.owner_color}"></span>{list.owner_display_name}</span>{/if}
        {#each shares.filter(s => !currentUser || s.user_id !== currentUser.id) as share}<span class="flex items-center gap-1"><span class="w-3 h-3 rounded-full inline-block" style="background-color: {share.user_color}"></span>{share.user_display_name}</span>{/each}
      </div>
    {/if}

    <form onsubmit={addItem} class="flex gap-2 mb-6">
      <input type="text" bind:value={newItemName} placeholder={$t('item.add.placeholder')} class="input-field flex-1" />
      <input type="text" bind:value={newItemQty} placeholder={$t('item.quantity.placeholder')} class="input-field w-20" />
      <button type="submit" disabled={addingItem} class="btn-primary whitespace-nowrap">+</button>
    </form>

    <!-- Uncategorized items -->
    {#if uncatItems.length > 0}
      <div class="mb-4">
        <h3 class="text-sm font-semibold text-gray-400 italic mb-2 px-1">{$t('item.uncategorized')}</h3>
        <div use:dndHandleOnly use:dndzone={{ items: uncatItems, flipDurationMs, type: 'items' }} onconsider={(e) => handleUncatConsider(e)} onfinalize={(e) => handleUncatFinalize(e)} class="min-h-[2.5rem]">
          {#each uncatItems as item (item.id)}
            {@render itemRow(item)}
          {/each}
        </div>
      </div>
    {/if}

    <!-- Categories -->
    {#if sortedCats.length > 0}
      <div use:dndHandleOnly use:dndzone={{ items: sortedCats, flipDurationMs, type: 'categories' }} onconsider={(e) => handleCatConsider(e)} onfinalize={(e) => handleCatFinalize(e)} class="space-y-4">
        {#each sortedCats as cat (cat.id)}
          <div class="bg-gray-50 rounded-xl p-3 border border-gray-100">
            <div>
              {#if renamingCatId === cat.id}
                <form onsubmit={submitRenameCategory} class="flex gap-2 items-center mb-2">
                  <input bind:this={renameInput} type="text" bind:value={renameCatValue} class="input-field flex-1 text-sm" />
                  <button type="submit" class="btn-primary text-sm px-3 py-1.5">OK</button>
                  <button type="button" onclick={cancelRename} class="btn-icon p-1 text-gray-400" aria-label="Cancel">
                    <svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" /></svg>
                  </button>
                </form>
              {:else}
                <div class="flex items-center justify-between mb-2">
                  <h3 class="text-sm font-semibold text-gray-600 uppercase tracking-wide flex items-center gap-2">
                    <span class="text-gray-300 drag-handle text-lg">&#x2630;</span>
                    {cat.name}
                    <span class="text-gray-300 font-normal text-xs">({(itemGroups[cat.id]||[]).length})</span>
                  </h3>
                  <div class="flex items-center gap-0.5">
                    <button onclick={() => startRenameCategory(cat)} class="btn-icon p-1 text-gray-400" aria-label="Rename" title={$t('category.rename')}>
                      <svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor"><path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793L3 14.172V17h2.828l8.38-8.379-2.83-2.828z" /></svg>
                    </button>
                    <button onclick={() => deleteCategory(cat.id)} class="btn-icon p-1 text-red-400" aria-label="Delete">
                      <svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" /></svg>
                    </button>
                  </div>
                </div>
              {/if}

              <div use:dndHandleOnly use:dndzone={{ items: itemGroups[cat.id]||[], flipDurationMs, type: 'items' }} onconsider={(e) => handleItemConsider(cat.id, e)} onfinalize={(e) => handleItemFinalize(cat.id, e)} class="min-h-[2.5rem]">
                {#each (itemGroups[cat.id]||[]) as item (item.id)}
                  {@render itemRow(item)}
                {/each}
              </div>
              {#if (itemGroups[cat.id]||[]).length === 0}
                <div class="text-center text-gray-300 text-sm py-3 border border-dashed border-gray-200 rounded-lg">—</div>
              {/if}
            </div>
          </div>
        {/each}
      </div>
    {/if}

    {#if items.length === 0 && categories.length === 0}
      <div class="text-center text-gray-400 py-12">{$t('sort.auto.no.items')}</div>
    {/if}
  </main>

  <!-- Photo action sheet -->
  {#if photoMenuItemId}
    <div class="fixed inset-0 bg-black/40 z-50 flex items-end justify-center" role="dialog" onclick={() => photoMenuItemId = null}>
      <div class="bg-white rounded-t-2xl w-full max-w-md p-4 pb-8 space-y-2" onclick={(e) => e.stopPropagation()}>
        <button onclick={() => doUpload(true)} class="w-full py-3 text-center rounded-xl bg-blue-50 text-blue-600 font-medium flex items-center justify-center gap-2">
          <svg class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M4 5a2 2 0 00-2 2v8a2 2 0 002 2h12a2 2 0 002-2V7a2 2 0 00-2-2h-1.586a1 1 0 01-.707-.293l-1.121-1.121A2 2 0 0011.172 3H8.828a2 2 0 00-1.414.586L6.293 4.707A1 1 0 015.586 5H4zm6 9a3 3 0 100-6 3 3 0 000 6z" clip-rule="evenodd" /></svg>
          {$t('item.photo.camera')}
        </button>
        <button onclick={() => doUpload(false)} class="w-full py-3 text-center rounded-xl bg-gray-50 text-gray-700 font-medium flex items-center justify-center gap-2">
          <svg class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M4 3a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V5a2 2 0 00-2-2H4zm12 12H4l4-8 3 6 2-4 3 6z" clip-rule="evenodd" /></svg>
          {$t('item.photo.gallery')}
        </button>
        <button onclick={() => photoMenuItemId = null} class="w-full py-3 text-center rounded-xl text-gray-400">{$t('btn.cancel')}</button>
      </div>
    </div>
  {/if}

  <!-- Image viewer -->
  {#if viewingImage}
    <div class="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4" role="dialog" onclick={() => viewingImage = null}>
      <div class="relative max-w-lg w-full" onclick={(e) => e.stopPropagation()}>
        <img src={viewingImage.url} alt={viewingImage.name} class="w-full rounded-xl" />
        <div class="flex gap-2 mt-3 justify-center">
          <button onclick={() => { openPhotoMenu(viewingImage.itemId); viewingImage = null; }} class="bg-white/20 text-white px-4 py-2 rounded-lg text-sm">{$t('item.photo')}</button>
          <button onclick={() => removePhoto(viewingImage.itemId)} class="bg-red-500/80 text-white px-4 py-2 rounded-lg text-sm">{$t('item.photo.remove')}</button>
          <button onclick={() => viewingImage = null} class="bg-white/20 text-white px-4 py-2 rounded-lg text-sm">{$t('btn.close')}</button>
        </div>
      </div>
    </div>
  {/if}

  <!-- Category picker -->
  {#if categoryPickerItemId}
    <div class="fixed inset-0 bg-black/40 z-50 flex items-end justify-center" role="dialog" onclick={() => categoryPickerItemId = null}>
      <div class="bg-white rounded-t-2xl w-full max-w-md p-4 pb-8" onclick={(e) => e.stopPropagation()}>
        <h3 class="text-sm font-medium text-gray-500 mb-3">{$t('category.new.placeholder')}</h3>
        <div class="space-y-1">
          <button onclick={() => changeCategory(categoryPickerItemId, '')} class="w-full text-left px-3 py-2.5 rounded-lg hover:bg-gray-50 text-gray-500 italic">— {$t('item.uncategorized')}</button>
          {#each sortedCats as cat}
            <button onclick={() => changeCategory(categoryPickerItemId, cat.id)} class="w-full text-left px-3 py-2.5 rounded-lg hover:bg-gray-50 font-medium">{cat.name}</button>
          {/each}
        </div>
        <button onclick={() => categoryPickerItemId = null} class="w-full mt-3 py-2 text-center text-gray-400 text-sm">{$t('btn.cancel')}</button>
      </div>
    </div>
  {/if}

  {#if showShare}
    <ShareDialog listId={params.id} bind:shares onClose={() => showShare = false} />
  {/if}
  {#if showAutoSort}
    <AutoSortDialog listId={params.id} categories={sortedCats} onApply={handleAutoSortApplied} onClose={() => showAutoSort = false} />
  {/if}
{/if}

<!-- Shared item row snippet -->
{#snippet itemRow(item)}
  <div class="card mb-2 flex items-center gap-0 py-2 {item.checked ? 'opacity-60' : ''}" style="border-left: 4px solid {item.added_by_color}">
    <!-- Drag handle: far left, ONLY element that triggers DnD -->
    <span class="text-gray-300 drag-handle text-lg flex-shrink-0" aria-label="Drag">&#x2630;</span>
    <!-- All other content: interactive but won't trigger drag -->
    <div class="flex items-center gap-2 flex-1 min-w-0">
      <button onclick={() => toggleCheck(item)} class="flex-shrink-0">
        <div class="w-6 h-6 rounded-full border-2 flex items-center justify-center transition-colors {item.checked ? 'bg-green-500 border-green-500' : 'border-gray-300'}">
          {#if item.checked}<svg class="h-4 w-4 text-white" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd" /></svg>{/if}
        </div>
      </button>
      {#if item.image_url}
        <button onclick={() => viewingImage = { url: item.image_url, name: item.name, itemId: item.id }} class="flex-shrink-0">
          <img src={item.image_url} alt="" class="w-8 h-8 rounded object-cover border border-gray-200" />
        </button>
      {/if}
      <div class="flex-1 min-w-0">
        <span class={item.checked ? 'line-through text-gray-400' : ''}>{item.name}</span>
        {#if item.quantity}<span class="text-xs text-gray-400 ml-1">({item.quantity})</span>{/if}
      </div>
      <div class="flex items-center gap-0.5 flex-shrink-0">
        {#if !item.image_url}
          <button onclick={() => openPhotoMenu(item.id)} class="btn-icon p-1 text-gray-300" aria-label="Photo">
            <svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M4 5a2 2 0 00-2 2v8a2 2 0 002 2h12a2 2 0 002-2V7a2 2 0 00-2-2h-1.586a1 1 0 01-.707-.293l-1.121-1.121A2 2 0 0011.172 3H8.828a2 2 0 00-1.414.586L6.293 4.707A1 1 0 015.586 5H4zm6 9a3 3 0 100-6 3 3 0 000 6z" clip-rule="evenodd" /></svg>
          </button>
        {/if}
        <button onclick={() => categoryPickerItemId = item.id} class="btn-icon p-1 text-gray-300" aria-label="Category">
          <svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor"><path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" /></svg>
        </button>
        <button onclick={() => deleteItem(item.id)} class="btn-icon p-1 text-red-400" aria-label="Delete">
          <svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" /></svg>
        </button>
      </div>
    </div>
  </div>
{/snippet}
