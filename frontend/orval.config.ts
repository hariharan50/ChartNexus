import { defineConfig } from 'orval';

/**
 * Generates the typed API client from the committed contract, not from a
 * running server — CI regenerates and fails if the output differs from what is
 * checked in, so a backend change cannot silently break the frontend.
 */
export default defineConfig({
  marketcompass: {
    input: {
      target: '../contracts/openapi/v1/openapi.yaml',
      validation: true
    },
    output: {
      mode: 'tags-split',
      target: './src/lib/shared/api/generated/endpoints.ts',
      schemas: './src/lib/shared/api/generated/models',
      client: 'svelte-query',
      httpClient: 'fetch',
      clean: true,
      prettier: true,
      override: {
        mutator: {
          path: './src/lib/shared/api/client.ts',
          name: 'apiFetch'
        },
        query: {
          useQuery: true,
          useInfinite: false,
          signal: true
        }
      }
    },
    hooks: {
      afterAllFilesWrite: 'prettier --write'
    }
  }
});
