<script>
  import { t } from '../lib/i18n.js';
  import { api } from '../lib/api.js';
  import { showToast } from '../lib/store.js';

  let { listId, shares = $bindable([]), onClose } = $props();

  let email = $state('');
  let permission = $state('edit');
  let loading = $state(false);

  async function addShare(e) {
    e.preventDefault();
    if (!email.trim()) return;
    loading = true;
    try {
      const share = await api.post('/lists/' + listId + '/shares', { email: email.trim(), permission });
      shares = [...shares, share];
      email = '';
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      loading = false;
    }
  }

  async function removeShare(shareId) {
    try {
      await api.delete('/lists/' + listId + '/shares/' + shareId);
      shares = shares.filter(s => s.id !== shareId);
    } catch (err) {
      showToast(err.message, 'error');
    }
  }
</script>

<div class="fixed inset-0 bg-black/50 z-50 flex items-end sm:items-center justify-center" onclick={onClose}>
  <div class="bg-white rounded-t-2xl sm:rounded-2xl w-full max-w-md p-6 max-h-[80vh] overflow-y-auto" onclick={(e) => e.stopPropagation()}>
    <div class="flex justify-between items-center mb-4">
      <h2 class="text-lg font-bold">{$t('list.share')}</h2>
      <button onclick={onClose} class="btn-icon">&times;</button>
    </div>

    <form onsubmit={addShare} class="space-y-3 mb-6">
      <input type="email" bind:value={email} placeholder={$t('share.email.placeholder')} class="input-field" />
      <div class="flex gap-2">
        <select bind:value={permission} class="input-field flex-1">
          <option value="edit">{$t('share.permission.edit')}</option>
          <option value="view">{$t('share.permission.view')}</option>
        </select>
        <button type="submit" disabled={loading} class="btn-primary">{$t('share.invite')}</button>
      </div>
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
            <div class="flex items-center gap-2">
              <span class="text-xs text-gray-400">{share.permission}</span>
              <button onclick={() => removeShare(share.id)} class="text-red-400 hover:text-red-600 text-sm">
                {$t('share.remove')}
              </button>
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </div>
</div>
