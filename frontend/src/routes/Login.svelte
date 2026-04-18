<script>
  import { t, locale, availableLocales } from '../lib/i18n.js';
  import { login } from '../lib/auth.js';
  import { push } from 'svelte-spa-router';
  import { showToast } from '../lib/store.js';

  let email = $state('');
  let password = $state('');
  let loading = $state(false);
  let error = $state('');

  async function handleLogin(e) {
    e.preventDefault();
    loading = true;
    error = '';
    try {
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
      <h1 class="text-2xl font-bold text-blue-600">🛒 {$t('app.title')}</h1>
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

      <button type="submit" disabled={loading} class="btn-primary w-full">
        {loading ? '...' : $t('auth.login')}
      </button>

      <div class="text-center text-sm space-y-2">
        <a href="#/forgot-password" class="text-blue-500 hover:underline block">{$t('auth.forgot')}</a>
        <p class="text-gray-500">
          {$t('auth.no.account')} <a href="#/register" class="text-blue-500 hover:underline">{$t('auth.register')}</a>
        </p>
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
