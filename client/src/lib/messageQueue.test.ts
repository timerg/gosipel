import { describe, it, expect } from "vitest";
import { MessageQueue } from "./messageQueue";
import { Message } from "@/hooks/useChat";

const user = (id: number, content = "hi"): Message => ({ id, role: "user", content });
const asst = (id: number, content = "hello"): Message => ({ id, role: "assistant", content });

describe("MessageQueue.make", () => {
  it("returns an empty array", () => {
    expect(MessageQueue.make()).toEqual([]);
  });
});

describe("MessageQueue.add", () => {
  it("adds a message to an empty queue", () => {
    const result = MessageQueue.add([], user(1));
    expect(result).toEqual([user(1)]);
  });

  it("prepends a message with a higher id (newest first)", () => {
    const queue = [user(1)];
    const result = MessageQueue.add(queue, user(2));
    expect(result).toEqual([user(2), user(1)]);
  });

  it("appends a message with a lower id (oldest last)", () => {
    const queue = [user(2)];
    const result = MessageQueue.add(queue, user(1));
    expect(result).toEqual([user(2), user(1)]);
  });

  it("inserts a message in the correct position between two messages", () => {
    const queue = [user(3), user(1)];
    const result = MessageQueue.add(queue, user(2));
    expect(result).toEqual([user(3), user(2), user(1)]);
  });

  it("merges content when id and role match", () => {
    const queue = [asst(1, "Hello")];
    const result = MessageQueue.add(queue, asst(1, ", world"));
    expect(result).toEqual([asst(1, "Hello, world")]);
  });

  it("does not merge when id matches but role differs", () => {
    const queue = [user(1, "Hello")];
    const result = MessageQueue.add(queue, asst(1, "Reply"));
    // different roles with same id: asst(1) > user(1) not applicable — same id, different role
    // based on the logic: id match but role mismatch → falls to else if (message.id > msg.id)
    // asst(1).id === user(1).id → not greater, goes to else → pushes user(1) and asst(1) appended at end
    expect(result.length).toBe(2);
    expect(result.find((m) => m.role === "user")?.content).toBe("Hello");
    expect(result.find((m) => m.role === "assistant")?.content).toBe("Reply");
  });

  it("accumulates multiple stream chunks into one message", () => {
    let queue = MessageQueue.make();
    queue = MessageQueue.add(queue, asst(1, "Hello"));
    queue = MessageQueue.add(queue, asst(1, ", "));
    queue = MessageQueue.add(queue, asst(1, "world"));
    expect(queue).toEqual([asst(1, "Hello, world")]);
  });

  it("does not mutate the original queue", () => {
    const queue = [user(1)];
    const original = [...queue];
    MessageQueue.add(queue, user(2));
    expect(queue).toEqual(original);
  });

  it("handles interleaved user and assistant messages correctly", () => {
    let queue = MessageQueue.make();
    queue = MessageQueue.add(queue, user(1, "first"));
    queue = MessageQueue.add(queue, asst(2, "reply1"));
    queue = MessageQueue.add(queue, user(3, "second"));
    queue = MessageQueue.add(queue, asst(4, "reply2"));
    expect(queue.map((m) => m.id)).toEqual([4, 3, 2, 1]);
    expect(queue.map((m) => m.role)).toEqual(["assistant", "user", "assistant", "user"]);
  });
});
