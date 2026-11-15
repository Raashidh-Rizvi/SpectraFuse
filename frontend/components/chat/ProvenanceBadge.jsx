import React from 'react';
import { CheckCircle2, AlertTriangle, HelpCircle, Satellite, Sparkles } from 'lucide-react';

export default function ProvenanceBadge({ status, product, calibrationApplied = false, coverage = 'complete' }) {
  const normStatus = (status || '').toLowerCase();

  if (normStatus === 'observed') {
    return (
      <span
        className="provenance-badge badge-observed"
        title="Direct satellite observation (VIIRS S-NPP 375m). Complete coverage partition."
        aria-label="Observed by VIIRS"
      >
        <Satellite size={12} aria-hidden="true" />
        <span>Observed by VIIRS</span>
      </span>
    );
  }

  if (normStatus === 'estimated' || calibrationApplied) {
    return (
      <span
        className="provenance-badge badge-estimated"
        title="Estimated from MODIS using regional calibration multiplier. Empirical holdout error applies."
        aria-label="Estimated from MODIS"
      >
        <Sparkles size={12} aria-hidden="true" />
        <span>Estimated from MODIS</span>
      </span>
    );
  }

  if (normStatus === 'unavailable') {
    return (
      <span
        className="provenance-badge badge-unavailable"
        title="Data partition unavailable. Missing observation data is distinct from zero observed fires."
        aria-label="Unavailable data"
      >
        <AlertTriangle size={12} aria-hidden="true" />
        <span>Data Unavailable</span>
      </span>
    );
  }

  if (normStatus === 'partial') {
    return (
      <span
        className="provenance-badge badge-partial"
        title="Partial coverage. Incomplete satellite daily partitions."
        aria-label="Partial coverage"
      >
        <AlertTriangle size={12} aria-hidden="true" />
        <span>Partial Coverage</span>
      </span>
    );
  }

  return (
    <span
      className="provenance-badge badge-neutral"
      title={product ? `Product: ${product}` : 'Verified remote sensing metric'}
    >
      <CheckCircle2 size={12} aria-hidden="true" />
      <span>{product || 'Verified'}</span>
    </span>
  );
}
