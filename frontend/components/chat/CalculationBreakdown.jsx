import React from 'react';
import { Calculator, ChevronDown } from 'lucide-react';

export default function CalculationBreakdown({ calculations = [] }) {
  if (!calculations || calculations.length === 0) return null;

  return (
    <details className="calculation-breakdown" aria-label="Step-by-step mathematical calculations">
      <summary>
        <Calculator size={13} aria-hidden="true" />
        <span>Calculation Breakdown ({calculations.length} {calculations.length === 1 ? 'step' : 'steps'})</span>
        <ChevronDown size={13} className="chevron-icon" aria-hidden="true" />
      </summary>
      <div className="calc-content">
        {calculations.map((calc, idx) => (
          <div key={idx} className="calc-step-row">
            <div className="calc-step-name">{calc.step}</div>
            <div className="calc-formula-block">
              <code>{calc.formula}</code>
              <span className="calc-equals">=</span>
              <strong>{String(calc.result)}</strong>
            </div>
          </div>
        ))}
      </div>
    </details>
  );
}
