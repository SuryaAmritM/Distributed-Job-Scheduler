import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { orgs, projects, queues, jobs, type Job, type Queue } from '../api';

function StatusBadge({ status }: { status: string }) {
  return <span className={`badge badge-${status}`}>{status}</span>;
}

export default function JobsPage() {
  const [queueList, setQueueList] = useState<Queue[]>([]);
  const [selectedQueue, setSelectedQueue] = useState('');
  const [jobList, setJobList] = useState<Job[]>([]);
  const [statusFilter, setStatusFilter] = useState('');
  const [payload, setPayload] = useState('{"action": "process", "duration_seconds": 0.5}');

  useEffect(() => {
    orgs.list().then(async orgList => {
      if (!orgList.length) return;
      const projs = await projects.list(orgList[0].id);
      if (!projs.length) return;
      const qs = await queues.list(projs[0].id);
      setQueueList(qs);
      if (qs.length) setSelectedQueue(qs[0].id);
    });
  }, []);

  const loadJobs = () => {
    if (!selectedQueue) return;
    jobs.list(selectedQueue, 1, statusFilter || undefined).then(r => setJobList(r.items));
  };

  useEffect(() => { loadJobs(); const i = setInterval(loadJobs, 3000); return () => clearInterval(i); }, [selectedQueue, statusFilter]);

  const createJob = async (type: string) => {
    if (!selectedQueue) return;
    await jobs.create(selectedQueue, {
      job_type: type,
      payload: JSON.parse(payload),
      ...(type === 'delayed' ? { delay_seconds: 10 } : {}),
      ...(type === 'recurring' ? { cron_expression: '*/1 * * * *' } : {}),
    });
    loadJobs();
  };

  return (
    <div>
      <h2>Job Explorer</h2>
      <div className="toolbar">
        <select value={selectedQueue} onChange={e => setSelectedQueue(e.target.value)} style={{ maxWidth: 200 }}>
          {queueList.map(q => <option key={q.id} value={q.id}>{q.name}</option>)}
        </select>
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={{ maxWidth: 160 }}>
          <option value="">All statuses</option>
          {['queued','scheduled','running','completed','failed','dead_letter'].map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <button className="btn" onClick={() => createJob('immediate')}>Enqueue Job</button>
        <button className="btn-outline" onClick={() => createJob('delayed')}>Delayed (10s)</button>
        <button className="btn-outline" onClick={() => createJob('recurring')}>Recurring (1min)</button>
      </div>
      <div className="form-group" style={{ marginBottom: 20 }}>
        <label>Payload (JSON)</label>
        <textarea value={payload} onChange={e => setPayload(e.target.value)} rows={3} />
      </div>
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <table>
          <thead><tr><th>ID</th><th>Type</th><th>Status</th><th>Retries</th><th>Created</th><th></th></tr></thead>
          <tbody>
            {jobList.map(j => (
              <tr key={j.id}>
                <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{j.id.slice(0, 8)}...</td>
                <td>{j.job_type}</td>
                <td><StatusBadge status={j.status} /></td>
                <td>{j.retry_count}</td>
                <td>{new Date(j.created_at).toLocaleString()}</td>
                <td><Link to={`/jobs/${j.id}`}>Details</Link></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
