/**
 * Svelte compiled `<style>` blocks into the component. React Router / Vite
 * import them as CSS Modules instead, and `verbatimModuleSyntax` + `strict`
 * need this declaration for `import s from './Thing.module.css'` to typecheck.
 *
 * `localsConvention: 'camelCase'` (vite.config.ts) means a `.badge-ico` rule is
 * reachable as `s.badgeIco`; the CSS file itself keeps the kebab-case name so
 * style blocks copy over from Svelte unedited.
 */
declare module '*.module.css' {
  const classes: Readonly<Record<string, string>>;
  export default classes;
}
