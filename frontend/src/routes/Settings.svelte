<script>
  import { onMount } from 'svelte';
  import { t, locale, availableLocales } from '../lib/i18n.js';
  import { getProfile, updateProfile, logout } from '../lib/auth.js';
  import { api } from '../lib/api.js';
  import { user, showToast } from '../lib/store.js';
  import Navbar from '../components/Navbar.svelte';

  let displayName = $state('');
  let color = $state('#4A90D9');
  let saving = $state(false);
  let wipingHints = $state(false);

  // Password change
  let currentPassword = $state('');
  let newPassword = $state('');
  let confirmPassword = $state('');
  let changingPassword = $state(false);

  // Account deletion — 'idle' → 'confirming' → 'awaiting_code'
  let deleteState = $state('idle');
  let deleteCode = $state('');
  let deletePassword = $state('');
  let sendingDeleteRequest = $state(false);
  let confirmingDelete = $state(false);

  function startDeleteFlow() {
    deleteState = 'confirming';
  }

  async function requestDeleteCode() {
    if (confirmingDelete) return;
    sendingDeleteRequest = true;
    try {
      await api.post('/auth/me/delete/request', {});
      deleteState = 'awaiting_code';
      deleteCode = '';
      deletePassword = '';
      showToast($t('settings.delete.code.sent'), 'success');
    } catch (err) {
      showToast(err.message || $t('error.generic'), 'error');
      deleteState = 'idle';
    } finally {
      sendingDeleteRequest = false;
    }
  }

  async function confirmDelete() {
    const code = (deleteCode || '').trim();
    const password = deletePassword || '';
    if (!/^\d{6}$/.test(code)) {
      showToast($t('settings.delete.code.invalid'), 'error');
      return;
    }
    if (!password) {
      showToast($t('auth.password.current'), 'error');
      return;
    }
    confirmingDelete = true;
    try {
      await api.post('/auth/me/delete/confirm', { code, current_password: password });
      // Tokens are now useless — force logout + redirect to login.
      try { logout(); } catch (_) { window.location.hash = '#/login'; }
    } catch (err) {
      showToast(err.message || $t('error.generic'), 'error');
    } finally {
      confirmingDelete = false;
      deletePassword = '';
    }
  }

  function cancelDelete() {
    deleteState = 'idle';
    deleteCode = '';
    deletePassword = '';
  }

  async function handleChangePassword(e) {
    e.preventDefault();
    if (newPassword !== confirmPassword) {
      showToast($t('auth.password.mismatch'), 'error');
      return;
    }
    if (newPassword.length < 8) {
      showToast($t('auth.password.too.short'), 'error');
      return;
    }
    changingPassword = true;
    try {
      await api.post('/auth/me/password', {
        current_password: currentPassword,
        new_password: newPassword,
      });
      currentPassword = '';
      newPassword = '';
      confirmPassword = '';
      showToast($t('auth.password.changed'), 'success');
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      changingPassword = false;
    }
  }

  onMount(async () => {
    try {
      const profile = await getProfile();
      user.set(profile);
      displayName = profile.display_name;
      color = profile.color;
      locale.set(profile.locale);
    } catch (err) {
      showToast(err.message, 'error');
    }
  });

  async function handleSave(e) {
    e.preventDefault();
    saving = true;
    try {
      const updated = await updateProfile({
        display_name: displayName,
        color: color,
        locale: $locale,
      });
      user.set(updated);
      showToast($t('settings.saved'), 'success');
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      saving = false;
    }
  }

  async function wipeHints() {
    if (!confirm($t('settings.hints.wipe.confirm'))) return;
    wipingHints = true;
    try {
      const result = await api.delete('/auth/me/hints');
      showToast($t('settings.hints.wiped'), 'success');
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      wipingHints = false;
    }
  }

  const colors = ['#4A90D9', '#E74C3C', '#2ECC71', '#F39C12', '#9B59B6', '#1ABC9C', '#E91E63', '#FF9800'];
</script>

<Navbar />

