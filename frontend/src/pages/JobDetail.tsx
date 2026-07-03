import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { jobs, type JobDetail } from '../api';

export default function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [job, setJob] = useState<JobDetail | null>(null);

  useEffect(() => {
    if (!id) return;
    const load = () => jobs.get(id).then(setJob);
    load();
    const i = setInterval(load, 3000);
    return () => clearInterval(i);
  }, [id]);

  if (!job) return <p>Loading...</p>;

  return (
    <div>
      <Link to="/jobs" style={{ fontSize: 14 }}>← Back to jobs</Link>
      <h2 style={{ marginTop: 12 }}>Job {job.id.slice(0, 8)}...</h2>
      <div className="grid grid-2" style={{ marginBottom: 24 }}>
        <div className="card">
          <h3>Details</h3>
          <p><strong>Status:</strong> <span className={`badge badge-${job.status}`}>{job.status}</span></p>
          <p style={{ marginTop: 8 }}><strong>Type:</strong> {job.job_type}</p>
          <p style={{ marginTop: 8 }}><strong>Retries:</strong> {job.retry_count}</p>
          {job.error_message && <p style={{ marginTop: 8, color: 'var(--danger)' }}>{job.error_message}</p>}
          <pre style={{ marginTop: 12, fontSize: 12, background: 'var(--bg)', padding: 12, borderRadius: 8, overflow: 'auto' }}>
            {JSON.stringify(job.payload, null, 2)}
          </pre>
        </div>
        <div className="card">
          <h3>Executions</h3>
          {job.executions.map(ex => (
            <div key={ex.id} style={{ padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
              Attempt #{ex.attempt_number} — {ex.status}
              {ex.duration_ms != null && ` (${ex.duration_ms}ms)`}
              {ex.error_message && <div style={{ color: 'var(--danger)', fontSize: 13 }}>{ex.error_message}</div>}
            </div>
          ))}
          {job.retry_history.length > 0 && (
            <>
              <h3 style={{ marginTop: 16 }}>Retry History</h3>
              {job.retry_history.map((r, i) => (
                <div key={i} style={{ fontSize: 13, padding: '4px 0' }}>
                  Attempt {r.attempt_number}: retry in {r.retry_after_seconds}s — {r.error_message}
                </div>
              ))}
            </>
          )}
        </div>
      </div>
      <div className="card">
        <h3>Execution Logs</h3>
        {job.logs.map(log => (
          <div key={log.id} className={`log-entry log-${log.level}`}>
            <span style={{ color: 'var(--muted)' }}>{new Date(log.created_at).toLocaleTimeString()}</span>{' '}
            [{log.level}] {log.message}
          </div>
        ))}
      </div>
    </div>
  );
}
