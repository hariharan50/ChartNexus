import adapter from '@sveltejs/adapter-node';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),

  compilerOptions: {
    // We never compile to custom elements, so the compiler's warning about
    // rest props preventing custom-element prop inference does not apply.
    warningFilter: (warning) => warning.code !== 'custom_element_props_identifier'
  },

  kit: {
    adapter: adapter({ out: 'build' }),

    alias: {
      $app: 'src/lib/app',
      '$app/*': 'src/lib/app/*',
      $contexts: 'src/lib/contexts',
      '$contexts/*': 'src/lib/contexts/*',
      $shared: 'src/lib/shared',
      '$shared/*': 'src/lib/shared/*'
    },

    // The API sets an httpOnly session cookie, so the browser never holds a
    // token and CSRF protection has to be explicit. An empty trustedOrigins
    // list means same-origin only.
    csrf: { trustedOrigins: [] },

    csp: {
      mode: 'auto',
      directives: {
        'default-src': ['self'],
        'script-src': ['self'],
        'style-src': ['self', 'unsafe-inline'],
        'img-src': ['self', 'data:'],
        'connect-src': ['self', 'ws:', 'wss:'],
        'frame-ancestors': ['none'],
        'base-uri': ['self'],
        'form-action': ['self']
      }
    },

    env: { publicPrefix: 'PUBLIC_' },

    typescript: {
      config: (cfg) => {
        cfg.include = [...(cfg.include ?? []), '../tests/**/*.ts'];
        return cfg;
      }
    }
  }
};

export default config;
