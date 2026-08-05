<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { HTMLInputAttributes } from 'svelte/elements';

  interface Props extends Omit<HTMLInputAttributes, 'value'> {
    label: string;
    value: string;
    error?: string | undefined;
    /** Leading glyph, rendered decoratively inside the field. */
    icon?: Snippet;
    /**
     * Leading content that carries meaning — a country code, a currency
     * symbol. Unlike `icon` it is not `aria-hidden`, because a screen reader
     * has to announce it to make sense of what is typed.
     */
    leading?: Snippet;
    /** Trailing control, e.g. a password reveal toggle. */
    trailing?: Snippet;
  }

  let {
    label,
    value = $bindable(''),
    error = undefined,
    icon,
    leading,
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

    {#if leading}
      <span class="leading">{@render leading()}</span>
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
    background: var(--mc-field-bg);
    border: 1px solid var(--mc-field-border);
    border-radius: var(--mc-radius);
    transition:
      border-color var(--mc-duration-fast) ease,
      background var(--mc-duration-fast) ease;
  }

  .shell:hover {
    background: var(--mc-field-bg-hover);
  }

  .shell:focus-within {
    border-color: var(--mc-brand);
    background: var(--mc-field-bg-hover);
  }

  .shell.invalid {
    border-color: var(--mc-danger);
  }

  .icon,
  .leading,
  .trailing {
    display: inline-flex;
    align-items: center;
    color: var(--mc-text-subtle);
    flex-shrink: 0;
  }

  /* Sits against the input, separated by a rule, so it reads as part of the
     value rather than as another piece of chrome. */
  .leading {
    padding-right: var(--mc-space-2);
    border-right: 1px solid var(--mc-field-border);
    color: var(--mc-text-muted);
    font-size: var(--mc-text-base);
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
    box-shadow: 0 0 0 1000px var(--mc-field-bg-hover) inset;
    transition: background-color 100000s ease-in-out 0s;
  }

  .error {
    margin: 0;
    font-size: var(--mc-text-xs);
    color: var(--mc-danger);
  }
</style>
