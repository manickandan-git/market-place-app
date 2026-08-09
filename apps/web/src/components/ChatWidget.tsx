"use client";

import { useRef, useState, useTransition } from "react";

import { sendChatMessageAction, type ChatMessage } from "@/lib/actions/chat";
import { buttonPrimary, input as inputClass } from "@/lib/ui";

const GREETING =
  "Hi! I can help you find products, check stock, look up your orders, or add something to your cart. What are you looking for?";

export function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const listRef = useRef<HTMLDivElement>(null);

  function scrollToBottom() {
    queueMicrotask(() => {
      listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
    });
  }

  function send() {
    const text = draft.trim();
    if (!text || isPending) {
      return;
    }

    // The greeting above is a static local-only bubble, never part of the
    // history sent to the backend — the Messages API requires the first
    // turn to be "user", and this keeps that invariant regardless of how
    // many turns follow.
    const nextMessages: ChatMessage[] = [...messages, { role: "user", content: text }];
    setMessages(nextMessages);
    setDraft("");
    setError(null);
    scrollToBottom();

    startTransition(async () => {
      const result = await sendChatMessageAction(nextMessages);
      if (!result.ok) {
        setError(result.error ?? "Something went wrong.");
        return;
      }
      setMessages((previous) => [
        ...previous,
        { role: "assistant", content: result.reply ?? "" },
      ]);
      scrollToBottom();
    });
  }

  return (
    <div className="fixed bottom-5 right-5 z-20 flex flex-col items-end gap-3">
      {open ? (
        <div className="flex h-[32rem] w-80 flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-lg sm:w-96">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <span className="text-sm font-semibold text-foreground">
              Marketplace Assistant
            </span>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Close chat"
              className="rounded-full p-1 text-foreground/60 transition-colors hover:bg-muted hover:text-foreground"
            >
              <CloseIcon />
            </button>
          </div>

          <div ref={listRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
            <ChatBubble role="assistant" content={GREETING} />
            {messages.map((message, index) => (
              <ChatBubble key={index} role={message.role} content={message.content} />
            ))}
            {isPending ? (
              <div className="mr-auto max-w-[85%] rounded-2xl rounded-bl-sm bg-muted px-3.5 py-2 text-sm text-muted-foreground">
                Thinking…
              </div>
            ) : null}
            {error ? (
              <div className="mr-auto max-w-[85%] rounded-2xl rounded-bl-sm bg-danger/10 px-3.5 py-2 text-sm text-danger">
                {error}
              </div>
            ) : null}
          </div>

          <form
            onSubmit={(event) => {
              event.preventDefault();
              send();
            }}
            className="flex items-center gap-2 border-t border-border px-3 py-3"
          >
            <input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="Ask about products, orders, stock…"
              className={inputClass + " flex-1"}
              disabled={isPending}
            />
            <button
              type="submit"
              disabled={isPending || !draft.trim()}
              className={buttonPrimary + " !px-4"}
            >
              Send
            </button>
          </form>
        </div>
      ) : null}

      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-label={open ? "Close chat" : "Open chat"}
        className="flex h-14 w-14 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg transition-all hover:bg-primary-hover hover:shadow-xl active:scale-95"
      >
        {open ? <CloseIcon /> : <ChatIcon />}
      </button>
    </div>
  );
}

function ChatBubble({ role, content }: { role: "user" | "assistant"; content: string }) {
  return (
    <div
      className={
        role === "user"
          ? "ml-auto max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-3.5 py-2 text-sm text-primary-foreground"
          : "mr-auto max-w-[85%] rounded-2xl rounded-bl-sm bg-muted px-3.5 py-2 text-sm text-foreground"
      }
    >
      {content}
    </div>
  );
}

function ChatIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-6 w-6"
      aria-hidden="true"
    >
      <path d="M4 5.5h16a1 1 0 0 1 1 1V16a1 1 0 0 1-1 1H9l-4.5 3.8V17H4a1 1 0 0 1-1-1V6.5a1 1 0 0 1 1-1Z" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-5 w-5"
      aria-hidden="true"
    >
      <path d="M6 6l12 12M18 6 6 18" />
    </svg>
  );
}
