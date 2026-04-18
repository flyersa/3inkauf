<script>
  import { onMount } from 'svelte';
  import { t } from '../lib/i18n.js';
  import { api } from '../lib/api.js';
  import { showToast } from '../lib/store.js';
  import Navbar from '../components/Navbar.svelte';

  let cards = $state([]);
  let loading = $state(true);

  let showAdd = $state(false);
  let newName = $state('');
  let newDescription = $state('');
  let newPhotoFile = $state(null);
  let newPhotoPreview = $state(null);
  let adding = $state(false);

  let viewing = $state(null);
  let photoMenuCardId = $state(null);

  // Sharing
  let sharingCard = $state(null);
  let shareEmail = $state('');
  let shares = $state([]);
  let shareLoading = $state(false);

  onMount(async () => {
    try {
      cards = await api.get('/bonus-cards');
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      loading = false;
    }
  });

  async function compressImage(file, maxWidth = 1200, quality = 0.8) {
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

  function pickNewPhoto(useCamera) {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    if (useCamera) input.capture = 'environment';
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      const compressed = await compressImage(file);
      newPhotoFile = compressed;
      newPhotoPreview = URL.createObjectURL(compressed);
    };
    input.click();
  }

  async function uploadImageForCard(cardId, blob) {
    const token = localStorage.getItem('access_token') || sessionStorage.getItem('access_token');
    const fd = new FormData();
    fd.append('file', blob, 'photo.jpg');
    const res = await fetch('/api/v1/bonus-cards/' + cardId + '/image', {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + token },
      body: fd,
    });
    if (!res.ok) throw new Error('Image upload failed');
    return await res.json();
  }

  async function submitAdd(e) {
    e?.preventDefault();
    const name = newName.trim();
    if (!name) return;
    adding = true;
    try {
      const created = await api.post('/bonus-cards', {
        name,
        description: newDescription.trim() || null,
      });
      let finalCard = created;
      if (newPhotoFile) {
        finalCard = await uploadImageForCard(created.id, newPhotoFile);
      }
      cards = [...cards, finalCard];
      newName = '';
      newDescription = '';
      newPhotoFile = null;
      if (newPhotoPreview) URL.revokeObjectURL(newPhotoPreview);
      newPhotoPreview = null;
      showAdd = false;
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      adding = false;
    }
  }

  function cancelAdd() {
    newName = '';
    newDescription = '';
    newPhotoFile = null;
    if (newPhotoPreview) URL.revokeObjectURL(newPhotoPreview);
    newPhotoPreview = null;
    showAdd = false;
  }

  async function deleteCard(card) {
    if (!card.is_owner) return;
    if (!confirm($t('bonus.delete.confirm'))) return;
    try {
      await api.delete('/bonus-cards/' + card.id);
      cards = cards.filter(c => c.id !== card.id);
      if (viewing && viewing.id === card.id) viewing = null;
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  async function leaveCard(card) {
    if (card.is_owner) return;
    if (!confirm($t('bonus.leave.confirm'))) return;
    try {
      await api.delete('/bonus-cards/' + card.id + '/shares/me');
      cards = cards.filter(c => c.id !== card.id);
      if (viewing && viewing.id === card.id) viewing = null;
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  function replacePhoto(cardId, useCamera) {
    photoMenuCardId = null;
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    if (useCamera) input.capture = 'environment';
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      try {
        const compressed = await compressImage(file);
        const updated = await uploadImageForCard(cardId, compressed);
        cards = cards.map(c => c.id === cardId ? updated : c);
        if (viewing && viewing.id === cardId) viewing = updated;
      } catch (err) {
        showToast(err.message, 'error');
      }
    };
    input.click();
  }

  async function removePhoto(cardId) {
    try {
      const updated = await api.delete('/bonus-cards/' + cardId + '/image');
      if (updated) {
        cards = cards.map(c => c.id === cardId ? updated : c);
        if (viewing && viewing.id === cardId) viewing = updated;
      }
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  async function openShareDialog(card) {
    if (!card.is_owner) return;
    sharingCard = card;
    shareEmail = '';
    shares = [];
    try {
      shares = await api.get('/bonus-cards/' + card.id + '/shares');
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  function closeShareDialog() {
    sharingCard = null;
    shares = [];
    shareEmail = '';
  }

  async function addShare(e) {
    e?.preventDefault();
    const email = shareEmail.trim();
    if (!email || !sharingCard) return;
    shareLoading = true;
    try {
      const share = await api.post('/bonus-cards/' + sharingCard.id + '/shares', { email });
      shares = [...shares, share];
      shareEmail = '';
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      shareLoading = false;
    }
  }

  async function removeShare(shareId) {
    if (!sharingCard) return;
    try {
      await api.delete('/bonus-cards/' + sharingCard.id + '/shares/' + shareId);
      shares = shares.filter(s => s.id !== shareId);
    } catch (err) {
      showToast(err.message, 'error');
    }
  }
</script>

<Navbar />

<div class="max-w-lg mx-auto px-4 py-4">
  <div class="flex items-center justify-between mb-4">
    <h1 class="text-xl font-bold text-gray-800">{$t('bonus.title')}</h1>
    <button onclick={() => showAdd = true} class="btn-primary text-sm px-3 py-1.5">+ {$t('bonus.add')}</button>
  </div>

  {#if loading}
    <p class="text-gray-400 text-sm">…</p>
  {:else if cards.length === 0}
    <p class="text-gray-400 text-sm text-center py-12">{$t('bonus.empty')}</p>
  {:else}
    <div class="grid grid-cols-2 gap-3">
      {#each cards as card}
        <div class="card p-0 overflow-hidden relative">
          <button
            type="button"
            onclick={() => viewing = card}
            class="block w-full text-left"
          >
            {#if card.image_url}
              <img src={card.image_url} alt={card.name} class="w-full aspect-[4/3] object-cover bg-gray-100" />
            {:else}
              <div class="w-full aspect-[4/3] bg-gray-100 flex items-center justify-center text-gray-300">
                <svg class="h-10 w-10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <rect x="2" y="5" width="20" height="14" rx="2" />
                  <path d="M2 10h20" />
                </svg>
              </div>
            {/if}
            <div class="p-2">
              <div class="font-medium text-sm text-gray-800 truncate">{card.name}</div>
              {#if card.description}
                <div class="text-xs text-gray-500 truncate">{card.description}</div>
              {/if}
              {#if !card.is_owner}
                <div class="flex items-center gap-1 text-xs text-gray-400 mt-1">
                  <span class="w-2 h-2 rounded-full inline-block" style="background-color: {card.owner_color || '#999'}"></span>
                  <span class="truncate">{$t('bonus.shared.by')} {card.owner_display_name || '?'}</span>
                </div>
              {/if}
            </div>
          </button>
          {#if card.is_owner}
            <button
              type="button"
              onclick={() => openShareDialog(card)}
              class="absolute top-1 left-1 bg-black/40 text-white rounded-full w-6 h-6 flex items-center justify-center hover:bg-blue-500/80"
              aria-label={$t('bonus.share')}
              title={$t('bonus.share')}
            >
              <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="18" cy="5" r="3" />
                <circle cx="6" cy="12" r="3" />
                <circle cx="18" cy="19" r="3" />
                <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
                <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
              </svg>
            </button>
            <button
              type="button"
              onclick={() => deleteCard(card)}
              class="absolute top-1 right-1 bg-black/40 text-white rounded-full w-6 h-6 flex items-center justify-center hover:bg-red-500/80"
              aria-label={$t('btn.delete')}
              title={$t('btn.delete')}
            >
              <svg class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" /></svg>
            </button>
          {:else}
            <button
              type="button"
              onclick={() => leaveCard(card)}
              class="absolute top-1 right-1 bg-black/40 text-white rounded-full w-6 h-6 flex items-center justify-center hover:bg-red-500/80"
              aria-label={$t('bonus.leave')}
              title={$t('bonus.leave')}
            >
              <svg class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M3 3a1 1 0 011 1v12a1 1 0 11-2 0V4a1 1 0 011-1zm7.707 3.293a1 1 0 010 1.414L9.414 9H17a1 1 0 110 2H9.414l1.293 1.293a1 1 0 01-1.414 1.414l-3-3a1 1 0 010-1.414l3-3a1 1 0 011.414 0z" clip-rule="evenodd" /></svg>
            </button>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</div>

{#if showAdd}
  <div class="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" role="dialog">
    <form onsubmit={submitAdd} class="bg-white rounded-xl p-4 w-full max-w-sm space-y-3">
      <h2 class="text-lg font-bold">{$t('bonus.add')}</h2>
      <input type="text" bind:value={newName} placeholder={$t('bonus.name.placeholder')} class="input-field w-full" required />
      <textarea bind:value={newDescription} placeholder={$t('bonus.description.placeholder')} rows="2" class="input-field w-full resize-none"></textarea>

      {#if newPhotoPreview}
        <div class="relative">
          <img src={newPhotoPreview} alt="" class="w-full rounded-lg object-cover max-h-48" />
          <button
            type="button"
            onclick={() => { if (newPhotoPreview) URL.revokeObjectURL(newPhotoPreview); newPhotoFile = null; newPhotoPreview = null; }}
            class="absolute top-2 right-2 bg-black/60 text-white rounded-full w-7 h-7 flex items-center justify-center"
            aria-label={$t('btn.delete')}
          >
            <svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" /></svg>
          </button>
        </div>
      {:else}
        <div class="grid grid-cols-2 gap-2">
          <button type="button" onclick={() => pickNewPhoto(true)} class="btn-icon border border-gray-200 rounded-lg py-2 text-sm">{$t('item.photo.camera')}</button>
          <button type="button" onclick={() => pickNewPhoto(false)} class="btn-icon border border-gray-200 rounded-lg py-2 text-sm">{$t('item.photo.gallery')}</button>
        </div>
      {/if}

      <div class="flex gap-2 pt-2">
        <button type="button" onclick={cancelAdd} class="flex-1 py-2 rounded-lg border border-gray-200 text-sm">{$t('btn.cancel')}</button>
        <button type="submit" disabled={adding || !newName.trim()} class="flex-1 btn-primary text-sm">{$t('btn.save')}</button>
      </div>
    </form>
  </div>
{/if}

{#if viewing}
  <div class="fixed inset-0 bg-black/90 z-50 flex items-center justify-center p-4" role="dialog" onclick={() => viewing = null}>
    <div class="relative max-w-lg w-full" onclick={(e) => e.stopPropagation()}>
      {#if viewing.image_url}
        <img src={viewing.image_url} alt={viewing.name} class="w-full max-h-[70vh] object-contain rounded-lg bg-black" />
      {:else}
        <div class="w-full aspect-[4/3] bg-gray-800 rounded-lg flex items-center justify-center text-gray-500">
          <svg class="h-16 w-16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
            <rect x="2" y="5" width="20" height="14" rx="2" />
            <path d="M2 10h20" />
          </svg>
        </div>
      {/if}
      <div class="mt-3 text-white">
        <div class="font-bold text-lg">{viewing.name}</div>
        {#if viewing.description}<div class="text-sm text-gray-300 mt-1 whitespace-pre-wrap">{viewing.description}</div>{/if}
        {#if !viewing.is_owner}
          <div class="flex items-center gap-1 text-xs text-gray-400 mt-1">
            <span class="w-2 h-2 rounded-full inline-block" style="background-color: {viewing.owner_color || '#999'}"></span>
            <span>{$t('bonus.shared.by')} {viewing.owner_display_name || '?'}</span>
          </div>
        {/if}
      </div>
      <div class="flex flex-wrap gap-2 mt-3">
        {#if viewing.is_owner}
          <button onclick={() => photoMenuCardId = viewing.id} class="bg-white/20 text-white px-3 py-1.5 rounded-lg text-xs">{viewing.image_url ? $t('bonus.photo.replace') : $t('item.photo')}</button>
          {#if viewing.image_url}
            <button onclick={() => removePhoto(viewing.id)} class="bg-red-500/80 text-white px-3 py-1.5 rounded-lg text-xs">{$t('item.photo.remove')}</button>
          {/if}
          <button onclick={() => openShareDialog(viewing)} class="bg-blue-500/80 text-white px-3 py-1.5 rounded-lg text-xs">{$t('bonus.share')}</button>
        {:else}
          <button onclick={() => leaveCard(viewing)} class="bg-red-500/80 text-white px-3 py-1.5 rounded-lg text-xs">{$t('bonus.leave')}</button>
        {/if}
        <button onclick={() => viewing = null} class="ml-auto bg-white/10 text-white px-3 py-1.5 rounded-lg text-xs">{$t('btn.close')}</button>
      </div>
    </div>
  </div>
{/if}

{#if photoMenuCardId}
  <div class="fixed inset-0 bg-black/50 z-[60] flex items-end justify-center" role="dialog" onclick={() => photoMenuCardId = null}>
    <div class="bg-white w-full max-w-sm rounded-t-2xl p-3 space-y-2" onclick={(e) => e.stopPropagation()}>
      <button onclick={() => replacePhoto(photoMenuCardId, true)} class="w-full py-3 text-center rounded-xl bg-gray-50">{$t('item.photo.camera')}</button>
      <button onclick={() => replacePhoto(photoMenuCardId, false)} class="w-full py-3 text-center rounded-xl bg-gray-50">{$t('item.photo.gallery')}</button>
      <button onclick={() => photoMenuCardId = null} class="w-full py-3 text-center rounded-xl text-gray-400">{$t('btn.cancel')}</button>
    </div>
  </div>
{/if}

{#if sharingCard}
  <div class="fixed inset-0 bg-black/50 z-[70] flex items-end sm:items-center justify-center" role="dialog" onclick={closeShareDialog}>
    <div class="bg-white rounded-t-2xl sm:rounded-2xl w-full max-w-md p-6 max-h-[80vh] overflow-y-auto" onclick={(e) => e.stopPropagation()}>
      <div class="flex justify-between items-center mb-4">
        <h2 class="text-lg font-bold">{$t('bonus.share')}: {sharingCard.name}</h2>
        <button onclick={closeShareDialog} class="btn-icon">&times;</button>
      </div>

      <form onsubmit={addShare} class="flex gap-2 mb-4">
        <input type="email" bind:value={shareEmail} placeholder={$t('share.email.placeholder')} class="input-field flex-1" />
        <button type="submit" disabled={shareLoading || !shareEmail.trim()} class="btn-primary">{$t('share.invite')}</button>
      </form>

      {#if shares.length > 0}
        <div class="space-y-2">
          {#each shares as share (share.id)}
            <div class="flex items-center justify-between py-2 border-b border-gray-100">
              <div class="flex items-center gap-2">
                <span class="w-3 h-3 rounded-full" style="background-color: {share.user_color}"></span>
                <div>
                  <div class="text-sm font-medium">{share.user_display_name}</div>
                  <div class="text-xs text-gray-400">{share.user_email}</div>
                </div>
              </div>
              <button onclick={() => removeShare(share.id)} class="text-red-400 hover:text-red-600 text-sm">{$t('share.remove')}</button>
            </div>
          {/each}
        </div>
      {:else}
        <p class="text-xs text-gray-400 text-center py-4">{$t('bonus.share.empty')}</p>
      {/if}
    </div>
  </div>
{/if}
