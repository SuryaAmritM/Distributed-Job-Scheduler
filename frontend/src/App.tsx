import { BrowserRouter, Routes, Route, Navigate, NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { auth } from './api';
import Dashboard from './pages/Dashboard';
import Queues from './pages/Queues';
import Jobs from './pages/Jobs';
import Workers from './pages/Workers';
import JobDetail from './pages/JobDetail';
import Login from './pages/Login';

function Layout() {
  const navigate = useNavigate();
  const [user, setUser] = useState<{ full_name: string } | null>(null);

  useEffect(() => {
    auth.me().then(setUser).catch(() => navigate('/login'));
  }, [navigate]);

  const logout = () => { localStorage.removeItem('token'); navigate('/login'); };

  return (
    <div className="layout">
      <aside className="sidebar">
        <h1>Job Scheduler</h1>
        <nav>
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/queues">Queues</NavLink>
          <NavLink to="/jobs">Jobs</NavLink>
          <NavLink to="/workers">Workers</NavLink>
        </nav>
        <div style={{ marginTop: 'auto', paddingTop: 40, fontSize: 13, color: 'var(--muted)' }}>
          {user?.full_name}
          <button className="btn-outline" style={{ marginTop: 8, width: '100%' }} onClick={logout}>Logout</button>
        </div>
      </aside>
      <main className="main"><Outlet /></main>
    </div>
  );
}

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const token = localStorage.getItem('token');
  return token ? <>{children}</> : <Navigate to="/login" />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<PrivateRoute><Layout /></PrivateRoute>}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/queues" element={<Queues />} />
          <Route path="/jobs" element={<Jobs />} />
          <Route path="/jobs/:id" element={<JobDetail />} />
          <Route path="/workers" element={<Workers />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
