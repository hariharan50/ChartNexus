/// <reference types="@sveltejs/kit" />

declare global {
  namespace App {
    /**
     * Shape of the RFC 9457 problem document the API returns for every error.
     * `message` is required by SvelteKit itself; `detail` carries the same text
     * under the name the API and the rest of the client use.
     */
    interface Error {
      message: string;
      code: string;
      detail: string;
      requestId?: string;
    }

    /**
     * Set by hooks.server.ts. The authenticated principal is deliberately not
     * here: the session cookie is opaque to SvelteKit and only the API can
     * resolve it, so `(terminal)/+layout.ts` fetches the user instead.
     */
    interface Locals {
      requestId: string;
    }

    interface PageData {
      user?: import('$contexts/identity/types').User;
    }

    interface PageState {}

    interface Platform {}
  }
}

export {};
