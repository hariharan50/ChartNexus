<script lang="ts">
  import TextField from './TextField.svelte';
  import IconPhone from './icons/IconPhone.svelte';
  import { normalisePhoneDigits } from '$shared/validation/phone';

  /**
   * An Indian mobile number field.
   *
   * `value` holds the ten national digits — the country code is fixed at +91
   * and shown as a prefix rather than typed, so there is nothing to strip and
   * no way to enter a number the backend would reject on its dialling code.
   */
  interface Props {
    label?: string;
    value: string;
    error?: string | undefined;
    required?: boolean;
  }

  let {
    label = 'Phone number',
    value = $bindable(''),
    error = undefined,
    required = false
  }: Props = $props();

  const NATIONAL_LENGTH = 10;

  /**
   * Keep the bound value to bare digits whatever gets typed or pasted — a
   * pasted "+91 98765 43210" should land as "9876543210" rather than be
   * rejected for containing spaces.
   */
  function onInput(event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    const digits = normalisePhoneDigits(input.value).slice(0, NATIONAL_LENGTH);
    value = digits;
    // The bound value may be unchanged (typing a letter), in which case Svelte
    // will not re-render and the stray character would stay on screen.
    input.value = digits;
  }
</script>

<TextField
  {label}
  {value}
  {error}
  {required}
  type="tel"
  inputmode="numeric"
  autocomplete="tel-national"
  placeholder="9876543210"
  maxlength={NATIONAL_LENGTH}
  oninput={onInput}
>
  {#snippet icon()}
    <IconPhone />
  {/snippet}

  {#snippet leading()}
    +91
  {/snippet}
</TextField>
