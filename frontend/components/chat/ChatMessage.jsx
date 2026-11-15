import React from 'react';
import { Bot, User, MapPin, Download, AlertCircle } from 'lucide-react';
import ProvenanceBadge from './ProvenanceBadge';
import CalculationBreakdown from './CalculationBreakdown';

function escapeHtml(text) {
  if (!text) return '';
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function renderSafeMarkdown(text) {
  if (!text) return null;
  // Strip dangerous script tags completely
  const sanitized = text.replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '');

  const paragraphs = sanitized.split(/\n\n+/);
  return (
    <div className="message-text-body">
      {paragraphs.map((p, pIdx) => {
        const lines = p.split(/\n/);
        return (
          <p key={pIdx}>
            {lines.map((line, lIdx) => {
              // Format bold **text**
              const parts = line.split(/(\*\*[^*]+\*\*)/g);
              const renderedLine = parts.map((part, partIdx) => {
                if (part.startsWith('**') && part.endsWith('**')) {
                  return <strong key={partIdx}>{part.slice(2, -2)}</strong>;
                }
                return part;
              });

              return (
                <React.Fragment key={lIdx}>
                  {renderedLine}
                  {lIdx < lines.length - 1 && <br />}
                </React.Fragment>
              );
            })}
          </p>
        );
      })}
    </div>
  );
}

export default function ChatMessage({ message, onExecuteAction }) {
  const isUser = message.role === 'user';

  if (isUser) {
    return (
      <div className="chat-message-row user-row">
        <div className="message-bubble user-bubble">
          <div className="message-content">{message.content}</div>
        </div>
        <div className="avatar user-avatar" title="You" aria-label="User Avatar">
          <User size={15} />
        </div>
      </div>
    );
  }

  // Assistant response
  const evidenceItems = message.evidence || [];
  const calculations = message.calculations || [];
  const uiActions = message.ui_actions || [];
  const downloads = message.downloads || [];
  const limitations = message.limitations || [];

  return (
    <div className="chat-message-row assistant-row">
      <div className="avatar assistant-avatar" title="SpectraFuse Assistant" aria-label="Assistant Avatar">
        <Bot size={15} />
      </div>

      <div className="message-bubble assistant-bubble">
        {/* Provenance Badges Header */}
        {evidenceItems.length > 0 && (
          <div className="provenance-badges-bar">
            {evidenceItems.map((ev, idx) => (
              <ProvenanceBadge
                key={idx}
                status={ev.status}
                product={ev.product}
                calibrationApplied={ev.calibration_applied}
                coverage={ev.coverage}
              />
            ))}
          </div>
        )}

        {/* Formatted Answer Body */}
        <div className="message-content">
          {renderSafeMarkdown(message.content)}
        </div>

        {/* Step-by-Step Calculations Accordion */}
        {calculations.length > 0 && (
          <CalculationBreakdown calculations={calculations} />
        )}

        {/* Interactive UI Action Dispatchers */}
        {uiActions.length > 0 && (
          <div className="actions-button-row">
            {uiActions.map((action, idx) => (
              <button
                key={idx}
                type="button"
                className="button action-pill-button"
                onClick={() => onExecuteAction && onExecuteAction(action)}
              >
                <MapPin size={13} aria-hidden="true" />
                <span>Show On Map ({action.payload?.start || 'Selected Period'})</span>
              </button>
            ))}
          </div>
        )}

        {/* CSV Downloads */}
        {downloads.length > 0 && (
          <div className="downloads-button-row">
            {downloads.map((dl, idx) => (
              <a
                key={idx}
                href={dl.url}
                className="button download-pill-button"
                download
              >
                <Download size={13} aria-hidden="true" />
                <span>{dl.label}</span>
              </a>
            ))}
          </div>
        )}

        {/* Scientific Limitations Footer */}
        {limitations.length > 0 && (
          <div className="scientific-limitations-notice">
            <AlertCircle size={11} aria-hidden="true" />
            <span>{limitations[0]}</span>
          </div>
        )}
      </div>
    </div>
  );
}
