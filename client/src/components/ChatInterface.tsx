"use client";
import { useRef } from "react";
import MarkdownRenderer from "./MarkdownRenderer";
import { useChat } from "@/hooks/useChat";

export default function ChatInterface() {
  const { messages, input, setInput, sendMessage, isProcessing, bottomRef, streamMode, setStreamMode, newSession } = useChat();
  const editableRef = useRef<HTMLDivElement>(null);
  const isComposingRef = useRef(false);

  function submit() {
    if (!input.trim() || isProcessing) return;
    sendMessage();
    if (editableRef.current) {
      editableRef.current.innerText = "";
    }
  }

  function handleInput() {
    const text = editableRef.current?.innerText ?? "";
    setInput(text.replace(/\r\n/g, "\n").replace(/\r/g, "\n"));
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Enter" && !e.shiftKey && !isComposingRef.current) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <div className="flex h-screen flex-col bg-white dark:bg-zinc-950">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">Chat</h1>
          <button
            onClick={newSession}
            disabled={isProcessing}
            className="rounded-full border border-zinc-300 px-3 py-1 text-xs text-zinc-500 transition-colors hover:border-zinc-500 hover:text-zinc-900 disabled:opacity-40 dark:border-zinc-700 dark:text-zinc-400 dark:hover:border-zinc-400 dark:hover:text-zinc-100"
          >
            New session
          </button>
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-sm text-zinc-500 dark:text-zinc-400">
          <span>Stream</span>
          <div className="relative">
            <input
              type="checkbox"
              className="sr-only"
              checked={streamMode}
              onChange={(e) => setStreamMode(e.target.checked)}
            />
            <div className={`h-5 w-9 rounded-full transition-colors ${streamMode ? "bg-zinc-900 dark:bg-zinc-100" : "bg-zinc-300 dark:bg-zinc-700"}`} />
            <div className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform dark:bg-zinc-900 ${streamMode ? "translate-x-4" : "translate-x-0.5"}`} />
          </div>
        </label>
      </header>

      {/* Message list */}
      <main className="flex-1 overflow-y-auto px-4 py-6">
        <div className="mx-auto flex max-w-2xl flex-col-reverse gap-4">
          <div ref={bottomRef} />
          {messages.length === 0 && (
            <p className="text-center text-sm text-zinc-400 dark:text-zinc-500">Start a conversation below.</p>
          )}
          {messages.map((msg) => (
            <div key={msg.id} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[75%] rounded-2xl px-4 py-2 text-sm leading-relaxed ${
                  msg.role === "user"
                    ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                    : "bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100"
                }`}
              >
                {msg.role === "user"
                  ? <span className="whitespace-pre-wrap">{msg.content}</span>
                  : <MarkdownRenderer content={msg.content} />
                }
              </div>
            </div>
          ))}
        </div>
      </main>

      {/* Input */}
      <footer className="border-t border-zinc-200 px-4 py-4 dark:border-zinc-800">
        <div className="mx-auto flex max-w-2xl items-end gap-2">
          <div
            ref={editableRef}
            contentEditable
            suppressContentEditableWarning
            role="textbox"
            aria-multiline="true"
            aria-placeholder="Type a message... (Shift+Enter for new line)"
            onInput={handleInput}
            onKeyDown={handleKeyDown}
            onCompositionStart={() => { isComposingRef.current = true; }}
            onCompositionEnd={() => {
              isComposingRef.current = false;
              handleInput();
            }}
            className="relative flex-1 cursor-text overflow-y-auto rounded-2xl border border-zinc-300 bg-white px-4 py-2 text-sm outline-none focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 dark:focus:border-zinc-400 empty:before:pointer-events-none empty:before:text-zinc-400 empty:before:content-[attr(aria-placeholder)] dark:empty:before:text-zinc-500"
            style={{ minHeight: "40px", maxHeight: "120px" }}
          />
          <button
            onClick={submit}
            disabled={!input.trim() || isProcessing}
            className="self-end rounded-full bg-zinc-900 px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-zinc-700 disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
          >
            Send
          </button>
        </div>
      </footer>
    </div>
  );
}
