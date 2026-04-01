import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useChat } from "./useChat";

// Mock config
vi.mock("@/lib/config", () => ({
  config: { apiHost: "http://localhost:8000" },
}));

function mockFetchJSON(reply: string, status = 200) {
  global.fetch = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    body: true,
    json: async () => ({ reply }),
  } as unknown as Response);
}

function mockFetchStream(chunks: string[]) {
  const encoder = new TextEncoder();
  const lines = chunks.map((c) => `data: ${c}\n\n`).concat("data: [DONE]\n\n");
  const encoded = lines.map((l) => encoder.encode(l));

  let i = 0;
  const reader = {
    read: vi.fn(async () => {
      if (i < encoded.length) return { done: false, value: encoded[i++] };
      return { done: true, value: undefined };
    }),
  };

  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    body: { getReader: () => reader },
  } as unknown as Response);
}

beforeEach(() => {
  vi.clearAllMocks();
});

// ─── MessageQueue ──────────────────────────────────────────────────────────

describe("MessageQueue (via hook state)", () => {
  it("appends a new message to an empty queue", async () => {
    mockFetchJSON("hello");
    const { result } = renderHook(() => useChat());

    await act(async () => {
      result.current.setInput("hi");
      result.current.setStreamMode(false);
    });
    await act(async () => {
      await result.current.sendMessage();
    });

    await waitFor(() => expect(result.current.isProcessing).toBe(false));

    const userMsg = result.current.messages.find((m) => m.role === "user");
    expect(userMsg?.content).toBe("hi");
  });

  it("merges chunks into the same assistant message", async () => {
    mockFetchStream(["Hello", ", world"]);
    const { result } = renderHook(() => useChat());

    await act(async () => {
      result.current.setInput("test");
      result.current.setStreamMode(true);
    });
    await act(async () => {
      await result.current.sendMessage();
    });

    await waitFor(() => expect(result.current.isProcessing).toBe(false));

    const assistantMsg = result.current.messages.find((m) => m.role === "assistant");
    expect(assistantMsg?.content).toBe("Hello, world");
  });
});

// ─── useChat ───────────────────────────────────────────────────────────────

describe("useChat", () => {
  it("initialises with empty state", () => {
    const { result } = renderHook(() => useChat());
    expect(result.current.messages).toEqual([]);
    expect(result.current.input).toBe("");
    expect(result.current.isProcessing).toBe(false);
    expect(result.current.streamMode).toBe(true);
  });

  it("does not send when input is empty", async () => {
    const { result } = renderHook(() => useChat());
    await act(async () => { await result.current.sendMessage(); });
    expect(fetch).not.toHaveBeenCalled();
  });

  it("clears input after sending", async () => {
    mockFetchJSON("response");
    const { result } = renderHook(() => useChat());

    await act(async () => {
      result.current.setInput("hello");
      result.current.setStreamMode(false);
    });
    await act(async () => { await result.current.sendMessage(); });

    expect(result.current.input).toBe("");
  });

  it("sets isProcessing while waiting for response", async () => {
    let resolve!: () => void;
    global.fetch = vi.fn().mockReturnValue(
      new Promise((res) => {
        resolve = () => res({ ok: true, status: 200, body: true, json: async () => ({ reply: "hi" }) });
      })
    );

    const { result } = renderHook(() => useChat());

    await act(async () => {
      result.current.setInput("ping");
      result.current.setStreamMode(false);
    });

    act(() => { result.current.sendMessage(); });
    await waitFor(() => expect(result.current.isProcessing).toBe(true));

    await act(async () => { resolve(); });
    await waitFor(() => expect(result.current.isProcessing).toBe(false));
  });

  it("shows error message on fetch failure", async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error("Network error"));
    const { result } = renderHook(() => useChat());

    await act(async () => {
      result.current.setInput("hello");
      result.current.setStreamMode(false);
    });
    await act(async () => { await result.current.sendMessage(); });

    await waitFor(() => expect(result.current.isProcessing).toBe(false));

    const assistantMsg = result.current.messages.find((m) => m.role === "assistant");
    expect(assistantMsg?.content).toBe("Something went wrong. Please try again.");
  });

  it("shows error message on non-ok HTTP response", async () => {
    mockFetchJSON("", 500);
    const { result } = renderHook(() => useChat());

    await act(async () => {
      result.current.setInput("hello");
      result.current.setStreamMode(false);
    });
    await act(async () => { await result.current.sendMessage(); });

    await waitFor(() => expect(result.current.isProcessing).toBe(false));

    const assistantMsg = result.current.messages.find((m) => m.role === "assistant");
    expect(assistantMsg?.content).toBe("Something went wrong. Please try again.");
  });

  it("sends stream:false when streamMode is off", async () => {
    mockFetchJSON("ok");
    const { result } = renderHook(() => useChat());

    await act(async () => {
      result.current.setInput("hi");
      result.current.setStreamMode(false);
    });
    await act(async () => { await result.current.sendMessage(); });

    const body = JSON.parse((fetch as ReturnType<typeof vi.fn>).mock.calls[0][1].body);
    expect(body.stream).toBe(false);
  });

  it("sends stream:true when streamMode is on", async () => {
    mockFetchStream(["ok"]);
    const { result } = renderHook(() => useChat());

    await act(async () => {
      result.current.setInput("hi");
      result.current.setStreamMode(true);
    });
    await act(async () => { await result.current.sendMessage(); });

    const body = JSON.parse((fetch as ReturnType<typeof vi.fn>).mock.calls[0][1].body);
    expect(body.stream).toBe(true);
  });
});
