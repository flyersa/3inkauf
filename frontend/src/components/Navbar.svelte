<script>
  import { t, locale, availableLocales } from '../lib/i18n.js';
  import { logout } from '../lib/auth.js';
  import { user } from '../lib/store.js';

  let flagOpen = $state(false);
  let flagWrap = $state(null);

  function setLocale(code) {
    locale.set(code);
    flagOpen = false;
  }

  function handleDocClick(e) {
    if (flagOpen && flagWrap && !flagWrap.contains(e.target)) flagOpen = false;
  }
</script>

<svelte:window onclick={handleDocClick} />

{#snippet flag(code)}
  {#if code === 'de'}
    <svg viewBox="0 0 5 3" class="h-4 w-6 rounded-sm ring-1 ring-black/10 block" aria-hidden="true">
      <rect width="5" height="1" y="0" fill="#000"/>
      <rect width="5" height="1" y="1" fill="#DD0000"/>
      <rect width="5" height="1" y="2" fill="#FFCE00"/>
    </svg>
  {:else}
    <svg viewBox="0 0 60 30" class="h-4 w-6 rounded-sm ring-1 ring-black/10 block" aria-hidden="true">
      <rect width="60" height="30" fill="#012169"/>
      <path d="M0,0 L60,30 M60,0 L0,30" stroke="#fff" stroke-width="6"/>
      <path d="M0,0 L60,30" stroke="#C8102E" stroke-width="4" stroke-dasharray="33 60"/>
      <path d="M60,0 L0,30" stroke="#C8102E" stroke-width="4" stroke-dasharray="33 60" stroke-dashoffset="-33"/>
      <path d="M30,0 v30 M0,15 h60" stroke="#fff" stroke-width="10"/>
      <path d="M30,0 v30 M0,15 h60" stroke="#C8102E" stroke-width="6"/>
    </svg>
  {/if}
{/snippet}

<nav class="bg-white border-b border-gray-200 sticky top-0 z-40">
  <div class="max-w-lg mx-auto px-4 h-14 flex items-center justify-between">
    <a href="#/" class="flex items-center gap-2">
      <img src="/icons/logo.png" alt="3inkauf" class="h-8 w-8 rounded" />
      <span class="font-bold text-blue-600 text-lg">3inkauf</span>
    </a>
    <div class="flex items-center gap-2">
      <div bind:this={flagWrap} class="relative">
        <button
          type="button"
          onclick={() => flagOpen = !flagOpen}
          class="btn-icon flex items-center justify-center"
          aria-label="Language"
          aria-haspopup="true"
          aria-expanded={flagOpen}
        >
          {@render flag($locale)}
        </button>
        {#if flagOpen}
          <div class="absolute right-0 mt-1 bg-white border border-gray-200 rounded-md shadow-lg py-1 z-50 min-w-max">
            {#each availableLocales as loc}
              <button
                type="button"
                onclick={() => setLocale(loc.code)}
                class="flex items-center gap-2 px-3 py-1.5 text-xs w-full text-left hover:bg-gray-50 {$locale === loc.code ? 'bg-gray-50 font-medium' : ''}"
              >
                {@render flag(loc.code)}
                <span class="text-gray-700">{loc.name}</span>
              </button>
            {/each}
          </div>
        {/if}
      </div>
      <a href="#/bonus-cards" class="btn-icon" title={$t('bonus.title')}>
        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="2" y="5" width="20" height="14" rx="2" />
          <path d="M2 10h20" />
          <path d="M6 15h4" />
        </svg>
      </a>
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
