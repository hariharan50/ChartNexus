import SettingsIcon from './components/SettingsIcon';
import s from './help.module.css';
import type { Route } from './+types/help';

export const meta: Route.MetaFunction = () => [{ title: 'Help & Support · Settings · ChartNexus' }];

interface HelpLink {
  glyph: string;
  title: string;
  desc: string;
  href: string;
  external?: boolean;
}

const links: HelpLink[] = [
  {
    glyph: 'book',
    title: 'Documentation',
    desc: 'Guides for options tools, indicators & the terminal',
    href: '#'
  },
  {
    glyph: 'lifebuoy',
    title: 'Contact support',
    desc: 'Reach the team — typically replies within a few hours',
    href: 'mailto:support@chartnexus.app',
    external: true
  },
  {
    glyph: 'bug',
    title: 'Report a bug',
    desc: 'Something off with the data or charts? Let us know',
    href: 'mailto:support@chartnexus.app?subject=Bug%20report',
    external: true
  },
  {
    glyph: 'users',
    title: 'Community',
    desc: 'Join other traders on the ChartNexus channel',
    href: '#'
  }
];

export default function SettingsHelp() {
  return (
    <>
      <h1 className={s.heading}>Help &amp; Support</h1>

      <ul className={s.links}>
        {links.map((link) => (
          <li key={link.title}>
            <a
              className={s.row}
              href={link.href}
              rel={link.external ? 'noopener noreferrer' : undefined}
              target={link.external ? '_blank' : undefined}
            >
              <span className={s.ico}>
                <SettingsIcon name={link.glyph} />
              </span>
              <span className={s.text}>
                <span className={s.title}>{link.title}</span>
                <span className={s.desc}>{link.desc}</span>
              </span>
              <span className={s.chevron}>
                <SettingsIcon name="chevron" />
              </span>
            </a>
          </li>
        ))}
      </ul>
    </>
  );
}
