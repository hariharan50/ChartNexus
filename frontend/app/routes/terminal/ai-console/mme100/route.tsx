import { useEffect, useRef, useState, type MutableRefObject, type ReactNode } from 'react';
import { Link } from 'react-router';
import { streamMme100 } from '$contexts/mme100/api';
import { downloadReport } from '$contexts/report/api';
import { loadChat, saveChat } from '$contexts/mme100/chat-store';
import { useMme100AvailabilityQuery, useMme100BriefingTodayQuery } from '$contexts/mme100/queries';
import type { Mme100Briefing, Mme100StreamEvent } from '$contexts/mme100/types';
import type { ChatMessage, ChatTool } from '$contexts/signals/types';
import { useUser } from '$contexts/identity/use-session';
import { cx } from '$shared/ui/cx';
import { INSTRUMENTS, nextId } from '../ai-console-data';
import AgentInfoWindow from '../components/AgentInfoWindow';
import ConsoleHeader from '../components/ConsoleHeader';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [
  { title: 'MME100 · Market Analysis · MarketCompass' }
];

/** The agent's name, shown throughout the console. */
const AGENT_NAME = 'MME100';

/** MME100-flavoured prompts — it analyses the whole pre-market setup. */
const SUGGESTIONS = [
  'Pre-market outlook?',
  'Key levels today?',
  'Global cues?',
  'Which sectors are in focus?'
] as const;

export default function Mme100Agent() {
  const [instIdx, setInstIdx] = useState(0);
  const [infoOpen, setInfoOpen] = useState(false);
  const instrument = INSTRUMENTS[instIdx] ?? INSTRUMENTS[0];
  const availability = useMme100AvailabilityQuery();
  const userId = useUser()?.id ?? 'anon';
  // MME100 is LLM-only: with no key configured, show a notice instead of a chat
  // that could only ever fail.
  const disabled = availability.data?.available === false;

  return (
    <div className={s.page}>
      <ConsoleHeader
        title="MME100 · Market Analysis"
        mark="M"
        subtitle={
          <>
            <strong>{AGENT_NAME}</strong> — Market Made Easy 100%. The pre-market desk: global cues,
            the day&apos;s India setup, sectors, stocks and risks.
          </>
        }
        instIdx={instIdx}
        onSelect={setInstIdx}
        onInfo={() => setInfoOpen(true)}
      />

      {infoOpen ? <AgentInfoWindow agent="mme100" onClose={() => setInfoOpen(false)} /> : null}

      <div className={s.wrap}>
        {disabled ? (
          <div className={cx(s.panel, s.notice)}>
            <div className={s.noticeTitle}>{AGENT_NAME} is offline</div>
            <p className={s.noticeBody}>
              MME100 runs on your own LLM key. Add one in{' '}
              <Link to="/settings/ai">Settings → AI</Link>, then reload.
            </p>
          </div>
        ) : (
          <>
            <ReportDownload symbol={instrument.symbol} />
            <BriefingCard />
            <ChatPanel
              key={`${userId}:${instrument.symbol}`}
              userId={userId}
              symbol={instrument.symbol}
            />
          </>
        )}
      </div>
    </div>
  );
}

