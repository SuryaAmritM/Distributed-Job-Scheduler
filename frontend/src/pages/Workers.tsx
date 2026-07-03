import { useEffect, useState } from 'react';
import { workers, type Worker } from '../api';

export default function WorkersPage() {
  const [list, setList] = useState<Worker[]>([]);

  useEffect(() => {
    const load = () => workers.list().then(setList);
    load();
    const i = setInterval(load, 5000);
    return () => clearInterval(i);
  }, []);

  return (
    <div>
      <h2>Workers</h2>
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <table>
          <thead>
            <tr><th>Hostname</th><th>Status</th><th>Concurrency</th><th>Active</th><th>Processed</th><th>Last Heartbeat</th></tr>
          </thead>
          <tbody>
            {list.map(w => (
              <tr key={w.id}>
                <td>{w.hostname}</td>
                <td><span className={`badge badge-${w.status === 'online' ? 'completed' : 'failed'}`}>{w.status}</span></td>
                <td>{w.concurrency}</td>
                <td>{w.active_jobs}</td>
                <td>{w.total_jobs_processed}</td>
                <td>{w.last_heartbeat_at ? new Date(w.last_heartbeat_at).toLocaleString() : '—'}</td>
              </tr>
            ))}
            {list.length === 0 && <tr><td colSpan={6} style={{ textAlign: 'center', color: 'var(--muted)' }}>No workers online</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
