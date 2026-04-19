<script>
  import { onMount } from 'svelte';
  import { t, locale, availableLocales } from '../lib/i18n.js';
  import { login, setRememberMe } from '../lib/auth.js';
  import { push } from 'svelte-spa-router';
  import { showToast } from '../lib/store.js';

  let email = $state('');
  let password = $state('');
  let rememberMe = $state(true);
  let loading = $state(false);
  let error = $state('');
  // Hide signup link when the admin has disabled self-registration. Default
  // to true so a blip in the /config fetch never silently hides the link on
  // a fresh install.
  let registrationEnabled = $state(true);

  onMount(async () => {
    try {
      const r = await fetch('/api/v1/config');
      if (r.ok) {
        const cfg = await r.json();
        registrationEnabled = cfg.registration_enabled !== false;
      }
    } catch { /* network hiccup — keep the default */ }
  });

  async function handleLogin(e) {
    e.preventDefault();
    loading = true;
    error = '';
    try {
      setRememberMe(rememberMe);
      await login(email, password);
      push('/');
    } catch (err) {
      error = err.message;
    } finally {
      loading = false;
    }
  }
</script>

<div class="min-h-screen flex items-center justify-center px-4 bg-gradient-to-br from-blue-50 to-indigo-100">
  <div class="card w-full max-w-sm">
    <div class="text-center mb-6">
      <img src="/icons/logo.png" alt="3inkauf" class="w-20 h-20 mx-auto rounded-2xl shadow-sm mb-3" />
      <h1 class="text-2xl font-bold text-blue-600">3inkauf</h1>
    </div>

    <form onsubmit={handleLogin} class="space-y-4">
      {#if error}
        <div class="bg-red-50 text-red-600 text-sm p-3 rounded-lg">{error}</div>
      {/if}

      <div>
        <label for="email" class="block text-sm font-medium text-gray-700 mb-1">{$t('auth.email')}</label>
        <input id="email" type="email" bind:value={email} required class="input-field" autocomplete="email" />
      </div>

      <div>
        <label for="password" class="block text-sm font-medium text-gray-700 mb-1">{$t('auth.password')}</label>
        <input id="password" type="password" bind:value={password} required class="input-field" autocomplete="current-password" />
      </div>

      <label class="flex items-center gap-2 cursor-pointer">
        <input type="checkbox" bind:checked={rememberMe} class="w-4 h-4 rounded border-gray-300 text-blue-500 focus:ring-blue-500" />
        <span class="text-sm text-gray-600">{$t('auth.remember')}</span>
      </label>

      <button type="submit" disabled={loading} class="btn-primary w-full">
        {loading ? '...' : $t('auth.login')}
      </button>

      <div class="text-center text-sm space-y-2">
        <a href="#/forgot-password" class="text-blue-500 hover:underline block">{$t('auth.forgot')}</a>
        {#if registrationEnabled}
          <p class="text-gray-500">
            {$t('auth.no.account')} <a href="#/register" class="text-blue-500 hover:underline">{$t('auth.register')}</a>
          </p>
        {/if}
      </div>
    </form>

    <div class="mt-4 flex justify-center gap-2">
      {#each availableLocales as loc}
        <button
          onclick={() => locale.set(loc.code)}
          class="text-xs px-2 py-1 rounded {$locale === loc.code ? 'bg-blue-100 text-blue-600 font-medium' : 'text-gray-400 hover:text-gray-600'}"
        >
          {loc.name}
        </button>
      {/each}
    </div>
  </div>
</div>
