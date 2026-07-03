import { useEffect, useState } from 'react';
import { orgs, projects, queues, type Queue } from '../api';

export default function QueuesPage() {
  const [queueList, setQueueList] = useState<Queue[]>([]);
  const [newName, setNewName] = useState('');
  const [projectId, setProjectId] = useState('');

  const load = async () => {
    const orgList = await orgs.list();
    if (!orgList.length) return;
    const projs = await projects.list(orgList[0].id);
    if (!projs.length) return;
    setProjectId(projs[0].id);
    setQueueList(await queues.list(projs[0].id));
  };

  useEffect(() => { load(); const i = setInterval(load, 5000); return () => clearInterval(i); }, []);

  const create = async () => {
    if (!projectId || !newName) return;
    await queues.create(projectId, { name: newName });
    setNewName('');
    load();
  };

  const togglePause = async (q: Queue) => {
    if (q.is_paused) await queues.resume(q.id);
    else await queues.pause(q.id);
    load();
  };

  return (
    <div>
      <h2>Queues</h2>
      <div className="toolbar">
        <input placeholder="New queue name" value={newName} onChange={e => setNewName(e.target.value)} style={{ maxWidth: 240 }} />
        <button className="btn" onClick={create}>Create Queue</button>
      </div>
      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))' }}>
        {queueList.map(q => (
          <div className="card" key={q.id}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ color: 'var(--text)' }}>{q.name}</h3>
              <span className={`badge ${q.is_paused ? 'badge-failed' : 'badge-completed'}`}>
                {q.is_paused ? 'Paused' : 'Active'}
              </span>
            </div>
            <p style={{ fontSize: 13, color: 'var(--muted)', margin: '8px 0' }}>
              Priority: {q.priority} · Concurrency: {q.concurrency_limit}
            </p>
            {q.stats && (
              <div className="grid grid-4" style={{ marginTop: 12, gap: 8 }}>
                <div><div className="stat-value" style={{ fontSize: 20 }}>{q.stats.queued}</div><div className="stat-label">Queued</div></div>
                <div><div className="stat-value" style={{ fontSize: 20 }}>{q.stats.running}</div><div className="stat-label">Running</div></div>
                <div><div className="stat-value" style={{ fontSize: 20 }}>{q.stats.completed}</div><div className="stat-label">Done</div></div>
                <div><div className="stat-value" style={{ fontSize: 20 }}>{q.stats.dead_letter}</div><div className="stat-label">DLQ</div></div>
              </div>
            )}
            <button className="btn-outline" style={{ marginTop: 16 }} onClick={() => togglePause(q)}>
              {q.is_paused ? 'Resume' : 'Pause'}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
