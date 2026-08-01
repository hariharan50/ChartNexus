<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { HTMLButtonAttributes } from 'svelte/elements';

  type Variant = 'primary' | 'secondary' | 'ghost';

  interface Props extends HTMLButtonAttributes {
    variant?: Variant;
    loading?: boolean;
    full?: boolean;
    children: Snippet;
  }

  let {
    variant = 'primary',
    loading = false,
    full = false,
    disabled = false,
    type = 'button',
    children,
    ...rest
  }: Props = $props();
</script>

<button
  {type}
  class="btn {variant}"
  class:full
  disabled={disabled || loading}
  aria-busy={loading}
  {...rest}
>
  {#if loading}
    <span class="spinner" aria-hidden="true"></span>
  {/if}
  {@render children()}
</button>

<style>
  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--mc-space-2);
    min-height: var(--mc-control-h);
    padding: 0 var(--mc-control-px);
    border: 1px solid transparent;
    border-radius: var(--mc-radius);
    font-size: var(--mc-text-base);
    font-weight: 600;
    line-height: 1;
    cursor: pointer;
    transition:
      background var(--mc-duration-fast) ease,
      border-color var(--mc-duration-fast) ease,
      transform var(--mc-duration-fast) ease;
  }

  .btn.full {
    width: 100%;
  }

  .btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .btn:not(:disabled):active {
    transform: translateY(1px);
  }

  .primary {
    background: var(--mc-brand);
    color: var(--mc-on-brand);
  }

  .primary:not(:disabled):hover {
    background: var(--mc-brand-hover);
  }

  .secondary {
    background: var(--mc-auth-field);
    border-color: var(--mc-auth-border);
    color: var(--mc-text);
  }

  .secondary:not(:disabled):hover {
    background: var(--mc-auth-field-hover);
  }

  .ghost {
    background: transparent;
    color: var(--mc-text-muted);
  }

  .ghost:not(:disabled):hover {
    color: var(--mc-text);
  }

  .spinner {
    width: 0.875rem;
    height: 0.875rem;
    border: 2px solid currentColor;
    border-top-color: transparent;
    border-radius: 50%;
    animation: spin 700ms linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
</style>
