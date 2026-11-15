import React from 'react';
import { Sparkles } from 'lucide-react';

const SUGGESTIONS = [
  "What was the fire activity in Sri Lanka in August 2021?",
  "Was March 2023 unusual compared to earlier values?",
  "Compare MODIS and VIIRS for 2020.",
  "Show hotspots on the map for 2022-03-01 to 2022-03-10.",
  "What is the regional calibration multiplier?",
  "Download monthly data for 2021 as CSV.",
];

export default function SuggestedQuestions({ onSelect, disabled = false }) {
  return (
    <div className="suggested-questions-container" aria-label="Suggested starter questions">
      <div className="suggested-header">
        <Sparkles size={13} aria-hidden="true" />
        <span>Suggested Analytics Queries</span>
      </div>
      <div className="suggested-chips-grid">
        {SUGGESTIONS.map((q, idx) => (
          <button
            key={idx}
            type="button"
            className="suggested-chip-button"
            disabled={disabled}
            onClick={() => onSelect && onSelect(q)}
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