/** On-demand: generate today's full report for the instrument and download the PDF. */
function ReportDownload({ symbol }: { symbol: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);

  async function run() {
    setBusy(true);
    setError(false);
    try {
      await downloadReport(symbol);
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={cx(s.panel, s.reportBar)}>
      <div className={s.reportText}>
        <span className={s.reportTitle}>Daily Report - PDF</span>
        <span className={s.reportSub}>
          {error
            ? "Couldn't generate the report just now - try again."
            : `A branded PDF for ${symbol}: summary, technicals, options & PCR, sentiment and outlook.`}
        </span>
      </div>
      <button type="button" className={s.reportBtn} disabled={busy} onClick={() => void run()}>
        {busy ? 'Generating…' : '⭳ Download PDF'}
      </button>
    </div>
  );
}

/** Today's autonomous pre-market briefing, shown above the chat when present. */
function BriefingCard() {
  const briefing = useMme100BriefingTodayQuery();
  const data: Mme100Briefing | null = briefing.data ?? null;

  if (briefing.isLoading) return null;

  return (
    <div className={cx(s.panel, s.briefing)}>
      <div className={s.briefingHead}>
        <h2 className={s.briefingTitle}>Today&apos;s Pre-Market Briefing</h2>
        {data ? (
          <span className={s.briefingMeta}>
            {data.instruments.join(' · ')}
            {data.source === 'mock' ? ' · simulated' : ''}
          </span>
        ) : null}
      </div>
      {data ? (
        <div className={s.briefingBody}>{renderRich(data.markdown)}</div>
      ) : (
        <p className={s.briefingEmpty}>
          No briefing generated yet today. It runs automatically before the open once enabled in{' '}
          <Link to="/settings/power-agents">Settings → Power AI Agents</Link> — or just ask below
          for a live read.
        </p>
      )}
    </div>
  );
}

function ChatPanel({ userId, symbol }: { userId: string; symbol: string }) {
  const [restored] = useState(() => loadChat(userId, symbol));
  const [messages, setMessages] = useState<ChatMessage[]>(restored.messages);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const sessionRef = useRef<string | null>(restored.sessionId);

  useEffect(() => {
    if (!busy) saveChat(userId, symbol, sessionRef.current, messages);
  }, [busy, messages, userId, symbol]);

  function patch(id: string, change: (msg: ChatMessage) => ChatMessage) {
    setMessages((prev) => prev.map((msg) => (msg.id === id ? change(msg) : msg)));
  }

  async function submit(question: string) {
    const trimmed = question.trim();
    if (!trimmed || busy) return;
    setInput('');
    setBusy(true);

    const agentId = nextId();
    setMessages((prev) => [
      ...prev,
      { id: nextId(), role: 'user', text: trimmed },
      { id: agentId, role: 'agent', text: '', tools: [], streaming: true }
    ]);

    try {
      await streamMme100(symbol, trimmed, sessionRef.current, (event) => {
        applyEvent(agentId, event, patch, sessionRef);
      });
    } catch {
      patch(agentId, (msg) => ({
        ...msg,
        text: msg.text || "Couldn't get a read just now — try again.",
        streaming: false
      }));
    } finally {
      patch(agentId, (msg) => (msg.streaming ? { ...msg, streaming: false } : msg));
      setBusy(false);
    }
  }

  return (
    <div className={cx(s.panel, s.chat)}>
      <div className={s.chatHead}>
        <span className={s.avatar}>M</span>
        <div className={s.chatHeadMeta}>
          <div className={s.chatName}>{AGENT_NAME}</div>
          <div className={s.chatSub}>Pre-market analyst · {symbol}</div>
        </div>
      </div>

      <div className={s.messages}>
        {messages.length === 0 ? (
          <p className={s.empty}>
            MME100 here. Ask me for the pre-market outlook on {symbol} — I&apos;ll read the global
            cues, the India setup, the sectors and stocks in focus, and the day&apos;s risks, with
            concrete levels.
          </p>
        ) : (
          messages.map((msg) => <Bubble key={msg.id} msg={msg} symbol={symbol} />)
        )}
      </div>

      <div className={s.suggestions}>
        {SUGGESTIONS.map((suggestion) => (
          <button
            key={suggestion}
            type="button"
            className={s.suggestion}
            disabled={busy}
            onClick={() => void submit(suggestion)}
          >
            {suggestion}
          </button>
        ))}
      </div>

      <form
        className={s.composer}
        onSubmit={(event) => {
          event.preventDefault();
          void submit(input);
        }}
      >
        <input
          className={s.input}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder={`Ask ${AGENT_NAME} for a read…`}
          aria-label={`Ask ${AGENT_NAME}`}
          maxLength={500}
        />
        <button type="submit" className={s.send} disabled={busy || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}

/** Apply one stream frame to the in-flight agent message. */
function applyEvent(
  agentId: string,
  event: Mme100StreamEvent,
  patch: (id: string, change: (msg: ChatMessage) => ChatMessage) => void,
  sessionRef: MutableRefObject<string | null>
) {
  switch (event.type) {
    case 'session':
      sessionRef.current = event.session_id;
      break;
    case 'skills':
      patch(agentId, (msg) => ({ ...msg, skills: event.titles }));
      break;
    case 'token':
      patch(agentId, (msg) => ({ ...msg, text: msg.text + event.text }));
      break;
    case 'tool':
      patch(agentId, (msg) => ({ ...msg, tools: applyTool(msg.tools ?? [], event) }));
      break;
    case 'done':
      patch(agentId, (msg) => ({ ...msg, streaming: false }));
      break;
    case 'error':
      // Keep whatever already streamed — the error is only the whole message
      // when the turn produced nothing at all.
      patch(agentId, (msg) => ({ ...msg, text: msg.text || event.message, streaming: false }));
      break;
  }
}

function applyTool(
  tools: ChatTool[],
  event: Extract<Mme100StreamEvent, { type: 'tool' }>
): ChatTool[] {
  if (event.status === 'started') {
    return [...tools, { name: event.name, title: event.title ?? 'Working', done: false }];
  }
  let marked = false;
  return [...tools].reverse().reduce<ChatTool[]>((acc, tool) => {
    if (!marked && tool.name === event.name && !tool.done) {
      marked = true;
      acc.unshift({ ...tool, done: true });
    } else {
      acc.unshift(tool);
    }
    return acc;
  }, []);
}

/**
 * Lightweight, dependency-free markdown for MME100's replies and briefings —
 * `**bold**`, `` `code` ``, `-`/`*` bullets, `#`/`##`/`###` headings and `---`
 * rules rendered as real elements. Deliberately small.
 */
function parseInline(text: string, keyBase: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const re = /\*\*(.+?)\*\*|`([^`]+)`/g;
  let last = 0;
  let i = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    if (m[1] != null) {
      nodes.push(
        <strong key={`${keyBase}-b${i}`} className={s.mdStrong}>
          {m[1]}
        </strong>
      );
    } else if (m[2] != null) {
      nodes.push(
        <code key={`${keyBase}-c${i}`} className={s.mdCode}>
          {m[2]}
        </code>
      );
    }
    last = re.lastIndex;
    i++;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

function renderRich(text: string): ReactNode {
  const lines = text.split('\n');
  const blocks: ReactNode[] = [];
  let para: string[] = [];
  let list: string[] | null = null;
  let bk = 0;

  const flushPara = () => {
    if (para.length === 0) return;
    const key = `p${bk++}`;
    const para0 = para;
    blocks.push(
      <p key={key} className={s.mdP}>
        {para0.flatMap((ln, idx) => [
          ...(idx ? [<br key={`${key}-br${idx}`} />] : []),
          ...parseInline(ln, `${key}-${idx}`)
        ])}
      </p>
    );
    para = [];
  };

  const flushList = () => {
    if (!list) return;
    const key = `u${bk++}`;
    const items = list;
    blocks.push(
      <ul key={key} className={s.mdUl}>
        {items.map((it, idx) => (
          <li key={`${key}-${idx}`} className={s.mdLi}>
            {parseInline(it, `${key}-${idx}`)}
          </li>
        ))}
      </ul>
    );
    list = null;
  };

  for (const line of lines) {
    const heading = line.match(/^\s{0,3}(#{1,4})\s+(.*)$/);
    if (/^\s*[-*]\s+/.test(line)) {
      flushPara();
      (list ??= []).push(line.replace(/^\s*[-*]\s+/, ''));
    } else if (/^\s*---+\s*$/.test(line)) {
      flushList();
      flushPara();
      blocks.push(<hr key={`h${bk++}`} className={s.mdHr} />);
    } else if (heading) {
      flushList();
      flushPara();
      blocks.push(
        <div key={`hd${bk++}`} className={s.mdH}>
          {parseInline(heading[2] ?? '', `hd${bk}`)}
        </div>
      );
    } else {
      flushList();
      if (line.trim() === '') flushPara();
      else para.push(line);
    }
  }
  flushList();
  flushPara();
  return blocks;
}

function Bubble({ msg, symbol }: { msg: ChatMessage; symbol: string }) {
  const isAgent = msg.role === 'agent';
  const empty = msg.text.length === 0;
  const noTools = !msg.tools || msg.tools.length === 0;
  const noSkills = !msg.skills || msg.skills.length === 0;
  const thinking = isAgent && msg.streaming && empty && noTools && noSkills;
  // A finished, non-empty agent answer can be exported to PDF.
  const exportable = isAgent && !msg.streaming && !empty;
  const contentRef = useRef<HTMLDivElement>(null);

  return (
    <div className={cx(s.bubble, s[msg.role], thinking && s.thinking)}>
      {isAgent ? <div className={s.author}>{AGENT_NAME}</div> : null}

      {isAgent && msg.skills && msg.skills.length > 0 ? (
        <div className={s.skills}>
          <span className={s.skillsLabel}>Sections</span>
          {msg.skills.map((title) => (
            <span key={title} className={s.skillChip}>
              {title}
            </span>
          ))}
        </div>
      ) : null}

      {isAgent && msg.tools && msg.tools.length > 0 ? (
        <div className={s.tools}>
          {msg.tools.map((tool, index) => (
            <span key={index} className={cx(s.toolChip, tool.done && s.done)}>
              <i className={s.toolDot} />
              {tool.title}
            </span>
          ))}
        </div>
      ) : null}

      {thinking ? (
        <div className={s.bubbleText}>{AGENT_NAME} is on it…</div>
      ) : (
        <div className={s.bubbleText} ref={isAgent ? contentRef : null}>
          {isAgent ? renderRich(msg.text) : msg.text}
          {isAgent && msg.streaming ? <span className={s.caret} aria-hidden="true" /> : null}
        </div>
      )}

      {exportable ? (
        <div className={s.pdfActions}>
          <button
            type="button"
            className={s.pdfBtn}
            title="Download this answer as a PDF"
            onClick={() => {
              const html = contentRef.current?.innerHTML;
              if (html) downloadResponsePdf(html, symbol);
            }}
          >
            ⭳ Download PDF
          </button>
        </div>
      ) : null}
    </div>
  );
}

/** IST date as YYYY-MM-DD — the app's convention, also used for the filename. */
function istDate(): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata' }).format(new Date());
}

/**
 * Export a single MME100 answer to PDF, entirely client-side: write the
 * already-rendered (React-escaped) answer HTML into a hidden iframe with a print
 * stylesheet, then open the browser's print dialog (→ "Save as PDF"). Nothing
 * leaves the browser and no markup beyond our own `renderRich` output is used, so
 * there is no injection or network surface.
 */
function downloadResponsePdf(contentHtml: string, symbol: string): void {
  if (typeof document === 'undefined') return;
  const date = istDate();
  const title = `MME100-${symbol}-${date}`;
  const doc = `<!doctype html><html><head><meta charset="utf-8" />
<title>${title}</title>
<style>
  @page { margin: 0; }
  * { box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  html, body { margin: 0; padding: 0; }
  body { font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
    color: #1f2733; line-height: 1.6; font-size: 11.5pt; }

  /* -- Header band -- */
  .hero { position: relative; overflow: hidden; padding: 34px 44px 40px;
    color: #fff; background: linear-gradient(120deg, #0ea5e9 0%, #10b981 100%); }
  .hero-brand { font-size: 30pt; font-weight: 800; letter-spacing: 3px; margin: 0; }
  .hero-brand span { font-weight: 300; }
  .hero-slogan { margin: 6px 0 0; font-size: 8.5pt; letter-spacing: 7px;
    text-transform: uppercase; opacity: 0.92; }
  /* decorative shapes */
  .sh { position: absolute; border-radius: 50%; opacity: 0.18; background: #fff; }
  .sh1 { width: 190px; height: 190px; top: -70px; right: -40px; }
  .sh2 { width: 90px; height: 90px; bottom: -34px; right: 150px; opacity: 0.12; }
  .dot { position: absolute; width: 16px; height: 16px; border-radius: 50%;
    background: #f59e0b; top: 30px; right: 44px; opacity: 0.95; }
  .ring { position: absolute; width: 54px; height: 54px; border-radius: 50%;
    border: 6px solid rgba(255,255,255,0.5); left: 44px; bottom: -20px; }

  /* -- Title block -- */
  .titlewrap { padding: 30px 44px 6px; }
  .title { margin: 0; font-size: 17pt; font-weight: 800; letter-spacing: 1px; color: #0b7a5b;
    text-transform: uppercase; }
  .subtitle { margin: 6px 0 0; font-size: 10pt; letter-spacing: 4px; color: #64748b;
    text-transform: uppercase; }
  .rule { height: 3px; width: 64px; background: #f59e0b; margin: 14px 44px 0; border-radius: 2px; }

  /* -- Body -- */
  .body { padding: 16px 44px 26px; }
  .body strong { font-weight: 700; color: #0f172a; }
  .body code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.9em;
    background: #eef2f6; border: 1px solid #e2e8f0; border-radius: 3px; padding: 0 3px; }
  .body ul { padding-left: 1.1em; margin: 0.3em 0 0.7em; }
  .body li { margin: 2px 0; }
  .body p { margin: 0 0 0.6em; }
  .body hr { border: 0; border-top: 1px solid #e2e8f0; margin: 1em 0; }

  /* -- Footer band -- */
  .foot { position: relative; overflow: hidden; margin-top: 12px; padding: 18px 44px;
    color: #fff; background: linear-gradient(120deg, #10b981 0%, #0ea5e9 100%); }
  .foot-brand { font-weight: 800; letter-spacing: 1px; font-size: 11pt; margin: 0; }
  .foot-note { margin: 4px 0 0; font-size: 8pt; line-height: 1.5; opacity: 0.95; max-width: 78%; }
  .foot .dot { top: 18px; right: 44px; background: #f59e0b; }
</style></head>
<body>
  <div class="hero">
    <div class="sh sh1"></div>
    <div class="sh sh2"></div>
    <div class="ring"></div>
    <span class="dot"></span>
    <p class="hero-brand">MME<span>100</span></p>
    <p class="hero-slogan">Market Made Easy 100%</p>
  </div>

  <div class="titlewrap">
    <h1 class="title">Pre-Market Analysis · ${symbol}</h1>
    <p class="subtitle">${date}</p>
  </div>
  <div class="rule"></div>

  <div class="body">${contentHtml}</div>

  <div class="foot">
    <span class="dot"></span>
    <p class="foot-brand">MarketCompass</p>
    <p class="foot-note">Educational and informational purposes only — not investment advice.
      Consult a SEBI-registered adviser before investing. Generated ${date}.</p>
  </div>
</body></html>`;

  const frame = document.createElement('iframe');
  frame.setAttribute('aria-hidden', 'true');
  frame.style.position = 'fixed';
  frame.style.right = '0';
  frame.style.bottom = '0';
  frame.style.width = '0';
  frame.style.height = '0';
  frame.style.border = '0';
  document.body.appendChild(frame);

  const win = frame.contentWindow;
  const idoc = frame.contentDocument ?? win?.document;
  if (!win || !idoc) {
    frame.remove();
    return;
  }

  const cleanup = () => {
    // Give the print dialog a beat to open before removing the frame.
    window.setTimeout(() => frame.remove(), 1000);
  };
  win.addEventListener('afterprint', cleanup, { once: true });

  idoc.open();
  idoc.write(doc);
  idoc.close();

  // Let the iframe lay out before printing.
  window.setTimeout(() => {
    win.focus();
    win.print();
  }, 150);
}
