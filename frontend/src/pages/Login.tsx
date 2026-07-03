import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { auth } from '../api';

export default function Login() {
  const navigate = useNavigate();
  const [isRegister, setIsRegister] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState('');

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    try {
      if (isRegister) {
        await auth.register(email, password, name);
      }
      const { access_token } = await auth.login(email, password);
      localStorage.setItem('token', access_token);
      navigate('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed');
    }
  };

  return (
    <div className="login-page">
      <div className="card login-card">
        <h2>{isRegister ? 'Create Account' : 'Sign In'}</h2>
        <form onSubmit={submit}>
          {isRegister && (
            <div className="form-group">
              <label>Full Name</label>
              <input value={name} onChange={e => setName(e.target.value)} required />
            </div>
          )}
          <div className="form-group">
            <label>Email</label>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)} required />
          </div>
          <div className="form-group">
            <label>Password</label>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)} required minLength={8} />
          </div>
          {error && <p className="error">{error}</p>}
          <button className="btn" style={{ width: '100%', marginTop: 8 }} type="submit">
            {isRegister ? 'Register' : 'Login'}
          </button>
        </form>
        <p style={{ marginTop: 16, fontSize: 14, color: 'var(--muted)', textAlign: 'center' }}>
          {isRegister ? 'Have an account?' : 'No account?'}{' '}
          <a href="#" onClick={e => { e.preventDefault(); setIsRegister(!isRegister); }}>{isRegister ? 'Sign in' : 'Register'}</a>
        </p>
      </div>
    </div>
  );
}
