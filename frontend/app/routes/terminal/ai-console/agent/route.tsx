import { useEffect, useRef, useState, type MutableRefObject } from 'react';
import { streamAgent, type AgentStreamEvent } from '$contexts/signals/api';
import { loadChat, saveChat } from '$contexts/signals/chat-store';
import { useAgentAvailabilityQuery } from '$contexts/signals/queries';
import type { ChatMessage, ChatTool } from '$contexts/signals/types';
import { useUser } from '$contexts/identity/use-session';
import { cx } from '$shared/ui/cx';
import { INSTRUMENTS, SUGGESTIONS, nextId } from '../ai-console-data';
import ConsoleHeader from '../components/ConsoleHeader';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [
  { title: 'Hella · AI Analysis Agent · MarketCompass' }
];

/** The agent's name, shown throughout the console. */
const AGENT_NAME = 'Hella';

export default function AiAnalysisAgent() {
  const [instIdx, setInstIdx] = useState(0);
  const instrument = INSTRUMENTS[instIdx] ?? INSTRUMENTS[0];
  const availability = useAgentAvailabilityQuery();
  // Scopes the persisted chat to this user so a shared browser never crosses
  // conversations; `anon` only occurs before the profile loads on a guarded page.
  const userId = useUser()?.id ?? 'anon';
  // The console is LLM-only: with no key configured, show a notice instead of a
  // chat that could only ever fail.
  const disabled = availability.data?.available === false;

  return (
    <div className={s.page}>
      <ConsoleHeader
        title="AI Analysis Agent"
        subtitle={
          <>
            Ask <strong>{AGENT_NAME}</strong> — an independent markets analyst who reads the live
            tape over OI, price action, levels and risk.
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
              The AI Console needs a language model to run. Configure an LLM key (
              <code>MC_LLM_PROVIDER=anthropic</code> and <code>MC_LLM_ANTHROPIC_API_KEY</code>) on
              the backend, then reload.
            </p>
          </div>
        ) : (
          /* Keyed by user+symbol: each instrument keeps its own conversation
             (a NIFTY thread means nothing on BANKNIFTY), and a different signed-in
             user re-initialises from their own stored chat. */
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
  // Rehydrate today's conversation for this user+instrument (empty if none).
  const [restored] = useState(() => loadChat(userId, symbol));
  const [messages, setMessages] = useState<ChatMessage[]>(restored.messages);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  // A ref, not state: the id must be readable inside the stream closure without
  // re-running it, and it never needs to trigger a render.
  const sessionRef = useRef<string | null>(restored.sessionId);

  // Persist once a turn settles (not per streamed token). `busy` flipping false
  // is the signal a turn finished; the session id is set by then.
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
      await streamAgent(symbol, trimmed, sessionRef.current, (event) => {
        applyEvent(agentId, event, patch, sessionRef);
      });
    } catch {
      patch(agentId, (msg) => ({
        ...msg,
        text: msg.text || 'Sorry — I could not reach the guider just now.',
        streaming: false
      }));
    } finally {
      // A stream that closed without a `done`/`error` frame still ends the turn.
      patch(agentId, (msg) => (msg.streaming ? { ...msg, streaming: false } : msg));
      setBusy(false);
    }
  }

  return (
    <div className={cx(s.panel, s.chat)}>
      <div className={s.chatHead}>
        <span className={s.avatar}>H</span>
        <div>
          <div className={s.chatName}>{AGENT_NAME}</div>
          <div className={s.chatSub}>Soft-spoken guide · {symbol}</div>
        </div>
      </div>

      <div className={s.messages}>
        {messages.length === 0 ? (
          <p className={s.empty}>
            Hi, I&apos;m {AGENT_NAME}. Ask me about the call, your stop, the target, or which levels
            matter for {symbol} — I&apos;ll read the tape and walk you through it gently.
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
          placeholder={`Ask ${AGENT_NAME}…`}
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
  event: AgentStreamEvent,
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
      patch(agentId, (msg) => ({ ...msg, text: event.message, streaming: false }));
      break;
  }
}

function applyTool(
  tools: ChatTool[],
  event: Extract<AgentStreamEvent, { type: 'tool' }>
): ChatTool[] {
  if (event.status === 'started') {
    return [...tools, { name: event.name, title: event.title ?? 'Working', done: false }];
  }
  // Mark the most recent open chip for this tool as finished.
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

function Bubble({ msg }: { msg: ChatMessage }) {
  const isAgent = msg.role === 'agent';
  const empty = msg.text.length === 0;
  const noTools = !msg.tools || msg.tools.length === 0;
  const noSkills = !msg.skills || msg.skills.length === 0;
  // A brand-new agent turn with nothing yet reads as "thinking".
  const thinking = isAgent && msg.streaming && empty && noTools && noSkills;

  return (
    <div className={cx(s.bubble, s[msg.role], thinking && s.thinking)}>
      {isAgent ? <div className={s.author}>{AGENT_NAME}</div> : null}

      {isAgent && msg.skills && msg.skills.length > 0 ? (
        <div className={s.skills}>
          <span className={s.skillsLabel}>Skills</span>
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
        <div className={s.bubbleText}>{AGENT_NAME} is reading the tape…</div>
      ) : (
        <div className={s.bubbleText}>
          {msg.text}
          {isAgent && msg.streaming ? <span className={s.caret} aria-hidden="true" /> : null}
        </div>
      )}
    </div>
  );
}
