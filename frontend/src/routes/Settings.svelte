<script>
  import { onMount } from 'svelte';
  import { t, locale, availableLocales } from '../lib/i18n.js';
  import { getProfile, updateProfile } from '../lib/auth.js';
  import { api } from '../lib/api.js';
  import { user, showToast } from '../lib/store.js';
  import Navbar from '../components/Navbar.svelte';

  let displayName = $state('');
  let color = $state('#4A90D9');
  let saving = $state(false);
  let wipingHints = $state(false);

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

  <!-- AI Hints -->
  <div class="mt-8 pt-6 border-t border-gray-200">
    <h2 class="text-sm font-semibold text-gray-600 mb-2">{$t('settings.hints.title')}</h2>
    <p class="text-xs text-gray-400 mb-3">{$t('settings.hints.description')}</p>
    <button onclick={wipeHints} disabled={wipingHints} class="btn-danger">
      {wipingHints ? '...' : $t('settings.hints.wipe')}
    </button>
  </div>
</main>
