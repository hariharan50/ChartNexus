<script lang="ts">
  import TextField from './TextField.svelte';
  import IconLock from './icons/IconLock.svelte';
  import IconEye from './icons/IconEye.svelte';
  import IconEyeOff from './icons/IconEyeOff.svelte';

  interface Props {
    label?: string;
    value: string;
    placeholder?: string;
    error?: string | undefined;
    autocomplete?: 'current-password' | 'new-password';
    required?: boolean;
  }

  let {
    label = 'Password',
    value = $bindable(''),
    placeholder = 'Enter your password',
    error = undefined,
    autocomplete = 'current-password',
    required = false
  }: Props = $props();

  let revealed = $state(false);
</script>

<TextField
  {label}
  bind:value
  {error}
  {placeholder}
  {required}
  {autocomplete}
  type={revealed ? 'text' : 'password'}
>
  {#snippet icon()}
    <IconLock />
  {/snippet}

  {#snippet trailing()}
    <button
      type="button"
      class="toggle"
      onclick={() => (revealed = !revealed)}
      aria-pressed={revealed}
      aria-label={revealed ? 'Hide password' : 'Show password'}
      tabindex={-1}
    >
      {#if revealed}
        <IconEye />
      {:else}
        <IconEyeOff />
      {/if}
    </button>
  {/snippet}
</TextField>

<style>
  .toggle {
    display: inline-flex;
    align-items: center;
    padding: var(--mc-space-1);
    background: none;
    border: none;
    color: var(--mc-text-subtle);
    cursor: pointer;
  }

  .toggle:hover {
    color: var(--mc-text-muted);
  }
</style>