<main class="max-w-lg mx-auto px-4 py-6">
  <h1 class="text-xl font-bold mb-6">{$t('settings.title')}</h1>

  <form onsubmit={handleSave} class="space-y-6">
    <div>
      <label for="name" class="block text-sm font-medium text-gray-700 mb-1">{$t('settings.display.name')}</label>
      <input id="name" type="text" bind:value={displayName} class="input-field" />
    </div>

    <div>
      <span class="block text-sm font-medium text-gray-700 mb-2">{$t('settings.language')}</span>
      <div class="flex gap-2">
        {#each availableLocales as loc}
          <button
            type="button"
            onclick={() => locale.set(loc.code)}
            class="px-4 py-2 rounded-lg border transition-colors
              {$locale === loc.code ? 'border-blue-500 bg-blue-50 text-blue-600' : 'border-gray-200 hover:border-gray-300'}"
          >
            {loc.name}
          </button>
        {/each}
      </div>
    </div>

    <div>
      <span class="block text-sm font-medium text-gray-700 mb-2">{$t('settings.color')}</span>
      <div class="flex gap-2 flex-wrap">
        {#each colors as c}
          <button
            type="button"
            onclick={() => color = c}
            aria-label="Select color"
            class="w-8 h-8 rounded-full border-2 transition-transform
              {color === c ? 'border-gray-800 scale-110' : 'border-transparent hover:scale-105'}"
            style="background-color: {c}"
          ></button>
        {/each}
        <input type="color" bind:value={color} class="w-8 h-8 rounded-full cursor-pointer border-0 p-0" />
      </div>
    </div>

    <button type="submit" disabled={saving} class="btn-primary w-full">
      {saving ? '...' : $t('btn.save')}
    </button>
  </form>

  <!-- Change password -->
  <div class="mt-8 pt-6 border-t border-gray-200">
    <h2 class="text-sm font-semibold text-gray-600 mb-3">{$t('settings.password.title')}</h2>
    <form onsubmit={handleChangePassword} class="space-y-3">
      <div>
        <label for="cur-pw" class="block text-sm text-gray-700 mb-1">{$t('auth.password.current')}</label>
        <input id="cur-pw" type="password" autocomplete="current-password" bind:value={currentPassword} class="input-field" />
      </div>
      <div>
        <label for="new-pw" class="block text-sm text-gray-700 mb-1">{$t('auth.password.new')}</label>
        <input id="new-pw" type="password" autocomplete="new-password" bind:value={newPassword} minlength="8" class="input-field" />
      </div>
      <div>
        <label for="new-pw2" class="block text-sm text-gray-700 mb-1">{$t('auth.password.confirm.new')}</label>
        <input id="new-pw2" type="password" autocomplete="new-password" bind:value={confirmPassword} minlength="8" class="input-field" />
      </div>
      <button type="submit" disabled={changingPassword || !currentPassword || !newPassword || !confirmPassword} class="btn-primary w-full">
        {changingPassword ? '...' : $t('auth.password.change')}
      </button>
    </form>
  </div>

  <!-- AI Hints -->
  <div class="mt-8 pt-6 border-t border-gray-200">
    <h2 class="text-sm font-semibold text-gray-600 mb-2">{$t('settings.hints.title')}</h2>
    <p class="text-xs text-gray-400 mb-3">{$t('settings.hints.description')}</p>
    <button onclick={wipeHints} disabled={wipingHints} class="btn-danger">
      {wipingHints ? '...' : $t('settings.hints.wipe')}
    </button>
  </div>

  <!-- Delete account -->
  <div class="mt-8 pt-6 border-t border-red-200">
    <h2 class="text-sm font-semibold text-red-600 mb-2">{$t('settings.delete.title')}</h2>
    <p class="text-xs text-gray-500 mb-3">{$t('settings.delete.description')}</p>
    <button onclick={startDeleteFlow} class="btn-danger">
      {$t('settings.delete.button')}
    </button>
  </div>
</main>

<!-- Delete account: confirmation dialog -->
{#if deleteState === 'confirming'}
  <div class="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" role="dialog" onclick={cancelDelete}>
    <div class="bg-white rounded-2xl w-full max-w-md p-6" onclick={(e) => e.stopPropagation()}>
      <h3 class="text-lg font-bold text-red-600 mb-3">{$t('settings.delete.confirm.title')}</h3>
      <p class="text-sm text-gray-700 mb-2">{$t('settings.delete.confirm.warning')}</p>
      <ul class="text-xs text-gray-500 mb-4 list-disc pl-5 space-y-1">
        <li>{$t('settings.delete.confirm.bullet.lists')}</li>
        <li>{$t('settings.delete.confirm.bullet.shares')}</li>
        <li>{$t('settings.delete.confirm.bullet.cards')}</li>
        <li>{$t('settings.delete.confirm.bullet.photos')}</li>
      </ul>
      <p class="text-sm font-medium text-gray-700 mb-4">{$t('settings.delete.confirm.question')}</p>
      <div class="flex gap-2">
        <button onclick={cancelDelete} class="btn-secondary flex-1">{$t('btn.cancel')}</button>
        <button onclick={requestDeleteCode} disabled={sendingDeleteRequest} class="btn-danger flex-1">
          {sendingDeleteRequest ? '...' : $t('settings.delete.confirm.yes')}
        </button>
      </div>
    </div>
  </div>
{/if}

<!-- Delete account: enter code dialog -->
{#if deleteState === 'awaiting_code'}
  <div class="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" role="dialog">
    <div class="bg-white rounded-2xl w-full max-w-md p-6">
      <h3 class="text-lg font-bold text-red-600 mb-3">{$t('settings.delete.code.title')}</h3>
      <p class="text-sm text-gray-700 mb-4">{$t('settings.delete.code.instruction')}</p>
      <label for="del-code" class="block text-xs text-gray-500 mb-1">{$t('settings.delete.code.title')}</label>
      <input
        id="del-code"
        type="text"
        inputmode="numeric"
        pattern="[0-9]{'{6}'}"
        maxlength="6"
        autocomplete="one-time-code"
        bind:value={deleteCode}
        class="input-field text-center text-2xl tracking-[0.5em] font-mono mb-4"
        placeholder="______"
      />
      <label for="del-pw" class="block text-xs text-gray-500 mb-1">{$t('auth.password.current')}</label>
      <input
        id="del-pw"
        type="password"
        autocomplete="current-password"
        bind:value={deletePassword}
        class="input-field mb-4"
      />
      <div class="flex gap-2">
        <button onclick={cancelDelete} class="btn-secondary flex-1">{$t('btn.cancel')}</button>
        <button onclick={confirmDelete} disabled={confirmingDelete || deleteCode.length !== 6 || !deletePassword} class="btn-danger flex-1">
          {confirmingDelete ? '...' : $t('settings.delete.code.submit')}
        </button>
      </div>
      <button onclick={requestDeleteCode} disabled={sendingDeleteRequest || confirmingDelete} class="w-full mt-3 text-xs text-gray-500 underline disabled:opacity-50">
        {sendingDeleteRequest ? '...' : $t('settings.delete.code.resend')}
      </button>
    </div>
  </div>
{/if}
