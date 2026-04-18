// Web Speech wrapper. Supports both a single push-to-talk listen
// and a continuous "keep-listening" session for hands-free use.

const Ctor =
  typeof window !== 'undefined'
    ? (window.SpeechRecognition || window.webkitSpeechRecognition || null)
    : null;

export const speechSupported = !!Ctor;

export function localeToBcp47(locale) {
  if (!locale) return 'en-US';
  if (locale.startsWith('de')) return 'de-DE';
  return 'en-US';
}

/** Push-to-talk: one utterance, resolves with transcript or rejects. */
export function listenOnce({ lang = 'en-US' } = {}) {
  return new Promise((resolve, reject) => {
    if (!Ctor) return reject(new Error('unsupported'));
    const rec = new Ctor();
    rec.lang = lang;
    rec.interimResults = false;
    rec.continuous = false;
    rec.maxAlternatives = 1;
    let finalText = '';
    let settled = false;

    rec.onresult = (e) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) finalText += e.results[i][0].transcript;
      }
    };
    rec.onerror = (e) => {
      if (settled) return;
      settled = true;
      reject(new Error(e.error || 'speech-error'));
    };
    rec.onend = () => {
      if (settled) return;
      settled = true;
      const t = finalText.trim();
      if (!t) reject(new Error('no-speech'));
      else resolve(t);
    };
    try { rec.start(); } catch (err) { settled = true; reject(err); }
    listenOnce.currentRec = rec;
  });
}

export function cancelListening() {
  const rec = listenOnce.currentRec;
  if (rec) {
    try { rec.abort(); } catch {}
    listenOnce.currentRec = null;
  }
}

/** Continuous session: tap once to start, tap again to stop. Each final
 *  utterance calls onTranscript. Auto-restarts on benign end events so the
 *  mic keeps listening across multiple commands. */
export function createContinuousSession({
  lang = 'en-US',
  onTranscript,
  onError,
  onStateChange,
} = {}) {
  if (!Ctor) throw new Error('unsupported');
  let rec = null;
  let active = false;
  let restartHandle = null;

  function notify(state) {
    try { onStateChange?.(state); } catch {}
  }

  function makeRec() {
    const r = new Ctor();
    r.lang = lang;
    r.interimResults = false;
    // continuous=true would batch multiple final results per session, but
    // results are delivered reliably across browsers only with one-shot
    // sessions that we restart ourselves.
    r.continuous = false;
    r.maxAlternatives = 1;

    r.onresult = (e) => {
      let text = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) text += e.results[i][0].transcript;
      }
      text = text.trim();
      if (text) {
        try { onTranscript?.(text); } catch (err) { onError?.(err); }
      }
    };

    r.onerror = (e) => {
      const code = e.error;
      // Silence / user-silent / aborted-by-us are not fatal — we just loop.
      if (code === 'no-speech' || code === 'aborted' || code === 'audio-capture') return;
      onError?.(new Error(code || 'speech-error'));
      // For fatal errors (e.g. not-allowed, network), stop the session.
      if (code === 'not-allowed' || code === 'service-not-allowed') stop();
    };

    r.onend = () => {
      if (!active) return;
      // Debounce restart so Chrome doesn't throttle us.
      if (restartHandle) clearTimeout(restartHandle);
      restartHandle = setTimeout(() => {
        if (active) {
          try { r.start(); } catch { /* already starting */ }
        }
      }, 150);
    };

    return r;
  }

  function start() {
    if (active) return;
    active = true;
    rec = makeRec();
    notify('listening');
    try { rec.start(); } catch { /* already active */ }
  }

  function stop() {
    active = false;
    if (restartHandle) { clearTimeout(restartHandle); restartHandle = null; }
    if (rec) {
      try { rec.abort(); } catch {}
      rec = null;
    }
    notify('idle');
  }

  return { start, stop, isActive: () => active };
}
