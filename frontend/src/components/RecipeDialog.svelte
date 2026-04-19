<script>
  import { t } from '../lib/i18n.js';
  import { api } from '../lib/api.js';
  import { showToast } from '../lib/store.js';
  import Spinner from './Spinner.svelte';

  let { listId, itemsOnList = [], onClose, onItemsAdded } = $props();

  // 'from_list' | 'from_name'
  let mode = $state(itemsOnList.length > 0 ? 'from_list' : 'from_name');

  // ---- from_list state ----
  let loadingList = $state(false);
  let listRecipes = $state(null); // {recipes: [...]}
  let listError = $state('');
  let addingRecipeTitle = $state(null); // title currently being added

  async function generateFromList() {
    listError = '';
    loadingList = true;
    listRecipes = null;
    try {
      listRecipes = await api.post(`/lists/${listId}/recipes/from-items`, {});
    } catch (e) {
      listError = e.message || String(e);
    } finally {
      loadingList = false;
    }
  }

  async function addMissingFromRecipe(r) {
    const missing = (r.ingredients || []).filter(i => !i.already_have);
    if (!missing.length) { showToast($t('recipe.nothing.missing'), 'info'); return; }
    addingRecipeTitle = r.title;
    try {
      for (const ing of missing) {
        const body = { name: ing.name };
        if (ing.quantity) body.quantity = ing.quantity;
        try { await api.post(`/lists/${listId}/items`, body); } catch (err) { /* skip dupes */ }
      }
      showToast($t('recipe.added.toast').replace('{n}', String(missing.length)), 'success');
      onItemsAdded?.();
    } catch (e) {
      showToast(e.message || $t('error.generic'), 'error');
    } finally {
      addingRecipeTitle = null;
    }
  }

  // ---- from_name state ----
  let queryText = $state('');
  let loadingQuery = $state(false);
  let queryRecipe = $state(null); // {title, servings, notes, ingredients}
  let queryError = $state('');
  let selected = $state({}); // name -> bool

  async function generateFromName() {
    queryError = '';
    loadingQuery = true;
    queryRecipe = null;
    selected = {};
    try {
      const locale = localStorage.getItem('locale') || 'de';
      queryRecipe = await api.post('/recipes/from-query', { query: queryText, locale });
      for (const ing of queryRecipe.ingredients || []) {
        selected[ing.name] = true; // default all selected
      }
    } catch (e) {
      queryError = e.message || String(e);
    } finally {
      loadingQuery = false;
    }
  }

  async function addSelectedFromQuery() {
    const chosen = (queryRecipe?.ingredients || []).filter(i => selected[i.name]);
    if (!chosen.length) { showToast($t('recipe.pick.something'), 'info'); return; }
    loadingQuery = true;
    try {
      for (const ing of chosen) {
        const body = { name: ing.name };
        if (ing.quantity) body.quantity = ing.quantity;
        try { await api.post(`/lists/${listId}/items`, body); } catch (err) { /* skip dupes */ }
      }
      showToast($t('recipe.added.toast').replace('{n}', String(chosen.length)), 'success');
      onItemsAdded?.();
      onClose?.();
    } catch (e) {
      showToast(e.message || $t('error.generic'), 'error');
    } finally {
      loadingQuery = false;
    }
  }

  function toggleAll(val) {
    if (!queryRecipe) return;
    const next = {};
    for (const ing of queryRecipe.ingredients || []) next[ing.name] = val;
    selected = next;
  }

  // ---- full recipe view ----
  // null = not shown, {loading:true} = fetching, {data:{...}} = show
  let fullRecipe = $state(null);
  let emailSending = $state(false);
  let emailSent = $state(false);

  // Open the full recipe view. If the recipe object already has `steps`
  // (always the case for responses from /recipes/from-items and
  // /recipes/from-query since we bundle steps in the first call), show it
  // instantly and consistently — no second LLM call, no drift between views.
  // Only fall back to /recipes/full when the inline data is incomplete.
  async function openFullRecipe(recipe) {
    if (recipe && Array.isArray(recipe.steps) && recipe.steps.length > 0) {
      fullRecipe = { data: recipe };
      return;
    }
    // Fallback: old-shaped recipe without steps (should be rare)
    fullRecipe = { loading: true, title: recipe?.title || '' };
    try {
      const body = { title: recipe.title };
      if (recipe.servings) body.servings = recipe.servings;
      if (recipe.ingredients?.length) body.existing_ingredients = recipe.ingredients;
      body.locale = localStorage.getItem('locale') || 'de';
      const data = await api.post('/recipes/full', body);
      fullRecipe = { data };
    } catch (e) {
      fullRecipe = { error: e.message || String(e), title: recipe?.title || '' };
    }
  }

  function closeFullRecipe() {
    fullRecipe = null;
    emailSent = false;
    emailSending = false;
  }

  async function emailCurrentRecipe() {
    if (!fullRecipe?.data || emailSending || emailSent) return;
    emailSending = true;
    try {
      const locale = localStorage.getItem('locale') || 'de';
      await api.post('/recipes/email', { ...fullRecipe.data, locale });
      emailSent = true;
      showToast($t('recipe.full.emailed'), 'success');
    } catch (e) {
      showToast(e.message || $t('recipe.full.email_error'), 'error');
    } finally {
      emailSending = false;
    }
  }
