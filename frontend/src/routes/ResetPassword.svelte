<script>
  import { t } from '../lib/i18n.js';
  import { resetPassword } from '../lib/auth.js';
  import { push } from 'svelte-spa-router';

  let { params } = $props();

  let password = $state('');
  let passwordConfirm = $state('');
  let loading = $state(false);
  let error = $state('');
  let success = $state(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (password !== passwordConfirm) {
      error = 'Passwords do not match';
      return;
    }
    loading = true;
    error = '';
    try {
      await resetPassword(params.token, password);
      success = true;
      setTimeout(() => push('/login'), 2000);
    } catch (err) {
      error = err.message;
    } finally {
      loading = false;
    }
  }
</script>

<div class="min-h-screen flex items-center justify-center px-4 bg-gradient-to-br from-blue-50 to-indigo-100">
  <div class="card w-full max-w-sm">
    <h1 class="text-xl font-bold text-center mb-4">{$t('auth.reset')}</h1>

    {#if success}
      <div class="bg-green-50 text-green-600 text-sm p-3 rounded-lg text-center">
        {$t('auth.reset.success')}
      </div>
    {:else}
      <form onsubmit={handleSubmit} class="space-y-4">
        {#if error}
          <div class="bg-red-50 text-red-600 text-sm p-3 rounded-lg">{error}</div>
        {/if}
        <div>
          <label for="password" class="block text-sm font-medium text-gray-700 mb-1">{$t('auth.reset.new')}</label>
          <input id="password" type="password" bind:value={password} required minlength="8" class="input-field" />
        </div>
        <div>
          <label for="password2" class="block text-sm font-medium text-gray-700 mb-1">{$t('auth.password.confirm')}</label>
          <input id="password2" type="password" bind:value={passwordConfirm} required minlength="8" class="input-field" />
        </div>
        <button type="submit" disabled={loading} class="btn-primary w-full">
          {loading ? '...' : $t('auth.reset')}
        </button>
      </form>
    {/if}
  </div>
</div>
