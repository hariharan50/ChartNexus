<script lang="ts">
  import '../app.css';

  let { children } = $props();
</script>

<a class="mc-skip-link" href="#main">Skip to main content</a>

<main id="main">
  {@render children?.()}
</main>

<style>
  main {
    min-height: 100vh;
  }
</style>