</script>


<div class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4 overflow-y-auto" onclick={(e) => { if (e.target === e.currentTarget) onClose?.(); }} role="dialog">
  <div class="bg-white rounded-xl shadow-xl w-full max-w-lg my-8 max-h-[90vh] flex flex-col">
    <!-- Header -->
    <div class="flex items-center justify-between px-5 py-3 border-b">
      <div class="flex items-center gap-2 min-w-0">
        {#if fullRecipe}
          <button onclick={closeFullRecipe} class="btn-icon text-gray-600" aria-label="Back">
            <svg class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M9.707 16.707a1 1 0 01-1.414 0l-6-6a1 1 0 010-1.414l6-6a1 1 0 011.414 1.414L5.414 9H17a1 1 0 110 2H5.414l4.293 4.293a1 1 0 010 1.414z" clip-rule="evenodd" /></svg>
          </button>
        {/if}
        <h2 class="text-lg font-bold truncate">
          {fullRecipe ? (fullRecipe.data?.title || fullRecipe.title || $t('recipe.title')) : $t('recipe.title')}
        </h2>
      </div>
      <button onclick={() => onClose?.()} class="btn-icon text-gray-400 flex-shrink-0" aria-label="Close">
        <svg class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" /></svg>
      </button>
    </div>

    <!-- Tabs (hidden in full-recipe view) -->
    {#if !fullRecipe}
    <div class="flex border-b">
      <button onclick={() => mode = 'from_list'} disabled={itemsOnList.length === 0}
        class="flex-1 px-4 py-2 text-sm font-medium border-b-2 disabled:text-gray-300 disabled:cursor-not-allowed
          {mode === 'from_list' ? 'border-orange-500 text-orange-600' : 'border-transparent text-gray-600'}">
        {$t('recipe.tab.fromList')}
      </button>
      <button onclick={() => mode = 'from_name'}
        class="flex-1 px-4 py-2 text-sm font-medium border-b-2
          {mode === 'from_name' ? 'border-orange-500 text-orange-600' : 'border-transparent text-gray-600'}">
        {$t('recipe.tab.fromName')}
      </button>
    </div>

    <div class="overflow-y-auto px-5 py-4 space-y-4">
      {#if mode === 'from_list'}
        <div class="bg-orange-50 border-l-4 border-orange-300 p-3 text-sm text-gray-700">
          💡 {$t('recipe.hint.fromList')}
        </div>

        {#if itemsOnList.length === 0}
          <p class="text-sm text-gray-500">{$t('recipe.need.items')}</p>
        {:else if !listRecipes && !loadingList}
          <p class="text-sm text-gray-600">{$t('recipe.fromList.prompt').replace('{n}', String(itemsOnList.length))}</p>
          <button onclick={generateFromList} class="w-full bg-orange-500 hover:bg-orange-600 text-white py-2 rounded font-medium">
            🍳 {$t('recipe.fromList.button')}
          </button>
        {/if}

        {#if loadingList}
          <div class="text-center text-orange-600 py-6 text-sm">
            <Spinner size="md" label={$t('recipe.generating')} />
          </div>
        {/if}

        {#if listError}
          <div class="bg-red-50 border-l-4 border-red-400 p-3 text-sm text-red-700">{listError}</div>
        {/if}

        {#if listRecipes}
          {#if !listRecipes.recipes?.length}
            <p class="text-sm text-gray-500">{$t('recipe.none.found')}</p>
          {:else}
            <div class="space-y-3">
              {#each listRecipes.recipes as r (r.title)}
                <div class="border rounded-lg p-3 space-y-2">
                  <div>
                    <div class="flex items-start justify-between gap-2">
                      <h3 class="font-bold">{r.title}</h3>
                      <button onclick={() => openFullRecipe(r)}
                        class="btn-icon flex-shrink-0 text-gray-400 hover:text-orange-500" title={$t('recipe.view')} aria-label="View recipe">
                        <svg class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clip-rule="evenodd" /></svg>
                      </button>
                    </div>
                    {#if r.description}<p class="text-sm text-gray-600">{r.description}</p>{/if}
                  </div>
                  <ul class="text-sm space-y-1">
                    {#each r.ingredients as ing}
                      <li class="flex items-center gap-2">
                        {#if ing.already_have}
                          <span class="text-green-600 font-bold" title={$t('recipe.haveIt')}>✓</span>
                        {:else}
                          <span class="text-orange-500 font-bold" title={$t('recipe.missing')}>+</span>
                        {/if}
                        <span class={ing.already_have ? 'text-gray-500' : 'font-medium'}>
                          {ing.name}{ing.quantity ? ` (${ing.quantity})` : ''}
                        </span>
                      </li>
                    {/each}
                  </ul>
                  {#snippet missingCount()}
                    {@const missing = r.ingredients.filter(i => !i.already_have).length}
                    {#if missing === 0}
                      <p class="text-xs text-green-700">{$t('recipe.haveAll')}</p>
                    {:else}
                      <button onclick={() => addMissingFromRecipe(r)}
                        disabled={addingRecipeTitle === r.title}
                        class="w-full text-sm bg-orange-100 hover:bg-orange-200 text-orange-800 py-1.5 rounded font-medium disabled:opacity-50">
                        {#if addingRecipeTitle === r.title}
                          {$t('recipe.adding')}
                        {:else}
                          + {$t('recipe.addMissing').replace('{n}', String(missing))}
                        {/if}
                      </button>
                    {/if}
                  {/snippet}
                  {@render missingCount()}
                </div>
              {/each}
            </div>
            <button onclick={generateFromList} class="w-full text-sm text-orange-600 hover:underline">
              🔄 {$t('recipe.regenerate')}
            </button>
          {/if}
        {/if}
      {/if}

      {#if mode === 'from_name'}
        <div class="bg-orange-50 border-l-4 border-orange-300 p-3 text-sm text-gray-700">
          💡 {$t('recipe.hint.fromName')}
        </div>

        <form onsubmit={(e) => { e.preventDefault(); generateFromName(); }} class="space-y-2">
          <input
            type="text"
            bind:value={queryText}
            placeholder={$t('recipe.fromName.placeholder')}
            class="input-field w-full"
          />
          <button type="submit"
            disabled={!queryText.trim() || loadingQuery}
            class="w-full bg-orange-500 hover:bg-orange-600 text-white py-2 rounded font-medium disabled:opacity-50 flex items-center justify-center gap-2">
            {#if loadingQuery}
              <Spinner size="sm" label={$t('recipe.generating')} />
            {:else}
              🍳 {$t('recipe.fromName.button')}
            {/if}
          </button>
        </form>

        {#if queryError}
          <div class="bg-red-50 border-l-4 border-red-400 p-3 text-sm text-red-700">{queryError}</div>
        {/if}

        {#if queryRecipe}
          <div class="border rounded-lg p-3 space-y-2">
            <div>
              <div class="flex items-start justify-between gap-2">
                <h3 class="font-bold">{queryRecipe.title}</h3>
                <button onclick={() => openFullRecipe(queryRecipe)}
                  class="btn-icon flex-shrink-0 text-gray-400 hover:text-orange-500" title={$t('recipe.view')} aria-label="View recipe">
                  <svg class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clip-rule="evenodd" /></svg>
                </button>
              </div>
              {#if queryRecipe.servings}
                <p class="text-xs text-gray-500">{$t('recipe.servings').replace('{n}', String(queryRecipe.servings))}</p>
              {/if}
              {#if queryRecipe.notes}
                <p class="text-xs text-gray-500 italic mt-1">{queryRecipe.notes}</p>
              {/if}
            </div>
            <div class="flex justify-end gap-2 text-xs">
              <button onclick={() => toggleAll(true)} class="text-orange-600 hover:underline">{$t('scan.all')}</button>
              <span class="text-gray-300">|</span>
              <button onclick={() => toggleAll(false)} class="text-orange-600 hover:underline">{$t('scan.none')}</button>
            </div>
            <ul class="space-y-1 text-sm">
              {#each queryRecipe.ingredients as ing (ing.name)}
                <li class="flex items-center gap-2">
                  <input type="checkbox" bind:checked={selected[ing.name]} class="h-4 w-4" />
                  <span class="font-medium">{ing.name}</span>
                  {#if ing.quantity}<span class="text-gray-500 text-xs">({ing.quantity})</span>{/if}
                </li>
              {/each}
            </ul>
            <button onclick={addSelectedFromQuery}
              disabled={loadingQuery}
              class="w-full mt-2 bg-orange-500 hover:bg-orange-600 text-white py-2 rounded font-medium disabled:opacity-50">
              + {$t('recipe.addSelected')}
            </button>
          </div>
        {/if}
      {/if}
    </div>
    {/if}

    <!-- Full recipe view -->
    {#if fullRecipe}
      <div class="overflow-y-auto px-5 py-4 space-y-4">
        {#if fullRecipe.loading}
          <div class="text-center text-orange-600 py-12">
            <Spinner size="lg" label={$t('recipe.full.loading')} />
          </div>
        {:else if fullRecipe.error}
          <div class="bg-red-50 border-l-4 border-red-400 p-3 text-sm text-red-700">{fullRecipe.error}</div>
        {:else if fullRecipe.data}
          {@const d = fullRecipe.data}
          <div class="space-y-1">
            <h3 class="text-xl font-bold">{d.title}</h3>
            <p class="text-xs text-gray-500">
              {#if d.servings}<span>{$t('recipe.servings').replace('{n}', String(d.servings))}</span>{/if}
              {#if d.prep_time_minutes}<span class="ml-2">· {$t('recipe.full.prep')}: {d.prep_time_minutes} {$t('recipe.full.minutes')}</span>{/if}
              {#if d.cook_time_minutes}<span class="ml-2">· {$t('recipe.full.cook')}: {d.cook_time_minutes} {$t('recipe.full.minutes')}</span>{/if}
            </p>
          </div>

          <section>
            <h4 class="font-semibold mb-2">{$t('recipe.full.ingredients')}</h4>
            <ul class="text-sm space-y-1 list-disc list-inside">
              {#each d.ingredients || [] as ing}
                <li>{ing.name}{ing.quantity ? ` — ${ing.quantity}` : ''}</li>
              {/each}
            </ul>
          </section>

          <section>
            <h4 class="font-semibold mb-2">{$t('recipe.full.steps')}</h4>
            <ol class="text-sm space-y-2 list-decimal list-inside marker:text-orange-500 marker:font-bold">
              {#each d.steps || [] as step}
                <li>{step}</li>
              {/each}
            </ol>
          </section>

          {#if d.tips}
            <div class="bg-amber-50 border-l-4 border-amber-300 p-3 text-sm">
              <strong>{$t('recipe.full.tips')}:</strong> {d.tips}
            </div>
          {/if}

          <button onclick={emailCurrentRecipe} disabled={emailSending || emailSent}
            class="w-full py-2 rounded font-medium flex items-center justify-center gap-2
              {emailSent ? 'bg-green-500 text-white cursor-default' : 'bg-orange-500 hover:bg-orange-600 text-white disabled:opacity-50'}">
            {#if emailSending}
              <Spinner size="sm" label={$t('recipe.full.emailing')} />
            {:else if emailSent}
              ✓ {$t('recipe.full.emailed')}
            {:else}
              ✉ {$t('recipe.full.email')}
            {/if}
          </button>
        {/if}
      </div>
    {/if}

    <div class="border-t px-5 py-3 flex justify-between items-center">
      {#if fullRecipe}
        <button onclick={closeFullRecipe} class="px-4 py-2 text-sm rounded border hover:bg-gray-100">← {$t('recipe.full.back')}</button>
      {:else}
        <span></span>
      {/if}
      <button onclick={() => onClose?.()} class="px-4 py-2 text-sm rounded border hover:bg-gray-100">{$t('btn.close')}</button>
    </div>
  </div>
</div>
