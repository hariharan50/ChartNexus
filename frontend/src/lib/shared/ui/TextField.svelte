<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { HTMLInputAttributes } from 'svelte/elements';

  interface Props extends Omit<HTMLInputAttributes, 'value'> {
    label: string;
    value: string;
    error?: string | undefined;
    /** Leading glyph, rendered decoratively inside the field. */
    icon?: Snippet;
    /** Trailing control, e.g. a password reveal toggle. */
    trailing?: Snippet;
  }

  let {
    label,
    value = $bindable(''),
    error = undefined,
    icon,
    trailing,
    id,
    ...rest
  }: Props = $props();

  // $props.id() is stable across re-renders and identical between the server
  // and client renders, so hydration does not swap the label's `for` target.
  const uid = $props.id();
  const fieldId = $derived(id ?? uid);
  const errorId = $derived(`${fieldId}-error`);
</script>

<div class="field">
  <label for={fieldId}>{label}</label>

  <div class="shell" class:invalid={!!error}>
    {#if icon}
      <span class="icon" aria-hidden="true">{@render icon()}</span>
    {/if}

    <input
      id={fieldId}
      bind:value
      aria-invalid={error ? 'true' : undefined}
      aria-describedby={error ? errorId : undefined}
      {...rest}
    />

    {#if trailing}
      <span class="trailing">{@render trailing()}</span>
    {/if}
  </div>

  {#if error}
    <p class="error" id={errorId}>{error}</p>
  {/if}
</div>

<style>
  .field {
    display: flex;
    flex-direction: column;
    gap: 0.375rem;
  }

  label {
    font-size: var(--mc-text-xs);
    font-weight: 500;
    color: var(--mc-text-muted);
  }

  .shell {
    display: flex;
    align-items: center;
    gap: var(--mc-space-2);
    min-height: var(--mc-control-h);
    padding: 0 var(--mc-control-px);
    background: var(--mc-auth-field);
    border: 1px solid var(--mc-auth-border);
    border-radius: var(--mc-radius);
    transition:
      border-color var(--mc-duration-fast) ease,
      background var(--mc-duration-fast) ease;
  }

  .shell:hover {
    background: var(--mc-auth-field-hover);
  }

  .shell:focus-within {
    border-color: var(--mc-brand);
    background: var(--mc-auth-field-hover);
  }

  .shell.invalid {
    border-color: var(--mc-danger);
  }

  .icon,
  .trailing {
    display: inline-flex;
    align-items: center;
    color: var(--mc-text-subtle);
    flex-shrink: 0;
  }

  input {
    flex: 1;
    min-width: 0;
    background: none;
    border: none;
    outline: none;
    color: var(--mc-text);
    font-size: var(--mc-text-base);
  }

  input::placeholder {
    color: var(--mc-text-subtle);
  }

  /* Chrome's autofill repaints the field white and ignores background-color;
     a long inset shadow is the only reliable override. */
  input:-webkit-autofill,
  input:-webkit-autofill:hover,
  input:-webkit-autofill:focus {
    -webkit-text-fill-color: var(--mc-text);
    box-shadow: 0 0 0 1000px var(--mc-auth-field-hover) inset;
    transition: background-color 100000s ease-in-out 0s;
  }

  .error {
    margin: 0;
    font-size: var(--mc-text-xs);
    color: var(--mc-danger);
  }
</style>
