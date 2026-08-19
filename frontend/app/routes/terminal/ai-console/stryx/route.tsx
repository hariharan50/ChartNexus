import { useEffect, useRef, useState, type MutableRefObject, type ReactNode } from 'react';
import { streamStryx, type StryxStreamEvent } from '$contexts/signals/api';
import { loadChat, saveChat } from '$contexts/signals/stryx-chat-store';
import { useStryxAvailabilityQuery, useStryxJournalTodayQuery } from '$contexts/signals/queries';
import type { ChatMessage, ChatTool } from '$contexts/signals/types';
import { useUser } from '$contexts/identity/use-session';
import { cx } from '$shared/ui/cx';
import { INSTRUMENTS, nextId } from '../ai-console-data';
import ConsoleHeader from '../components/ConsoleHeader';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'STRYX · Trade Calls · MarketCompass' }];

/** The agent's name, shown throughout the console. */
const AGENT_NAME = 'STRYX';

/** STRYX-flavoured prompts — it hunts setups, it doesn't explain the tape. */
const SUGGESTIONS = [
  'Any setup right now?',
  "Where's the breakout?",
  'Is there an edge?',
  'Scan the OI flow'
] as const;

export default function StryxAgent() {
  const [instIdx, setInstIdx] = useState(0);
  const instrument = INSTRUMENTS[instIdx] ?? INSTRUMENTS[0];
  const availability = useStryxAvailabilityQuery();
  const userId = useUser()?.id ?? 'anon';
  // STRYX is LLM-only: with no key configured, show a notice instead of a chat
  // that could only ever fail.
  const disabled = availability.data?.available === false;

  return (
    <div className={s.page}>
      <ConsoleHeader
        title="STRYX · Trade Calls"
        mark="S"
        subtitle={
          <>
            <strong>{AGENT_NAME}</strong> hunts the setup — entry, stop, target, conviction. It
            calls <strong>NO TRADE</strong> just as fast when there&apos;s no edge.
          </>
        }
        instIdx={instIdx}
        onSelect={setInstIdx}
      />

      <div className={s.wrap}>
        {disabled ? (
          <div className={cx(s.panel, s.notice)}>
            <div className={s.noticeTitle}>{AGENT_NAME} is offline</div>
            <p className={s.noticeBody}>
              STRYX needs a language model to run. Configure an LLM key (
              <code>MC_LLM_PROVIDER=anthropic</code> and <code>MC_LLM_ANTHROPIC_API_KEY</code>) on
              the backend, then reload.
            </p>
          </div>
        ) : (
          <ChatPanel
            key={`${userId}:${instrument.symbol}`}
            userId={userId}
            symbol={instrument.symbol}
          />
        )}
      </div>
    </div>
  );
}

function ChatPanel({ userId, symbol }: { userId: string; symbol: string }) {
  const [restored] = useState(() => loadChat(userId, symbol));
  const [messages, setMessages] = useState<ChatMessage[]>(restored.messages);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const sessionRef = useRef<string | null>(restored.sessionId);
  // The day's LIVE-call budget — refetched after each turn so the chip reflects
  // a call STRYX just issued.
  const journal = useStryxJournalTodayQuery(symbol);

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
      await streamStryx(symbol, trimmed, sessionRef.current, (event) => {
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
      // A turn may have logged a call — refresh the budget chip.
      void journal.refetch();
    }
  }

  const remaining = journal.data?.remaining;
  const cap = journal.data?.cap ?? 2;

  return (
    <div className={cx(s.panel, s.chat)}>
      <div className={s.chatHead}>
        <span className={s.avatar}>S</span>
        <div className={s.chatHeadMeta}>
          <div className={s.chatName}>{AGENT_NAME}</div>
          <div className={s.chatSub}>Opportunity hunter · {symbol}</div>
        </div>
        {remaining != null ? (
          <span
            className={cx(s.budget, remaining === 0 && s.budgetSpent)}
            title="LIVE calls remaining today"
          >
            {remaining}/{cap} LIVE calls left
          </span>
        ) : null}
      </div>

      <div className={s.messages}>
        {messages.length === 0 ? (
          <p className={s.empty}>
            STRYX here. Ask me to scan {symbol} — I&apos;ll read the OI flow, the structure and the
            momentum, and hand you a call with a defined stop, or tell you flat out there&apos;s no
            edge.
          </p>
        ) : (
          messages.map((msg) => <Bubble key={msg.id} msg={msg} />)
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
          placeholder={`Ask ${AGENT_NAME} for a call…`}
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
  event: StryxStreamEvent,
  patch: (id: string, change: (msg: ChatMessage) => ChatMessage) => void,
  sessionRef: MutableRefObject<string | null>
) {
  switch (event.type) {
    case 'session':
      sessionRef.current = event.session_id;
      break;
    case 'styles':
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
      patch(agentId, (msg) => ({ ...msg, text: event.message, streaming: false }));
      break;
  }
}

function applyTool(
  tools: ChatTool[],
  event: Extract<StryxStreamEvent, { type: 'tool' }>
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

/** The call's status, read off the `Status:` line, for the coloured badge. */
type CallStatus = 'live' | 'no-trade' | 'watching';

function callStatus(text: string): CallStatus | null {
  const m = text.match(/^\s*Status\s*:\s*(.+)$/im);
  if (!m || m[1] == null) return null;
  const raw = m[1].trim().toUpperCase();
  if (raw.includes('NO') && raw.includes('TRADE')) return 'no-trade';
  if (raw.startsWith('WATCH')) return 'watching';
  if (raw.startsWith('LIVE')) return 'live';
  return null;
}

const STATUS_LABEL: Record<CallStatus, string> = {
  live: 'LIVE',
  'no-trade': 'NO TRADE',
  watching: 'WATCHING'
};

/**
 * Lightweight, dependency-free markdown for STRYX's replies — `**bold**`,
 * `` `code` `` and `-`/`*` bullets rendered as real elements. Deliberately small.
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
    if (/^\s*[-*]\s+/.test(line)) {
      flushPara();
      (list ??= []).push(line.replace(/^\s*[-*]\s+/, ''));
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

function Bubble({ msg }: { msg: ChatMessage }) {
  const isAgent = msg.role === 'agent';
  const empty = msg.text.length === 0;
  const noTools = !msg.tools || msg.tools.length === 0;
  const noSkills = !msg.skills || msg.skills.length === 0;
  const thinking = isAgent && msg.streaming && empty && noTools && noSkills;
  const status = isAgent && !empty ? callStatus(msg.text) : null;

  return (
    <div className={cx(s.bubble, s[msg.role], thinking && s.thinking)}>
      {isAgent ? (
        <div className={s.author}>
          {AGENT_NAME}
          {status ? (
            <span className={cx(s.status, s[`status_${status.replace('-', '')}`])}>
              {STATUS_LABEL[status]}
            </span>
          ) : null}
        </div>
      ) : null}

      {isAgent && msg.skills && msg.skills.length > 0 ? (
        <div className={s.skills}>
          <span className={s.skillsLabel}>Playbook</span>
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
        <div className={s.bubbleText}>
          {isAgent ? renderRich(msg.text) : msg.text}
          {isAgent && msg.streaming ? <span className={s.caret} aria-hidden="true" /> : null}
        </div>
      )}
    </div>
  );
}
