import { redirect } from 'react-router';

/**
 * Landing spot for Options Lab modules that have been removed.
 *
 * Deleting a route outright is not enough: an open tab, a bookmark or a
 * browser-history entry still points at the old address, and an unmatched URL
 * throws the reader onto the *root* error page — out of the terminal shell
 * entirely. Same reasoning as the retired `b<n>` tool slugs in
 * `routes/terminal/tools/tool.tsx`; these modules simply went away rather than
 * being renamed, so there is nothing more specific to aim at than the Lab.
 */
export function loader() {
  throw redirect('/options', 301);
}

// Registered at every retired path, so the redirect above is all there is. The
// component never renders — the loader always throws first.
export default function RetiredOptionsModule() {
  return null;
}
