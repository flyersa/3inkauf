<script>
  import { t } from '../lib/i18n.js';
  import { forgotPassword } from '../lib/auth.js';

  let email = $state('');
  let loading = $state(false);
  let sent = $state(false);
  let error = $state('');

  async function handleSubmit(e) {
    e.preventDefault();
    loading = true;
    error = '';
    try {
      await forgotPassword(email);
      sent = true;
    } catch (err) {
      error = err.message;
    } finally {
      loading = false;
    }
  }
</script>

<div class="min-h-screen flex items-center justify-center px-4 bg-gradient-to-br from-blue-50 to-indigo-100">
  <div class="card w-full max-w-sm">
    <h1 class="text-xl font-bold text-center mb-4">{$t('auth.forgot')}</h1>

    {#if sent}
      <div class="bg-green-50 text-green-600 text-sm p-3 rounded-lg text-center">
        {$t('auth.reset.sent')}
      </div>
      <div class="mt-4 text-center">
        <a href="#/login" class="text-blue-500 hover:underline text-sm">{$t('auth.login')}</a>
      </div>
    {:else}
      <form onsubmit={handleSubmit} class="space-y-4">
        {#if error}
          <div class="bg-red-50 text-red-600 text-sm p-3 rounded-lg">{error}</div>
        {/if}
        <div>
          <label for="email" class="block text-sm font-medium text-gray-700 mb-1">{$t('auth.email')}</label>
          <input id="email" type="email" bind:value={email} required class="input-field" />
        </div>
        <button type="submit" disabled={loading} class="btn-primary w-full">
          {loading ? '...' : $t('auth.reset')}
        </button>
        <div class="text-center">
          <a href="#/login" class="text-blue-500 hover:underline text-sm">{$t('btn.back')}</a>
        </div>
      </form>
    {/if}
  </div>
</div>
