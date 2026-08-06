/**
 * Container liveness probe.
 *
 * deploy/docker/frontend.Dockerfile has always curled `/healthz`, but the
 * SvelteKit app had no `+server.ts` anywhere — the probe was hitting the 404
 * page and failing. Three lines fixes it.
 */
export function loader(): Response {
  return new Response('ok', {
    headers: { 'content-type': 'text/plain; charset=utf-8' }
  });
}
