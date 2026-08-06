import { defineConfig } from 'orval';

/**
 * Generates the typed API client from the committed contract, not from a
 * running server — CI regenerates and fails if the output differs from what is
 * checked in, so a backend change cannot silently break the frontend.
 *
 * NOTE: this has never been run. `contracts/openapi/v1/openapi.yaml` is an
 * empty file, so there is nothing to generate from and `generated/` holds only
 * a `.gitkeep`. Every endpoint is currently a hand-written wrapper under
 * `app/lib/contexts`. The config is kept — and updated to the React client — so
 * that authoring the contract is the only step needed to switch over.
 */
export default defineConfig({
  marketcompass: {
    input: {
      target: '../contracts/openapi/v1/openapi.yaml',
      validation: true
    },
    output: {
      mode: 'tags-split',
      target: './app/lib/shared/api/generated/endpoints.ts',
      schemas: './app/lib/shared/api/generated/models',
      client: 'react-query',
      httpClient: 'fetch',
      clean: true,
      prettier: true,
      override: {
        mutator: {
          path: './app/lib/shared/api/client.ts',
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
