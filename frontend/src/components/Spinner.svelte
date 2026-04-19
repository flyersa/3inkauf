<script>
  // Reusable loading spinner. Inherits color from its parent via `currentColor`,
  // so place it inside a wrapper that sets the desired text color.
  let { size = 'md', label = '' } = $props();

  const sizeClass = {
    sm: 'h-4 w-4',
    md: 'h-6 w-6',
    lg: 'h-8 w-8',
  }[size] || size;
</script>

<span class="inline-flex items-center gap-2" role="status" aria-live="polite">
  <svg class="animate-spin {sizeClass}" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
    <path class="opacity-80" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
  </svg>
  {#if label}<span>{label}</span>{/if}
</span>
