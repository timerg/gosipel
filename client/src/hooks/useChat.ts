import { useState, useRef, useEffect } from "react";
import { config } from "@/lib/config";

export type Message = {
  id: number;
  role: "user" | "assistant";
  content: string;
  stop_reason?: "length" | "end_of_turn" | string;
};

/**
 * This queue should be sorted by Message.id, which is a timestamp. When a new message chunk arrives, it should be appended to the start of the queue if its id is greater than the last message, merged with the existing message if its id matches or inserted in the correct position if its id is in between.
 */
const MessageQueue = {
  make: () => [],
  add: (queue: Message[], message: Message) => {
    let newQueue: Message[] = [...queue];
    let i = 0

    while (i < queue.length) {
      const msg = queue[i];
      if (msg.id === message.id && msg.role === message.role) {
        newQueue[i] = {
          ...msg,
          content: msg.content + message.content,
        };
        if (message.stop_reason) {
          newQueue[i].stop_reason = message.stop_reason;
        };

        break;
      } else if (message.id > msg.id) {
        newQueue.splice(i, 0, message);
        break;
      } else {
        i++;
      }
    }

    if (i === queue.length) {
      newQueue.push(message);
    }

    return newQueue
  },

  addJson: (queue: Message[], messageId: number, json: any) => {
    const content: string = json.content ?? "";
    const stop_reason: string | undefined = json.stop_reason ?? undefined;
    return MessageQueue.add(queue, { id: messageId, role: "assistant", content, stop_reason });
  }
}


// Pure: splits accumulated buffer into complete SSE events and a leftover remainder
function splitSSEBuffer(buffer: string): { events: string[]; remainder: string } {
  const parts = buffer.split("\n\n");
  const remainder = parts.pop() ?? "";
  return { events: parts, remainder };
}

// Pure: extracts data lines and stop_reason from a single SSE event block
type SSEEvent = { data: string | null; stop_reason: string | null };
function parseSSEEvent(event: string): SSEEvent {
  const lines = event.split("\n");

  const data = lines
    .filter((l) => l.startsWith("data: "))
    .map((l) => l.slice(6))
    .join("\n") || "\n";

  const stopLine = lines.find((l) => l.startsWith("stop_reason: "));
  const stop_reason = stopLine ? stopLine.slice(13).trim() : null;

  return { data, stop_reason };
}

// Pure: parses the data payload — response_id events are JSON, content is plain text
type SSEData = { response_id?: string; content: string };
function parseSSEData(data: string): SSEData {
  try {
    const json = JSON.parse(data);
    if (json.response_id) return { response_id: json.response_id, content: "" };
  } catch {}
  return { content: data };
}

async function readStream(
  response: Response,
  messageId: number,
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>,
  setPreviousResponseId: React.Dispatch<React.SetStateAction<string | null>>,
) {
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const { events, remainder } = splitSSEBuffer(buffer);
    buffer = remainder;

    for (const event of events) {
      const { data, stop_reason } = parseSSEEvent(event);

      if (stop_reason) {
        setMessages((prev) => MessageQueue.add(prev, { id: messageId, role: "assistant", content: "", stop_reason }));
        continue;
      }

      if (!data || data === "[DONE]") continue;

      const { response_id, content } = parseSSEData(data);
      if (response_id) {
        setPreviousResponseId(response_id);
      } else {
        setMessages((prev) => MessageQueue.add(prev, { id: messageId, role: "assistant", content }));
      }
    }
  }
}

async function readJSON(
  response: Response,
  messageId: number,
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>,
  setPreviousResponseId: React.Dispatch<React.SetStateAction<string | null>>,
) {
  const json = await response.json();

  if (json.response_id) {
    setPreviousResponseId(json.response_id);
  }

  setMessages((prev) =>
    MessageQueue.addJson(prev, messageId, json)
  );
}

export function useChat() {
  const [messages, setMessages] = useState<Message[]>(MessageQueue.make());
  const [input, setInput] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [streamMode, setStreamMode] = useState(true);
  const [previousResponseId, setPreviousResponseId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function sendMessage() {
    const trimmed = input.trim();
    if (!trimmed || isProcessing) return;

    const messageId = Date.now();

    const userMsg: Message = { id: messageId, role: "user", content: trimmed };
    const assistantMsg: Message = { id: messageId + 1, role: "assistant", content: "" };
    setMessages((prev) => MessageQueue.add(MessageQueue.add(prev, userMsg), assistantMsg));
    setInput("");
    setIsProcessing(true);

    try {
      const response = await fetch(`${config.apiHost}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: [userMsg],
          stream: streamMode,
          ...(previousResponseId ? { previous_response_id: previousResponseId } : {}),
        }),
      });

      if (!response.ok) throw new Error(`HTTP error: ${response.status}`);
      if (!response.body) throw new Error("No response body");

      if (streamMode) {
        await readStream(response, assistantMsg.id, setMessages, setPreviousResponseId);
      } else {
        await readJSON(response, assistantMsg.id, setMessages, setPreviousResponseId);
      }
    } catch (err) {
      console.error("Chat error:", err);
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantMsg.id
            ? { ...msg, content: "Something went wrong. Please try again." }
            : msg
        )
      );
    } finally {
      setIsProcessing(false);
    }
  }

  function newSession() {
    setPreviousResponseId(null);
    setMessages(MessageQueue.make());
  }

  return { messages, input, setInput, sendMessage, isProcessing, streamMode, setStreamMode, newSession, bottomRef };
}
