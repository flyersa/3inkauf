<script>
  import Router from 'svelte-spa-router';
  import { wrap } from 'svelte-spa-router/wrap';
  import { isLoggedIn } from './lib/auth.js';
  import { t } from './lib/i18n.js';
  import { toastMessage } from './lib/store.js';

  import Login from './routes/Login.svelte';
  import Register from './routes/Register.svelte';
  import ForgotPassword from './routes/ForgotPassword.svelte';
  import ResetPassword from './routes/ResetPassword.svelte';
  import ListOverview from './routes/ListOverview.svelte';
  import ListDetail from './routes/ListDetail.svelte';
  import Settings from './routes/Settings.svelte';
  import BonusCards from './routes/BonusCards.svelte';
  import Admin from './routes/Admin.svelte';

  function authGuard() {
    if (!isLoggedIn()) {
      window.location.hash = '#/login';
      return false;
    }
    return true;
  }

  const routes = {
    '/login': Login,
    '/register': Register,
    '/forgot-password': ForgotPassword,
    '/reset-password/:token': ResetPassword,
    '/': wrap({ component: ListOverview, conditions: [authGuard] }),
    '/list/:id': wrap({ component: ListDetail, conditions: [authGuard] }),
    '/settings': wrap({ component: Settings, conditions: [authGuard] }),
    '/bonus-cards': wrap({ component: BonusCards, conditions: [authGuard] }),
    '/admin': Admin,
  };

  let online = $state(navigator.onLine);

  $effect(() => {
    const goOnline = () => online = true;
    const goOffline = () => online = false;
    window.addEventListener('online', goOnline);
    window.addEventListener('offline', goOffline);
    return () => {
      window.removeEventListener('online', goOnline);
      window.removeEventListener('offline', goOffline);
    };
  });
</script>

{#if !online}
  <div class="bg-amber-500 text-white text-center py-2 text-sm font-medium sticky top-0 z-50">
    {$t('offline.banner')}
  </div>
{/if}

{#if $toastMessage}
  <div class="fixed top-4 right-4 z-50 px-4 py-3 rounded-lg shadow-lg text-white text-sm font-medium transition-all
    {$toastMessage.type === 'error' ? 'bg-red-500' : $toastMessage.type === 'success' ? 'bg-green-500' : 'bg-blue-500'}">
    {$toastMessage.message}
  </div>
{/if}

<Router {routes} />
