<script>
  import { t, locale, availableLocales } from '../lib/i18n.js';
  import { logout } from '../lib/auth.js';
  import { user } from '../lib/store.js';
</script>

<nav class="bg-white border-b border-gray-200 sticky top-0 z-40">
  <div class="max-w-lg mx-auto px-4 h-14 flex items-center justify-between">
    <a href="#/" class="font-bold text-blue-600 text-lg">🛒 {$t('app.title')}</a>
    <div class="flex items-center gap-2">
      <select
        value={$locale}
        onchange={(e) => locale.set(e.target.value)}
        class="text-xs border-none bg-transparent text-gray-500 cursor-pointer"
      >
        {#each availableLocales as loc}
          <option value={loc.code}>{loc.name}</option>
        {/each}
      </select>
      <a href="#/settings" class="btn-icon" title={$t('nav.settings')}>
        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
          <path fill-rule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clip-rule="evenodd" />
        </svg>
      </a>
      <button onclick={logout} class="btn-icon text-red-400" title={$t('nav.logout')}>
        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
          <path fill-rule="evenodd" d="M3 3a1 1 0 00-1 1v12a1 1 0 102 0V4a1 1 0 00-1-1zm10.293 9.293a1 1 0 001.414 1.414l3-3a1 1 0 000-1.414l-3-3a1 1 0 10-1.414 1.414L14.586 9H7a1 1 0 100 2h7.586l-1.293 1.293z" clip-rule="evenodd" />
        </svg>
      </button>
    </div>
  </div>
</nav>
