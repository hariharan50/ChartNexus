import { data, Link, redirect } from 'react-router';
import ComingSoon from '$shared/ui/ComingSoon';
import { retiredSlugTarget, toolBySlug } from './catalog';
import s from './tools.module.css';
import type { Route } from './+types/tool';

export function loader({ params }: Route.LoaderArgs) {
  const tool = toolBySlug(params.tool);
  if (tool) return data({ tool });

  // A slot that has since been built lost its `b<n>` slug; an open tab or a
  // bookmark still points at it. Send it on to what it became.
  const moved = retiredSlugTarget(params.tool);
  if (moved) throw redirect(`/tools/${moved}`);

  // Anything else really is not a tool. A 404 status, but rendered *inside* the
  // terminal shell with a way back to the grid — throwing here would drop the
  // reader onto the root error page, out of the app, for a mistyped URL.
  return data({ tool: null }, { status: 404 });
}

export const meta: Route.MetaFunction = ({ params }) => [
  { title: `${toolBySlug(params.tool)?.name ?? 'Tool'} · ChartNexus` }
];

/** A reserved tool slot. Replaced by the tool's own page as each is built. */
export default function Tool({ loaderData }: Route.ComponentProps) {
  const tool = loaderData.tool;

  if (!tool) {
    return (
      <div className={s.page}>
        <header className={s.head}>
          <h1 className={s.title}>No such tool</h1>
          <p className={s.sub}>
            That address does not match any tool. It may have been renamed when the tool was built.
          </p>
        </header>
        <p>
          <Link to="/tools" className={s.backLink}>
            Back to Tools
          </Link>
        </p>
      </div>
    );
  }

  return <ComingSoon title={tool.name} description={tool.description} />;
}
