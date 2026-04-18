<script>
  import { onDestroy } from 'svelte';
  import { t, locale } from '../lib/i18n.js';
  import { showToast } from '../lib/store.js';
  import { speechSupported, createContinuousSession, localeToBcp47 } from '../lib/voice.js';
  import { parseIntent, executeIntent } from '../lib/voice_dispatch.js';

  let listening = $state(false);
  let processingCount = $state(0);   // how many intents are mid-flight
  let session = null;

  async function handleTranscript(transcript) {
    processingCount += 1;
    try {
      const intent = await parseIntent(transcript);
      await executeIntent(intent);
    } catch (err) {
      showToast(err.message || $t('voice.error'), 'error');
    } finally {
      processingCount -= 1;
    }
  }

  function handleError(err) {
    const msg = err.message || '';
    if (msg === 'not-allowed' || msg === 'service-not-allowed') {
      showToast($t('voice.permission'), 'error');
    } else if (msg && msg !== 'no-speech' && msg !== 'aborted') {
      showToast($t('voice.error'), 'error');
    }
  }

  function onClick() {
    if (!speechSupported) {
      showToast($t('voice.unsupported'), 'error');
      return;
    }
    if (listening) {
      session?.stop();
      session = null;
      listening = false;
      return;
    }
    session = createContinuousSession({
      lang: localeToBcp47($locale),
      onTranscript: handleTranscript,
      onError: handleError,
      onStateChange: (state) => { listening = state === 'listening'; },
    });
    session.start();
  }

  onDestroy(() => { session?.stop(); });
</script>

{#if speechSupported}
  <button
    type="button"
    onclick={onClick}
    class="btn-icon relative"
    title={$t('voice.tooltip')}
    aria-label={$t('voice.tooltip')}
    aria-pressed={listening}
  >
    <svg class="h-5 w-5 {listening ? 'text-red-500' : 'text-gray-500'}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
      <line x1="12" y1="19" x2="12" y2="23" />
      <line x1="8" y1="23" x2="16" y2="23" />
    </svg>
    {#if listening}
      <span class="absolute -top-0.5 -right-0.5 inline-flex h-2 w-2 rounded-full bg-red-500 animate-pulse"></span>
    {/if}
    {#if processingCount > 0}
      <span class="absolute -bottom-0.5 -right-0.5 inline-flex h-2 w-2 rounded-full bg-blue-500 animate-pulse"></span>
    {/if}
  </button>
{/if}
