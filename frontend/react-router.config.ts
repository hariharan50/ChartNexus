import type { Config } from '@react-router/dev/config';

export default {
  // Server-rendered then hydrated, matching what SvelteKit did. Nothing in this
  // app is prerenderable: every page is behind a session cookie or reads live
  // market data.
  ssr: true,
  appDirectory: 'app'
} satisfies Config;
