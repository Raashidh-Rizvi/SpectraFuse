import React, {useState} from 'react';

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
        period:result.first_month + ' to ' + result.last_month}]);
      setQuestion('');
    } catch (failure) {
      setError(failure.message);
    } finally {
      setPending(false);
    }
  }

  return <details className="panel dataset-chat">
    <summary>Ask about the dataset</summary>
    <p>{label} · Monthly counts, coverage, anomalies and sensor comparisons</p>
    <div role="log" aria-label="Dataset conversation">
      {history.map((message, index) => <div className="chat-message" key={index}>
        <strong>{message.role === 'user' ? 'You' : 'SpectraFuse'}</strong>
        <p>{message.content}</p>
        {message.source && <small>{message.source} · {message.period}</small>}
      </div>)}
    </div>
    <form onSubmit={submit}>
      <label htmlFor="dataset-question">Question</label>
      <textarea id="dataset-question" value={question} maxLength={2000} disabled={pending}
        onChange={event => setQuestion(event.target.value)}
        placeholder="Which months had the most fire detections in 2024?" required />
      <button className="button" disabled={pending || !question.trim()} type="submit">
        {pending ? 'Analyzing…' : 'Ask'}
      </button>
    </form>
    {error && <p role="alert">{error}</p>}
  </details>;
}
