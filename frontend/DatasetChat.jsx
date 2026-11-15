import React, {useState} from 'react';

const products = {
  MODIS_SP: 'MODIS', VIIRS_SNPP_SP: 'VIIRS S-NPP', VIIRS_NOAA20_SP: 'VIIRS NOAA-20',
  harmonized: 'Harmonized', 'MODIS_SP / VIIRS_SNPP_SP': 'MODIS / VIIRS S-NPP',
};
const bases = {
  daily_partitions: 'downloaded UTC days', complete_months: 'complete months',
  matched_months: 'matched months', anomaly_months: 'months with anomaly values', holdout_months: 'holdout months',
};

function citationLabel({product, basis, first, last, available, expected, start_month, end_month}) {
  const count = expected == null ? available : `${available} of ${expected}`;
  const period = first ? (first === last ? first : `${first} to ${last}`) : [start_month, end_month].filter(Boolean).join(' to ');
  return `${products[product] ?? product} · ${count} ${bases[basis]}${period ? ` · ${period}` : ''}`;
}

export default function DatasetChat({base, region, label}) {
  const [question, setQuestion] = useState('');
  const [history, setHistory] = useState([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');

  async function submit(event) {
    event.preventDefault();
    const content = question.trim();
    if (!content || pending) return;
    const message = {role:'user', content};
    setPending(true);
    setError('');
    try {
      const response = await fetch(base + '/chat', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({region, question:content, history:history.slice(-6).map(turn => ({
          role:turn.role, content:turn.content.slice(0, 4000),
        }))}),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Chat request failed.');
      setHistory([...history, message, {role:'assistant', content:result.answer, source:result.source,
        citations:result.citations}]);
      setQuestion('');
    } catch (failure) {
      setError(failure.message);
    } finally {
      setPending(false);
    }
  }

  return <details className="panel dataset-chat">
    <summary>Ask about the dataset</summary>
    <p>{label} · Archive coverage, monthly detections and fire radiative power</p>
    <div role="log" aria-label="Dataset conversation">
      {history.map((message, index) => <div className="chat-message" key={index}>
        <strong>{message.role === 'user' ? 'You' : 'SpectraFuse'}</strong>
        <p>{message.content}</p>
        {message.citations?.length > 0 && <small>
          {message.source}
          {message.citations.map((citation, index) => <React.Fragment key={index}>
            <br />{citationLabel(citation)}
          </React.Fragment>)}
        </small>}
      </div>)}
    </div>
    <form onSubmit={submit}>
      <label htmlFor="dataset-question">Question</label>
      <textarea id="dataset-question" value={question} maxLength={2000} disabled={pending}
        onChange={event => setQuestion(event.target.value)}
        placeholder="What is the oldest data available in the MODIS dataset?" required />
      <button className="button" disabled={pending || !question.trim()} type="submit">
        {pending ? 'Analyzing…' : 'Ask'}
      </button>
    </form>
    {error && <p role="alert">{error}</p>}
  </details>;
}
