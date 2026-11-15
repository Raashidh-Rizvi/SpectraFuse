import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';

const ChatContext = createContext(null);

export function ChatProvider({ children, base = '/api/fire', currentRegion = 'sri-lanka', currentYear = 'all', currentMeasure = 'harmonized', currentExtent = '79.5,5.8,82,10', onDispatchAction }) {
  const [messages, setMessages] = useState([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [isOpen, setIsOpen] = useState(false);
  const [sessionId, setSessionId] = useState(() => {
    try {
      const stored = localStorage.getItem('spectrafuse_session_id');
      if (stored) return stored;
    } catch {}
    const newId = 'sess_' + Math.random().toString(36).substring(2, 11);
    try { localStorage.setItem('spectrafuse_session_id', newId); } catch {}
    return newId;
  });

  const toggleOpen = useCallback(() => setIsOpen(v => !v), []);
  const openChat = useCallback(() => setIsOpen(true), []);
  const closeChat = useCallback(() => setIsOpen(false), []);

  const clearSession = useCallback(async () => {
    try {
      await fetch(`${base}/chat/session/${sessionId}`, { method: 'DELETE' });
    } catch (e) {
      console.warn('Session deletion error', e);
    }
    const newId = 'sess_' + Math.random().toString(36).substring(2, 11);
    try { localStorage.setItem('spectrafuse_session_id', newId); } catch {}
    setSessionId(newId);
    setMessages([]);
    setError('');
  }, [base, sessionId]);

  const sendMessage = useCallback(async (text) => {
    const content = (text || '').trim();
    if (!content || pending) return;

    const userMessage = {
      role: 'user',
      content,
      timestamp: new Date().toISOString(),
    };

    setMessages(prev => [...prev, userMessage]);
    setPending(true);
    setError('');

    try {
      const payload = {
        message: content,
        region: currentRegion,
        session_id: sessionId,
        context: {
          current_year: currentYear === 'all' ? null : String(currentYear),
          sensor_basis: currentMeasure,
          last_bounds: currentExtent,
        },
      };

      const response = await fetch(`${base}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      const result = await response.json();
      if (!response.ok) {
        throw new Error(typeof result.detail === 'string' ? result.detail : 'Assistant analysis failed.');
      }

      const assistantMessage = {
        role: 'assistant',
        content: result.answer || '',
        intent: result.intent || 'general',
        evidence: result.evidence || [],
        calculations: result.calculations || [],
        limitations: result.limitations || [],
        ui_actions: result.ui_actions || [],
        downloads: result.downloads || [],
        period: result.period || null,
        region: result.region || currentRegion,
        timestamp: new Date().toISOString(),
      };

      setMessages(prev => [...prev, assistantMessage]);

      // Automatically dispatch UI action if provided
      if (result.ui_actions && result.ui_actions.length > 0 && onDispatchAction) {
        result.ui_actions.forEach(action => onDispatchAction(action));
      }
    } catch (err) {
      setError(err.message || 'Error communicating with active fire intelligence.');
    } finally {
      setPending(false);
    }
  }, [base, currentRegion, currentYear, currentMeasure, currentExtent, sessionId, pending, onDispatchAction]);

  return (
    <ChatContext.Provider
      value={{
        messages,
        pending,
        error,
        isOpen,
        sessionId,
        toggleOpen,
        openChat,
        closeChat,
        sendMessage,
        clearSession,
      }}
    >
      {children}
    </ChatContext.Provider>
  );
}

export function useChat() {
  const ctx = useContext(ChatContext);
  if (!ctx) {
    throw new Error('useChat must be used within a ChatProvider');
  }
  return ctx;
}
