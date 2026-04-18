<script>
  import { t, locale, availableLocales } from '../lib/i18n.js';
  import { register } from '../lib/auth.js';
  import { push } from 'svelte-spa-router';

  let email = $state('');
  let password = $state('');
  let passwordConfirm = $state('');
  let displayName = $state('');
  let loading = $state(false);
  let error = $state('');

  async function handleRegister(e) {
    e.preventDefault();
    if (password !== passwordConfirm) {
      error = 'Passwords do not match';
      return;
    }
    loading = true;
    error = '';
    try {
      await register(email, password, displayName, $locale);
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
      <img src="/icons/logo.png" alt="3inkauf" class="w-16 h-16 mx-auto rounded-2xl shadow-sm mb-2" />
      <h1 class="text-2xl font-bold text-blue-600">3inkauf</h1>
      <p class="text-gray-500 text-sm mt-1">{$t('auth.register')}</p>
    </div>

    <form onsubmit={handleRegister} class="space-y-4">
      {#if error}
        <div class="bg-red-50 text-red-600 text-sm p-3 rounded-lg">{error}</div>
      {/if}

      <div>
        <label for="name" class="block text-sm font-medium text-gray-700 mb-1">{$t('auth.display.name')}</label>
        <input id="name" type="text" bind:value={displayName} required class="input-field" />
      </div>

      <div>
        <label for="email" class="block text-sm font-medium text-gray-700 mb-1">{$t('auth.email')}</label>
        <input id="email" type="email" bind:value={email} required class="input-field" autocomplete="email" />
      </div>

      <div>
        <label for="password" class="block text-sm font-medium text-gray-700 mb-1">{$t('auth.password')}</label>
        <input id="password" type="password" bind:value={password} required minlength="8" class="input-field" autocomplete="new-password" />
      </div>

      <div>
        <label for="password2" class="block text-sm font-medium text-gray-700 mb-1">{$t('auth.password.confirm')}</label>
        <input id="password2" type="password" bind:value={passwordConfirm} required minlength="8" class="input-field" autocomplete="new-password" />
      </div>

      <button type="submit" disabled={loading} class="btn-primary w-full">
        {loading ? '...' : $t('auth.register')}
      </button>

      <div class="text-center text-sm">
        <p class="text-gray-500">
          {$t('auth.has.account')} <a href="#/login" class="text-blue-500 hover:underline">{$t('auth.login')}</a>
        </p>
      </div>
    </form>
  </div>
</div>
