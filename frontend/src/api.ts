const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function getToken() {
  return localStorage.getItem('token');
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${API}${path}`, { ...options, headers });
  if (res.status === 401) {
    localStorage.removeItem('token');
    window.location.href = '/login';
    throw new Error('Unauthorized');
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = err.detail;
    const message = Array.isArray(detail)
      ? detail.map((e: { msg?: string }) => e.msg).filter(Boolean).join(', ')
      : (typeof detail === 'string' ? detail : res.statusText);
    throw new Error(message || 'Request failed');
  }
  return res.json();
}

export const auth = {
  login: (email: string, password: string) =>
    api<{ access_token: string }>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  register: (email: string, password: string, full_name: string) =>
    api('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, full_name }),
    }),
  me: () => api<{ id: string; email: string; full_name: string }>('/api/v1/auth/me'),
};

export const orgs = {
  list: () => api<Array<{ id: string; name: string; slug: string }>>('/api/v1/organizations'),
  create: (name: string, slug: string) =>
    api('/api/v1/organizations', { method: 'POST', body: JSON.stringify({ name, slug }) }),
};

export const projects = {
  list: (orgId: string) => api<Array<{ id: string; name: string; slug: string }>>(`/api/v1/organizations/${orgId}/projects`),
  create: (orgId: string, name: string, slug: string) =>
    api(`/api/v1/organizations/${orgId}/projects`, { method: 'POST', body: JSON.stringify({ name, slug }) }),
};

export const queues = {
  list: (projectId: string) => api<Array<Queue>>(`/api/v1/projects/${projectId}/queues`),
  create: (projectId: string, data: { name: string; priority?: number; concurrency_limit?: number }) =>
    api(`/api/v1/projects/${projectId}/queues`, { method: 'POST', body: JSON.stringify(data) }),
  pause: (id: string) => api(`/api/v1/queues/${id}/pause`, { method: 'POST' }),
  resume: (id: string) => api(`/api/v1/queues/${id}/resume`, { method: 'POST' }),
};

export const jobs = {
  list: (queueId: string, page = 1, status?: string) => {
    const params = new URLSearchParams({ page: String(page), page_size: '20' });
    if (status) params.set('status', status);
    return api<Paginated<Job>>(`/api/v1/queues/${queueId}/jobs?${params}`);
  },
  get: (id: string) => api<JobDetail>(`/api/v1/jobs/${id}`),
  create: (queueId: string, data: object) =>
    api(`/api/v1/queues/${queueId}/jobs`, { method: 'POST', body: JSON.stringify(data) }),
  cancel: (id: string) => api(`/api/v1/jobs/${id}/cancel`, { method: 'POST' }),
};

export const workers = {
  list: () => api<Worker[]>('/api/v1/workers'),
};

export const metrics = {
  get: () => api<SystemMetrics>('/api/v1/metrics'),
};

export const dlq = {
  list: (queueId: string) => api<Paginated<DLQEntry>>(`/api/v1/queues/${queueId}/dlq`),
  retry: (id: string) => api(`/api/v1/dlq/${id}/retry`, { method: 'POST' }),
};

export interface Queue {
  id: string; name: string; priority: number; concurrency_limit: number;
  is_paused: boolean; stats?: { total_jobs: number; queued: number; running: number; completed: number; failed: number; dead_letter: number; throughput_per_hour: number };
}

export interface Job {
  id: string; queue_id: string; job_type: string; status: string; priority: number;
  payload: Record<string, unknown>; error_message?: string; retry_count: number;
  created_at: string; started_at?: string; completed_at?: string;
}

export interface JobDetail extends Job {
  executions: Array<{ id: string; attempt_number: number; status: string; duration_ms?: number; error_message?: string; started_at: string }>;
  logs: Array<{ id: string; level: string; message: string; created_at: string }>;
  retry_history: Array<{ attempt_number: number; error_message?: string; retry_after_seconds: number; retried_at: string }>;
}

export interface Worker {
  id: string; hostname: string; status: string; concurrency: number;
  active_jobs: number; total_jobs_processed: number; last_heartbeat_at?: string;
}

export interface SystemMetrics {
  total_jobs: number; jobs_by_status: Record<string, number>;
  active_workers: number; throughput_last_hour: number; avg_duration_ms: number; dlq_count: number;
}

export interface DLQEntry {
  id: string; job_id: string; failure_reason: string; final_error?: string;
  total_attempts: number; moved_at: string; retried: boolean;
}

export interface Paginated<T> { items: T[]; total: number; page: number; pages: number }
