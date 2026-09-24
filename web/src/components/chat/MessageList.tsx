import { useLayoutEffect, useRef } from "react";

import type { ChatMessage } from "../../types/api";
import { isNearBottom, scrollToBottomIfFollowing } from "./autoScroll";
import { MessageBubble } from "./MessageBubble";

interface MessageListProps {
  messages: ChatMessage[];
}

export function MessageList({ messages }: MessageListProps) {
  const listRef = useRef<HTMLDivElement>(null);
  const shouldFollowRef = useRef(true);
  const previousMessageIdsRef = useRef("");
  const messageIds = messages.map((message) => message.id).join("\u0000");

  useLayoutEffect(() => {
    if (previousMessageIdsRef.current !== messageIds) {
      previousMessageIdsRef.current = messageIds;
      shouldFollowRef.current = true;
    }

    scrollToBottomIfFollowing(listRef.current, shouldFollowRef.current);
  }, [messages, messageIds]);

  function updateFollowState(): void {
    const list = listRef.current;
    if (list) shouldFollowRef.current = isNearBottom(list);
  }

  return (
    <div
      ref={listRef}
      className="message-list"
      aria-live="polite"
      onScroll={updateFollowState}
    >
      {messages.map((m) => (
        <MessageBubble key={m.id} message={m} />
      ))}
    </div>
  );
}
