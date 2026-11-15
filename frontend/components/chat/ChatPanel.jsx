import React, { useRef, useEffect, useState } from 'react';
import { X, Send, RotateCcw, Flame, Bot, Loader2 } from 'lucide-react';
import { useChat } from '../../context/ChatContext';
import ChatMessage from './ChatMessage';
import SuggestedQuestions from './SuggestedQuestions';

export default function ChatPanel({ onExecuteAction }) {
  const {
    messages,
    pending,
    error,
    isOpen,
    closeChat,
    sendMessage,
    clearSession,
  } = useChat();

  const [input, setInput] = useState('');
  const scrollRef = useRef(null);
  const inputRef = useRef(null);

  // Auto-scroll to bottom of message list
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, pending]);

  // Focus textarea when panel opens
  useEffect(() => {
    if (isOpen && inputRef.current) {
      setTimeout(() => inputRef.current?.focus(), 150);
    }
  }, [isOpen]);

  // Keyboard escape key listener
  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === 'Escape' && isOpen) {
        closeChat();
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, closeChat]);

  const handleSubmit = (e) => {
    e?.preventDefault();
    if (!input.trim() || pending) return;
    sendMessage(input.trim());
    setInput('');
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleExecuteAction = (action) => {
    if (action?.type === 'show_on_map') {
      closeChat();
    }
    if (onExecuteAction) {
      onExecuteAction(action);
    }
  };

  return (
    <>
      {/* Overlay Backdrop */}
      <div
        className={`chat-drawer-backdrop ${isOpen ? 'open' : ''}`}
        onClick={closeChat}
        aria-hidden="true"
      />

      {/* Main Drawer Panel */}
      <aside
        className={`chat-drawer-panel ${isOpen ? 'open' : ''}`}
        role="dialog"
        aria-label="Active Fire AI Assistant"
        aria-modal="true"
      >
        {/* Header */}
        <header className="chat-drawer-header">
          <div className="header-title-block">
            <div className="mark-badge">
              <Flame size={18} />
            </div>
            <div>
              <h3>SpectraFuse Intelligence</h3>
              <p>NASA FIRMS Satellite Reasoning</p>
            </div>
          </div>

          <div className="header-actions-block">
            <button
              type="button"
              className="button button-ghost-icon"
              title="Reset conversation (New Chat)"
              onClick={clearSession}
              aria-label="Reset conversation"
            >
              <RotateCcw size={15} />
            </button>
            <button
              type="button"
              className="button button-ghost-icon"
              title="Close assistant (Esc)"
              onClick={closeChat}
              aria-label="Close assistant"
            >
              <X size={17} />
            </button>
          </div>
        </header>

        {/* Message Thread Body */}
        <div
          className="chat-drawer-body"
          ref={scrollRef}
          role="log"
          aria-live="polite"
          aria-label="Conversation history"
        >
          {messages.length === 0 ? (
            <div className="chat-welcome-state">
              <div className="welcome-icon">
                <Bot size={36} />
              </div>
              <h4>Ask About Satellite Fire Activity</h4>
              <p>
                Analyze 25 years of MODIS & VIIRS active-fire detections, historical anomalies,
                regional calibrations, and geospatial hotspot coordinates.
              </p>
              <SuggestedQuestions onSelect={(q) => sendMessage(q)} disabled={pending} />
            </div>
          ) : (
            <div className="messages-list">
              {messages.map((msg, idx) => (
                <ChatMessage
                  key={idx}
                  message={msg}
                  onExecuteAction={handleExecuteAction}
                />
              ))}
              {pending && (
                <div className="chat-message-row assistant-row pending-row">
                  <div className="avatar assistant-avatar">
                    <Loader2 size={15} className="spin-icon" />
                  </div>
                  <div className="message-bubble assistant-bubble pending-bubble">
                    <span>Analyzing satellite observations and computing anomalies…</span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer & Input Form */}
        <footer className="chat-drawer-footer">
          {error && (
            <div className="chat-error-banner" role="alert">
              <span>{error}</span>
            </div>
          )}

          <form className="chat-input-form" onSubmit={handleSubmit}>
            <textarea
              ref={inputRef}
              className="chat-textarea"
              rows={2}
              maxLength={4000}
              value={input}
              placeholder="Ask a question (e.g., 'What was fire activity in August 2021?')..."
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={pending}
              aria-label="Chat query input"
            />
            <div className="input-toolbar">
              <span className="character-count">{input.length} / 4000</span>
              <button
                type="submit"
                className="button chat-send-button"
                disabled={!input.trim() || pending}
                aria-label="Send query"
              >
                {pending ? <Loader2 size={15} className="spin-icon" /> : <Send size={15} />}
                <span>{pending ? 'Analyzing…' : 'Send'}</span>
              </button>
            </div>
          </form>
        </footer>
      </aside>
    </>
  );
}
