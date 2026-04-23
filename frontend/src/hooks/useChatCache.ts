import { useState, useCallback, useRef } from 'react';

/**
 * 基于 sessionStorage 的对话消息缓存，切换页面后恢复。
 * T 为消息类型，key 为存储标识。
 */
export function useChatCache<T>(key: string, initial: T[] = []) {
  const [messages, setMessages] = useState<T[]>(() => {
    try {
      const raw = sessionStorage.getItem(key);
      if (raw) {
        const parsed = JSON.parse(raw) as T[];
        return parsed.filter((m: any) => !m.loading);
      }
    } catch { /* ignore */ }
    return initial;
  });

  const messagesRef = useRef(messages);
  messagesRef.current = messages;

  const updateMessages = useCallback((updater: T[] | ((prev: T[]) => T[])) => {
    setMessages((prev) => {
      const next = typeof updater === 'function' ? (updater as (p: T[]) => T[])(prev) : updater;
      try {
        const toSave = next.filter((m: any) => !m.loading);
        sessionStorage.setItem(key, JSON.stringify(toSave));
      } catch { /* quota exceeded */ }
      return next;
    });
  }, [key]);

  const clearCache = useCallback(() => {
    sessionStorage.removeItem(key);
    setMessages(initial);
  }, [key, initial]);

  return { messages, setMessages: updateMessages, clearCache };
}
