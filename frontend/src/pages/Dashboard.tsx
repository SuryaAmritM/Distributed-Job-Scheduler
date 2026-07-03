import { useEffect, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { metrics, type SystemMetrics } from '../api';

const COLORS = ['#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4'];

export default function Dashboard() {
  const [data, setData] = useState<SystemMetrics | null>(null);

  useEffect(() => {
    const load = () => metrics.get().then(setData).catch(console.error);
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, []);

  if (!data) return <p>Loading...</p>;

  const chartData = Object.entries(data.jobs_by_status).map(([name, value]) => ({ name, value }));
  const pieData = chartData.filter(d => d.value > 0);

  return (
    <div>
      <h2>System Overview</h2>
      <div className="grid grid-4" style={{ marginBottom: 24 }}>
        <div className="card"><div className="stat-value">{data.total_jobs}</div><div className="stat-label">Total Jobs</div></div>
        <div className="card"><div className="stat-value">{data.active_workers}</div><div className="stat-label">Active Workers</div></div>
        <div className="card"><div className="stat-value">{data.throughput_last_hour}</div><div className="stat-label">Throughput / hr</div></div>
        <div className="card"><div className="stat-value">{Math.round(data.avg_duration_ms)}ms</div><div className="stat-label">Avg Duration</div></div>
      </div>
      <div className="grid grid-2">
        <div className="card">
          <h3>Jobs by Status</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={chartData}>
              <XAxis dataKey="name" stroke="#8b8fa3" fontSize={12} />
              <YAxis stroke="#8b8fa3" fontSize={12} />
              <Tooltip contentStyle={{ background: '#1a1d27', border: '1px solid #2a2d3a' }} />
              <Bar dataKey="value" fill="#6366f1" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="card">
          <h3>Status Distribution</h3>
          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={90} label>
                {pieData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip contentStyle={{ background: '#1a1d27', border: '1px solid #2a2d3a' }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>
      {data.dlq_count > 0 && (
        <div className="card" style={{ marginTop: 20, borderColor: 'var(--danger)' }}>
          <strong style={{ color: 'var(--danger)' }}>{data.dlq_count} jobs in Dead Letter Queue</strong>
        </div>
      )}
    </div>
  );
}
