import { Message } from "@/hooks/useChat";

export const MessageQueue = {
  make: (): Message[] => [],
  add: (queue: Message[], message: Message): Message[] => {
    let newQueue: Message[] = [];
    let added = false;
    let i = 0;

    while (i < queue.length) {
      const msg = queue[i];
      if (added) {
        newQueue = newQueue.concat(queue.slice(i));
        break;
      }

      if (msg.id === message.id && msg.role === message.role) {
        if (msg.role === message.role) {
          newQueue.push({ ...msg, content: msg.content + message.content });
          added = true;
        } else {
          newQueue.push(msg);
        }
      } else if (message.id > msg.id) {
        newQueue.push(message);
        newQueue.push(msg);
        added = true;
      } else {
        newQueue.push(msg);
      }

      i++;
    }

    if (!added) {
      newQueue = newQueue.concat([message]).concat(queue.slice(i));
    }
    return newQueue;
  },
};
