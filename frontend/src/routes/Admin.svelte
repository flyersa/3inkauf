<script>
  import { onMount } from 'svelte';

  // ---------- Auth state ----------
  let authHeader = $state(sessionStorage.getItem('admin_auth') || '');
  let loggedIn = $derived(!!authHeader);

  let loginUser = $state('admin');
  let loginPw = $state('');
  let loginError = $state('');

  async function doLogin(e) {
    e?.preventDefault?.();
    loginError = '';
    const enc = btoa(`${loginUser}:${loginPw}`);
    const h = `Basic ${enc}`;
    const resp = await fetch('/api/v1/admin/stats', { headers: { Authorization: h } });
    if (resp.status === 200) {
      authHeader = h;
      sessionStorage.setItem('admin_auth', h);
      loginPw = '';
      await refreshAll();
    } else if (resp.status === 401) {
      loginError = 'Invalid credentials';
    } else if (resp.status === 503) {
      loginError = 'Admin not configured on the server';
    } else {
      loginError = `Error ${resp.status}`;
    }
  }

  function logout() {
    authHeader = '';
    sessionStorage.removeItem('admin_auth');
  }

  async function api(method, path, body) {
    const opts = { method, headers: { Authorization: authHeader } };
    if (body !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    const r = await fetch(`/api/v1/admin${path}`, opts);
    if (r.status === 401) {
      logout();
      throw new Error('Session expired');
    }
    if (!r.ok) {
      let msg = `${r.status} ${r.statusText}`;
      try { const j = await r.json(); if (j.detail) msg = j.detail; } catch {}
      throw new Error(msg);
    }
    if (r.status === 204) return null;
    return r.json();
  }

  // ---------- View state ----------
  let tab = $state('stats');
  let errorMsg = $state('');
  let busy = $state(false);

  function err(e) { errorMsg = e?.message || String(e); setTimeout(() => errorMsg = '', 4000); }

  // ---------- Stats ----------
  let stats = $state(null);
  async function loadStats() { stats = await api('GET', '/stats'); }

  // ---------- Users ----------
  let users = $state([]);
  async function loadUsers() { users = await api('GET', '/users'); }

  let editUser = $state(null);
  async function saveUser() {
    busy = true;
    try {
      const updated = await api('PATCH', `/users/${editUser.id}`, {
        display_name: editUser.display_name,
        email: editUser.email,
        locale: editUser.locale,
        color: editUser.color,
      });
      const idx = users.findIndex(u => u.id === updated.id);
      if (idx >= 0) users[idx] = updated;
      editUser = null;
    } catch (e) { err(e); }
    finally { busy = false; }
  }

  async function deleteUser(u) {
    if (!confirm(`Delete user ${u.email}?\nThis also removes their lists, shares and bonus cards.`)) return;
    busy = true;
    try {
      await api('DELETE', `/users/${u.id}`);
      users = users.filter(x => x.id !== u.id);
    } catch (e) { err(e); }
    finally { busy = false; }
  }

  let resetResult = $state(null);
  let resetSendEmail = $state(false);
  let resetTarget = $state(null);
  async function doResetPassword() {
    busy = true;
    try {
      const r = await api('POST', `/users/${resetTarget.id}/reset-password`, { send_email: resetSendEmail });
      resetResult = { ...r, user: resetTarget };
      resetTarget = null;
    } catch (e) { err(e); resetTarget = null; }
    finally { busy = false; }
  }

  // ---------- Lists ----------
  let lists = $state([]);
  let listDetail = $state(null);
  async function loadLists() { lists = await api('GET', '/lists'); }
  async function openList(l) { listDetail = await api('GET', `/lists/${l.id}`); }
  async function reloadListDetail() {
    if (listDetail) listDetail = await api('GET', `/lists/${listDetail.list.id}`);
  }
  async function deleteList(l) {
    if (!confirm(`Delete list "${l.name}" and all its items/categories?`)) return;
    busy = true;
    try {
      await api('DELETE', `/lists/${l.id}`);
      lists = lists.filter(x => x.id !== l.id);
      if (listDetail && listDetail.list.id === l.id) listDetail = null;
    } catch (e) { err(e); }
    finally { busy = false; }
  }
  async function deleteItem(item) {
    if (!confirm(`Delete item "${item.name}"?`)) return;
    try {
      await api('DELETE', `/lists/${listDetail.list.id}/items/${item.id}`);
      await reloadListDetail();
    } catch (e) { err(e); }
  }
  async function deleteCategory(c) {
    if (!confirm(`Delete category "${c.name}"? Items in it will become uncategorized.`)) return;
    try {
      await api('DELETE', `/lists/${listDetail.list.id}/categories/${c.id}`);
      await reloadListDetail();
    } catch (e) { err(e); }
  }
  async function moveItem(idx, dir) {
    const items = [...listDetail.items];
    const j = idx + dir;
    if (j < 0 || j >= items.length) return;
    [items[idx], items[j]] = [items[j], items[idx]];
    try {
      await api('PATCH', `/lists/${listDetail.list.id}/items/reorder`, { ordered_ids: items.map(i => i.id) });
      await reloadListDetail();
    } catch (e) { err(e); }
  }
  async function moveCat(idx, dir) {
    const cats = [...listDetail.categories];
    const j = idx + dir;
    if (j < 0 || j >= cats.length) return;
    [cats[idx], cats[j]] = [cats[j], cats[idx]];
    try {
      await api('PATCH', `/lists/${listDetail.list.id}/categories/reorder`, { ordered_ids: cats.map(c => c.id) });
      await reloadListDetail();
    } catch (e) { err(e); }
  }

  // ---------- Runtime Config ----------
  let runtimeCfg = $state(null);
  let ovrModel = $state('');
  let ovrOcr = $state('');
  let ovrAudio = $state('');
  let ovrRecipe = $state('');
  async function loadRuntime() {
    runtimeCfg = await api('GET', '/runtime-config');
    ovrModel = runtimeCfg.overrides.ollama_model || '';
    ovrOcr = runtimeCfg.overrides.ollama_ocr_model || '';
    ovrAudio = runtimeCfg.overrides.ollama_audio_model || '';
    ovrRecipe = runtimeCfg.overrides.ollama_recipe_model || '';
  }
  async function applyRuntime() {
    busy = true;
    try {
      runtimeCfg = await api('POST', '/runtime-config', {
        ollama_model: ovrModel,
        ollama_ocr_model: ovrOcr,
        ollama_audio_model: ovrAudio,
        ollama_recipe_model: ovrRecipe,
      });
    } catch (e) { err(e); }
    finally { busy = false; }
  }
  async function clearRuntime() {
    if (!confirm('Clear all runtime overrides? Effective models revert to .env values.')) return;
    busy = true;
    try {
      runtimeCfg = await api('DELETE', '/runtime-config');
      ovrModel = ''; ovrOcr = ''; ovrAudio = ''; ovrRecipe = '';
    } catch (e) { err(e); }
    finally { busy = false; }
  }

  async function refreshAll() {
    try {
      await Promise.all([loadStats(), loadUsers(), loadLists(), loadRuntime()]);
    } catch (e) { err(e); }
  }

  $effect(() => {
    if (tab === 'stats' && loggedIn && !stats) loadStats().catch(err);
    if (tab === 'users' && loggedIn && !users.length) loadUsers().catch(err);
    if (tab === 'lists' && loggedIn && !lists.length) loadLists().catch(err);
    if (tab === 'runtime' && loggedIn && !runtimeCfg) loadRuntime().catch(err);
  });

  onMount(() => {
    if (loggedIn) refreshAll();
  });

  function fmtDate(iso) {
    if (!iso) return '';
    try { return new Date(iso).toLocaleString(); } catch { return iso; }
  }
</script>

<div class="min-h-screen bg-gray-50 text-gray-900">
  {#if !loggedIn}
    <div class="flex min-h-screen items-center justify-center p-4">
      <form onsubmit={doLogin} class="w-full max-w-sm bg-white p-6 rounded-xl shadow space-y-4">
        <h1 class="text-2xl font-bold">Admin Login</h1>
        <p class="text-sm text-gray-600">Enter credentials configured in the backend <code>.env</code>.</p>
        <label class="block">
          <span class="text-sm font-medium">Username</span>
          <input type="text" bind:value={loginUser} class="mt-1 w-full rounded border-gray-300 px-3 py-2 border" autofocus />
        </label>
        <label class="block">
          <span class="text-sm font-medium">Password</span>
          <input type="password" bind:value={loginPw} class="mt-1 w-full rounded border-gray-300 px-3 py-2 border" />
        </label>
        {#if loginError}
          <p class="text-sm text-red-600">{loginError}</p>
        {/if}
        <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white py-2 rounded font-medium">Sign in</button>
      </form>
    </div>
  {:else}
    <header class="bg-white border-b px-4 py-3 flex items-center justify-between">
      <h1 class="text-xl font-bold">3inkauf Admin</h1>
      <div class="flex items-center gap-2">
        <button onclick={refreshAll} class="text-sm px-3 py-1 border rounded hover:bg-gray-100">Refresh</button>
        <button onclick={logout} class="text-sm px-3 py-1 bg-gray-200 rounded hover:bg-gray-300">Logout</button>
      </div>
    </header>

    <nav class="bg-white border-b flex gap-1 px-2">
      {#each [['stats','Stats'],['users','Users'],['lists','Lists'],['runtime','Runtime Config']] as [k,label]}
        <button onclick={() => tab = k}
          class="px-4 py-2 text-sm font-medium border-b-2 {tab === k ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-600 hover:text-gray-900'}">{label}</button>
      {/each}
    </nav>

    {#if errorMsg}
      <div class="bg-red-100 border-b border-red-200 px-4 py-2 text-sm text-red-800">{errorMsg}</div>
    {/if}

    <main class="p-4 max-w-6xl mx-auto">

      {#if tab === 'stats'}
        {#if stats}
          <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div class="bg-white rounded-xl shadow p-4"><div class="text-sm text-gray-500">Users</div><div class="text-3xl font-bold">{stats.users_total}</div></div>
            <div class="bg-white rounded-xl shadow p-4"><div class="text-sm text-gray-500">Lists</div><div class="text-3xl font-bold">{stats.lists_total}</div></div>
            <div class="bg-white rounded-xl shadow p-4"><div class="text-sm text-gray-500">Items</div><div class="text-3xl font-bold">{stats.items_total}</div></div>
            <div class="bg-white rounded-xl shadow p-4"><div class="text-sm text-gray-500">Bonus cards</div><div class="text-3xl font-bold">{stats.bonus_cards_total}</div></div>
            <div class="bg-white rounded-xl shadow p-4 col-span-2"><div class="text-sm text-gray-500">Active users right now (WebSocket)</div><div class="text-3xl font-bold text-green-600">{stats.active_users_now}</div><div class="text-xs text-gray-400 mt-1">Across {stats.active_list_rooms} list room(s)</div></div>
          </div>
        {:else}
          <p class="text-gray-500">Loading…</p>
        {/if}
      {/if}

      {#if tab === 'users'}
        <div class="bg-white rounded-xl shadow overflow-hidden">
          <table class="w-full text-sm">
            <thead class="bg-gray-50 text-left">
              <tr>
                <th class="px-3 py-2">Color</th>
                <th class="px-3 py-2">Email</th>
                <th class="px-3 py-2">Name</th>
                <th class="px-3 py-2">Locale</th>
                <th class="px-3 py-2">Created</th>
                <th class="px-3 py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {#each users as u (u.id)}
                <tr class="border-t">
                  <td class="px-3 py-2"><span class="inline-block w-5 h-5 rounded-full border" style="background:{u.color}"></span></td>
                  <td class="px-3 py-2 font-mono text-xs">{u.email}</td>
                  <td class="px-3 py-2">{u.display_name}</td>
                  <td class="px-3 py-2">{u.locale}</td>
                  <td class="px-3 py-2 text-xs text-gray-500">{fmtDate(u.created_at)}</td>
                  <td class="px-3 py-2 space-x-1">
                    <button onclick={() => editUser = { ...u }} class="text-xs px-2 py-1 border rounded hover:bg-gray-100">Edit</button>
                    <button onclick={() => { resetTarget = u; resetSendEmail = false; }} class="text-xs px-2 py-1 border rounded hover:bg-gray-100">Reset PW</button>
                    <button onclick={() => deleteUser(u)} class="text-xs px-2 py-1 bg-red-100 text-red-700 border border-red-200 rounded hover:bg-red-200">Delete</button>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
          {#if !users.length}
            <div class="p-4 text-sm text-gray-500 text-center">No users</div>
          {/if}
        </div>
      {/if}

      {#if tab === 'lists'}
        {#if listDetail}
          <div class="bg-white rounded-xl shadow p-4 space-y-4">
            <div class="flex items-center justify-between">
              <div>
                <button onclick={() => listDetail = null} class="text-blue-600 text-sm hover:underline">&larr; Back to lists</button>
                <h2 class="text-xl font-bold mt-1">{listDetail.list.name}</h2>
              </div>
            </div>

            <section>
              <h3 class="font-semibold mb-2">Categories ({listDetail.categories.length})</h3>
              <ul class="divide-y">
                {#each listDetail.categories as c, i (c.id)}
                  <li class="flex items-center justify-between py-2">
                    <span class="font-medium">{c.name}</span>
                    <div class="space-x-1">
                      <button onclick={() => moveCat(i, -1)} disabled={i === 0} class="text-xs px-2 py-1 border rounded disabled:opacity-40">↑</button>
                      <button onclick={() => moveCat(i, 1)} disabled={i === listDetail.categories.length - 1} class="text-xs px-2 py-1 border rounded disabled:opacity-40">↓</button>
                      <button onclick={() => deleteCategory(c)} class="text-xs px-2 py-1 bg-red-100 text-red-700 rounded">Delete</button>
                    </div>
                  </li>
                {/each}
              </ul>
              {#if !listDetail.categories.length}<p class="text-sm text-gray-500">No categories</p>{/if}
            </section>

            <section>
              <h3 class="font-semibold mb-2">Items ({listDetail.items.length})</h3>
              <ul class="divide-y">
                {#each listDetail.items as item, i (item.id)}
                  <li class="flex items-center justify-between py-2">
                    <span>
                      {#if item.checked}<span class="line-through text-gray-400">{item.name}</span>{:else}{item.name}{/if}
                      {#if item.quantity}<span class="text-xs text-gray-500 ml-1">({item.quantity})</span>{/if}
                      {#if item.category_id}
                        {@const cat = listDetail.categories.find(c => c.id === item.category_id)}
                        {#if cat}<span class="ml-2 text-xs bg-gray-100 px-2 py-0.5 rounded">{cat.name}</span>{/if}
                      {/if}
                    </span>
                    <div class="space-x-1">
                      <button onclick={() => moveItem(i, -1)} disabled={i === 0} class="text-xs px-2 py-1 border rounded disabled:opacity-40">↑</button>
                      <button onclick={() => moveItem(i, 1)} disabled={i === listDetail.items.length - 1} class="text-xs px-2 py-1 border rounded disabled:opacity-40">↓</button>
                      <button onclick={() => deleteItem(item)} class="text-xs px-2 py-1 bg-red-100 text-red-700 rounded">Delete</button>
                    </div>
                  </li>
                {/each}
              </ul>
              {#if !listDetail.items.length}<p class="text-sm text-gray-500">No items</p>{/if}
            </section>
          </div>
        {:else}
          <div class="bg-white rounded-xl shadow overflow-hidden">
            <table class="w-full text-sm">
              <thead class="bg-gray-50 text-left">
                <tr>
                  <th class="px-3 py-2">Name</th>
                  <th class="px-3 py-2">Owner</th>
                  <th class="px-3 py-2">Items</th>
                  <th class="px-3 py-2">Cats</th>
                  <th class="px-3 py-2">Shares</th>
                  <th class="px-3 py-2">Created</th>
                  <th class="px-3 py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {#each lists as l (l.id)}
                  <tr class="border-t">
                    <td class="px-3 py-2 font-medium">{l.name}</td>
                    <td class="px-3 py-2 text-xs">{l.owner_email}</td>
                    <td class="px-3 py-2">{l.items_count}</td>
                    <td class="px-3 py-2">{l.categories_count}</td>
                    <td class="px-3 py-2">{l.shares_count}</td>
                    <td class="px-3 py-2 text-xs text-gray-500">{fmtDate(l.created_at)}</td>
                    <td class="px-3 py-2 space-x-1">
                      <button onclick={() => openList(l)} class="text-xs px-2 py-1 border rounded hover:bg-gray-100">Open</button>
                      <button onclick={() => deleteList(l)} class="text-xs px-2 py-1 bg-red-100 text-red-700 border border-red-200 rounded hover:bg-red-200">Delete</button>
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
            {#if !lists.length}
              <div class="p-4 text-sm text-gray-500 text-center">No lists</div>
            {/if}
          </div>
        {/if}
      {/if}

      {#if tab === 'runtime'}
        {#if runtimeCfg}
          <div class="bg-amber-50 border-l-4 border-amber-400 p-3 text-sm mb-4">
            <strong>Temporary overrides.</strong> These are applied in memory only and reset on backend restart. The <code>.env</code> file remains the source of truth.
          </div>
          <div class="bg-white rounded-xl shadow p-4 space-y-4">
            <div>
              <h3 class="font-semibold mb-2">Effective models right now</h3>
              <ul class="text-sm font-mono space-y-1">
                <li>Auto-sort &amp; default: <span class="font-bold">{runtimeCfg.effective.ollama_model}</span> <span class="text-xs text-gray-500">(env: {runtimeCfg.settings.ollama_model || '—'})</span></li>
                <li>OCR / scan: <span class="font-bold">{runtimeCfg.effective.ollama_ocr_model}</span> <span class="text-xs text-gray-500">(env: {runtimeCfg.settings.ollama_ocr_model || '—'})</span></li>
                <li>Voice intent: <span class="font-bold">{runtimeCfg.effective.ollama_audio_model}</span> <span class="text-xs text-gray-500">(env: {runtimeCfg.settings.ollama_audio_model || '—'})</span></li>
                <li>Recipes: <span class="font-bold">{runtimeCfg.effective.ollama_recipe_model}</span> <span class="text-xs text-gray-500">(env: {runtimeCfg.settings.ollama_recipe_model || '—'})</span></li>
              </ul>
            </div>

            <div class="border-t pt-4 space-y-3">
              <h3 class="font-semibold">Set overrides</h3>
              <label class="block">
                <span class="text-sm font-medium">OLLAMA_MODEL (auto-sort)</span>
                <input bind:value={ovrModel} placeholder="leave empty to use env" class="mt-1 w-full font-mono text-sm rounded border-gray-300 px-3 py-2 border" />
              </label>
              <label class="block">
                <span class="text-sm font-medium">OLLAMA_OCR_MODEL (scan)</span>
                <input bind:value={ovrOcr} placeholder="leave empty to use env" class="mt-1 w-full font-mono text-sm rounded border-gray-300 px-3 py-2 border" />
              </label>
              <label class="block">
                <span class="text-sm font-medium">OLLAMA_AUDIO_MODEL (voice)</span>
                <input bind:value={ovrAudio} placeholder="leave empty to use env" class="mt-1 w-full font-mono text-sm rounded border-gray-300 px-3 py-2 border" />
              </label>
              <label class="block">
                <span class="text-sm font-medium">OLLAMA_RECIPE_MODEL (recipes)</span>
                <input bind:value={ovrRecipe} placeholder="leave empty to use env" class="mt-1 w-full font-mono text-sm rounded border-gray-300 px-3 py-2 border" />
              </label>
              <div class="flex gap-2">
                <button onclick={applyRuntime} disabled={busy} class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded font-medium text-sm disabled:opacity-50">Apply</button>
                <button onclick={clearRuntime} disabled={busy} class="px-4 py-2 bg-gray-200 hover:bg-gray-300 rounded font-medium text-sm disabled:opacity-50">Clear all overrides</button>
              </div>
            </div>
          </div>
        {:else}
          <p class="text-gray-500">Loading…</p>
        {/if}
      {/if}

    </main>

    {#if editUser}
      <div class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
        <div class="bg-white rounded-xl shadow-xl p-6 max-w-md w-full space-y-3">
          <h2 class="text-lg font-bold">Edit user</h2>
          <label class="block"><span class="text-sm font-medium">Display name</span>
            <input bind:value={editUser.display_name} class="mt-1 w-full rounded border-gray-300 px-3 py-2 border" /></label>
          <label class="block"><span class="text-sm font-medium">Email</span>
            <input bind:value={editUser.email} class="mt-1 w-full rounded border-gray-300 px-3 py-2 border" /></label>
          <label class="block"><span class="text-sm font-medium">Locale</span>
            <select bind:value={editUser.locale} class="mt-1 w-full rounded border-gray-300 px-3 py-2 border">
              <option value="de">de</option><option value="en">en</option>
            </select></label>
          <label class="block"><span class="text-sm font-medium">Color</span>
            <input type="color" bind:value={editUser.color} class="mt-1 w-20 h-10 rounded border" /></label>
          <div class="flex justify-end gap-2 pt-2">
            <button onclick={() => editUser = null} class="px-3 py-2 rounded border">Cancel</button>
            <button onclick={saveUser} disabled={busy} class="px-3 py-2 bg-blue-600 text-white rounded disabled:opacity-50">Save</button>
          </div>
        </div>
      </div>
    {/if}

    {#if resetTarget}
      <div class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
        <div class="bg-white rounded-xl shadow-xl p-6 max-w-md w-full space-y-3">
          <h2 class="text-lg font-bold">Reset password</h2>
          <p class="text-sm">Generate a new password for <strong>{resetTarget.email}</strong>?</p>
          <label class="flex items-center gap-2 text-sm">
            <input type="checkbox" bind:checked={resetSendEmail} />
            Also send the new password to the user's email
          </label>
          <p class="text-xs text-gray-500">The new password will always be shown here so you can hand it over manually if needed.</p>
          <div class="flex justify-end gap-2 pt-2">
            <button onclick={() => resetTarget = null} class="px-3 py-2 rounded border">Cancel</button>
            <button onclick={doResetPassword} disabled={busy} class="px-3 py-2 bg-blue-600 text-white rounded disabled:opacity-50">Reset</button>
          </div>
        </div>
      </div>
    {/if}

    {#if resetResult}
      <div class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
        <div class="bg-white rounded-xl shadow-xl p-6 max-w-md w-full space-y-3">
          <h2 class="text-lg font-bold">New password for {resetResult.user.email}</h2>
          <div class="bg-gray-100 p-3 rounded font-mono text-lg break-all select-all">{resetResult.new_password}</div>
          <button onclick={() => { navigator.clipboard?.writeText(resetResult.new_password); }} class="text-sm text-blue-600 hover:underline">Copy to clipboard</button>
          {#if resetResult.email_requested}
            {#if resetResult.email_sent}
              <p class="text-sm text-green-700">✓ Email sent successfully.</p>
            {:else}
              <p class="text-sm text-red-700">✗ Email delivery failed{resetResult.email_error ? `: ${resetResult.email_error}` : ''}. Hand the password over manually.</p>
            {/if}
          {:else}
            <p class="text-sm text-gray-600">No email sent — hand the password to the user manually.</p>
          {/if}
          <div class="flex justify-end pt-2">
            <button onclick={() => resetResult = null} class="px-3 py-2 bg-blue-600 text-white rounded">Close</button>
          </div>
        </div>
      </div>
    {/if}
  {/if}
</div>
