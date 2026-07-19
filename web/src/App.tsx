import { useState, useRef, useEffect } from 'react';
import { signInWithEmailAndPassword, onAuthStateChanged, signOut } from 'firebase/auth';
import type { User, IdTokenResult } from 'firebase/auth';
import { auth } from './lib/firebase';
import { sendQuery, fetchTelemetry } from './lib/api';
import type { TelemetryData } from './lib/api';

const LANGUAGES = [
  { code: 'en', label: 'EN' },
  { code: 'es', label: 'ES' },
  { code: 'fr', label: 'FR' },
  { code: 'ar', label: 'AR' },
];

const ROLE_META: Record<string, { label: string; color: string; icon: string }> = {
  'medic': { label: 'Medic', color: 'bg-red-100 text-red-800', icon: '🏥' },
  'usher': { label: 'Usher', color: 'bg-blue-100 text-blue-800', icon: '🎫' },
  'security': { label: 'Security', color: 'bg-amber-100 text-amber-800', icon: '🛡️' },
  'command-center': { label: 'Command Center', color: 'bg-purple-100 text-purple-800', icon: '📡' },
};

interface FeedItem {
  type: 'user' | 'bot' | 'error';
  text: string;
  agent?: string;
  time: string;
}

function formatTime(): string {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// ── Login Screen ──────────────────────────────────────────────────────

function LoginScreen({ onLogin }: { onLogin: () => void }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await signInWithEmailAndPassword(auth, email, password);
      onLogin();
    } catch (err: any) {
      setError(
        err.code === 'auth/invalid-credential'
          ? 'Invalid email or password.'
          : err.code === 'auth/too-many-requests'
          ? 'Too many attempts. Please try again later.'
          : 'Sign in failed. Please try again.'
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-blue-600 rounded-2xl mb-4 shadow-lg shadow-blue-200" aria-hidden="true">
            <span className="text-white text-2xl font-bold">O</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-900">OmniCrew AI</h1>
          <p className="text-slate-500 text-sm mt-1">Operations Console</p>
        </div>

        <form onSubmit={handleSubmit} className="bg-white rounded-2xl shadow-xl shadow-slate-200/50 p-6 space-y-4 border border-slate-200" aria-label="Sign in form">
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 text-sm px-4 py-3 rounded-xl" role="alert">
              {error}
            </div>
          )}

          <div>
            <label htmlFor="login-email" className="block text-sm font-medium text-slate-700 mb-1.5">Email</label>
            <input
              id="login-email"
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="name@omnicrew.test"
              required
              autoComplete="email"
              className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
            />
          </div>

          <div>
            <label htmlFor="login-password" className="block text-sm font-medium text-slate-700 mb-1.5">Password</label>
            <input
              id="login-password"
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="••••••••"
              required
              autoComplete="current-password"
              className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-blue-200 min-h-[44px]"
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  );
}

// ── Status Panel ──────────────────────────────────────────────────────

function StatusPanel({ role }: { role: string }) {
  const [telemetry, setTelemetry] = useState<TelemetryData | null>(null);

  useEffect(() => {
    // Only poll telemetry for command-center role — other roles get 403.
    if (role !== 'command-center') return;

    let interval: ReturnType<typeof setInterval>;
    const load = async () => {
      try {
        const data = await fetchTelemetry();
        if (!data.status) setTelemetry(data);
      } catch { /* swallow on failure */ }
    };
    load();
    interval = setInterval(load, 15000);
    return () => clearInterval(interval);
  }, [role]);

  if (!telemetry) {
    return (
      <aside className="bg-white rounded-2xl border border-slate-200 p-5" aria-label="Live status panel">
        <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-3">Live Status</h3>
        <p className="text-slate-500 text-sm">Awaiting telemetry data...</p>
      </aside>
    );
  }

  const density = telemetry.crowd_density ? Math.round(telemetry.crowd_density * 100) : 0;
  const densityColor = density > 85 ? 'text-red-600' : density > 70 ? 'text-amber-600' : 'text-emerald-600';
  const tempColor = (telemetry.temperature_c || 0) > 40 ? 'text-red-600' : 'text-slate-900';

  return (
    <aside className="space-y-4" aria-label="Live telemetry data">
      <div className="bg-white rounded-2xl border border-slate-200 p-5">
        <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-4">Gate Status</h3>
        <dl className="space-y-3">
          <div className="flex justify-between items-center">
            <dt className="text-sm text-slate-600">Gate</dt>
            <dd className="font-semibold text-slate-900">{telemetry.gate_id}</dd>
          </div>
          <div className="flex justify-between items-center">
            <dt className="text-sm text-slate-600">Turnstile Count</dt>
            <dd className="font-semibold text-slate-900">{telemetry.turnstile_count?.toLocaleString()}</dd>
          </div>
          <div className="flex justify-between items-center">
            <dt className="text-sm text-slate-600">Crowd Density</dt>
            <dd className={`font-semibold ${densityColor}`}>{density}%</dd>
          </div>
          <div className="flex justify-between items-center">
            <dt className="text-sm text-slate-600">Temperature</dt>
            <dd className={`font-semibold ${tempColor}`}>{telemetry.temperature_c}°C</dd>
          </div>
          <div className="flex justify-between items-center">
            <dt className="text-sm text-slate-600">Humidity</dt>
            <dd className="font-semibold text-slate-900">{telemetry.humidity_pct}%</dd>
          </div>
        </dl>
      </div>

      {telemetry.alerts && telemetry.alerts.length > 0 && (
        <div className="bg-white rounded-2xl border border-red-200 p-5" role="alert">
          <h3 className="text-sm font-semibold text-red-600 uppercase tracking-wider mb-3">
            <span aria-hidden="true">⚠ </span>Active Alerts
          </h3>
          <ul className="space-y-2">
            {telemetry.alerts.map((alert, i) => (
              <li key={i} className="text-sm text-red-700 bg-red-50 px-3 py-2 rounded-lg">
                {alert}
              </li>
            ))}
          </ul>
        </div>
      )}
    </aside>
  );
}

// ── Main Dashboard ────────────────────────────────────────────────────

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [claims, setClaims] = useState<IdTokenResult | null>(null);
  const [authLoading, setAuthLoading] = useState(true);

  const [location, setLocation] = useState('Gate-A');
  const [language, setLanguage] = useState('en');
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [feed, setFeed] = useState<FeedItem[]>([]);

  const feedEndRef = useRef<HTMLDivElement>(null);

  const isRTL = language === 'ar';

  // Update document lang and dir attributes when language changes.
  useEffect(() => {
    document.documentElement.lang = language;
    document.documentElement.dir = isRTL ? 'rtl' : 'ltr';
  }, [language, isRTL]);

  useEffect(() => {
    const unsub = onAuthStateChanged(auth, async (firebaseUser) => {
      setUser(firebaseUser);
      if (firebaseUser) {
        const tokenResult = await firebaseUser.getIdTokenResult();
        setClaims(tokenResult);
        if (tokenResult.claims.gate) {
          setLocation(tokenResult.claims.gate as string);
        }
      } else {
        setClaims(null);
      }
      setAuthLoading(false);
    });
    return unsub;
  }, []);

  useEffect(() => {
    feedEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [feed]);

  const handleSignOut = async () => {
    await signOut(auth);
    setFeed([]);
  };

  const handleQuery = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    const userText = query;
    setQuery('');
    setFeed(prev => [...prev, { type: 'user', text: userText, time: formatTime() }]);
    setLoading(true);

    try {
      const res = await sendQuery({
        query: userText,
        location,
        language,
      });
      setFeed(prev => [...prev, {
        type: 'bot',
        text: res.response,
        agent: res.agent_used,
        time: formatTime(),
      }]);
    } catch (err: any) {
      setFeed(prev => [...prev, {
        type: 'error',
        text: err.message || 'Failed to communicate with backend.',
        time: formatTime(),
      }]);
    } finally {
      setLoading(false);
    }
  };

  if (authLoading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center" role="status" aria-label="Loading application">
        <div className="text-slate-500 text-sm">Loading...</div>
      </div>
    );
  }

  if (!user || !claims) {
    return <LoginScreen onLogin={() => {}} />;
  }

  const role = (claims.claims.role as string) || 'unknown';
  const roleMeta = ROLE_META[role] || { label: role, color: 'bg-slate-100 text-slate-800', icon: '👤' };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col" dir={isRTL ? 'rtl' : 'ltr'}>
      {/* Skip to main content link */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:bg-blue-600 focus:text-white focus:px-4 focus:py-2 focus:rounded-lg focus:text-sm focus:font-semibold"
      >
        Skip to main content
      </a>

      {/* Header */}
      <header className="bg-slate-900 text-white px-4 py-3 shadow-lg z-20">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center text-sm font-bold" aria-hidden="true">O</div>
            <div>
              <h1 className="font-bold text-base leading-tight">OmniCrew AI</h1>
              <p className="text-xs text-slate-400">Operations Console</p>
            </div>
          </div>

          <nav className="flex items-center gap-3" aria-label="User controls">
            <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${roleMeta.color}`} aria-label={`Role: ${roleMeta.label}`}>
              <span aria-hidden="true">{roleMeta.icon} </span>{roleMeta.label}
            </span>
            <label htmlFor="language-select" className="sr-only">Select language</label>
            <select
              id="language-select"
              value={language}
              onChange={e => setLanguage(e.target.value)}
              className="bg-slate-800 text-white text-xs rounded-lg px-3 py-2 min-h-[44px] min-w-[44px] border border-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
              aria-label="Select response language"
            >
              {LANGUAGES.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}
            </select>
            <button
              onClick={handleSignOut}
              className="text-xs text-slate-300 hover:text-white transition-colors px-3 py-2 min-h-[44px] min-w-[44px] rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              aria-label="Sign out"
            >
              Sign Out
            </button>
          </nav>
        </div>
      </header>

      {/* Context Bar */}
      <div className="bg-white border-b border-slate-200 px-4 py-2">
        <div className="max-w-6xl mx-auto flex items-center gap-4 text-sm">
          <span className="text-slate-500" aria-hidden="true">📍</span>
          <label htmlFor="location-input" className="sr-only">Current location</label>
          <input
            id="location-input"
            type="text"
            value={location}
            onChange={e => setLocation(e.target.value)}
            aria-label="Current location"
            className="bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 w-32 min-h-[44px]"
          />
          <span className="text-slate-500 text-xs">{user.email}</span>
        </div>
      </div>

      {/* Main Content */}
      <main id="main-content" className="flex-1 max-w-6xl mx-auto w-full px-4 py-4 flex gap-4 min-h-0">
        {/* Chat Panel */}
        <section className="flex-1 flex flex-col bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden min-w-0" aria-label="Chat panel">
          {/* Chat Feed */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3" role="log" aria-live="polite" aria-label="Message history">
            {feed.length === 0 && (
              <div className="h-full flex items-center justify-center text-slate-500 flex-col py-12">
                <div className="w-16 h-16 bg-blue-50 rounded-2xl flex items-center justify-center mb-4" aria-hidden="true">
                  <svg className="w-8 h-8 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                  </svg>
                </div>
                <p className="font-medium text-slate-600">Ready for queries</p>
                <p className="text-sm mt-1">Report an incident or request routing guidance</p>
              </div>
            )}

            {feed.map((msg, idx) => (
              <div key={idx} className={`flex ${msg.type === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[85%] ${
                  msg.type === 'user'
                    ? 'bg-blue-600 text-white rounded-2xl rounded-br-sm px-4 py-3'
                    : msg.type === 'error'
                    ? 'bg-red-50 border border-red-200 text-red-700 rounded-2xl rounded-bl-sm px-4 py-3'
                    : 'bg-slate-50 border border-slate-200 text-slate-900 rounded-2xl rounded-bl-sm px-4 py-3'
                }`} role={msg.type === 'error' ? 'alert' : undefined}>
                  {msg.type === 'bot' && msg.agent && (
                    <div className="text-xs text-blue-600 font-semibold mb-1 uppercase tracking-wider">
                      {msg.agent.replace(/_/g, ' ')}
                    </div>
                  )}
                  <div className="text-sm whitespace-pre-wrap">{msg.text}</div>
                  <div className={`text-xs mt-1 ${msg.type === 'user' ? 'text-blue-200' : 'text-slate-500'}`}>
                    <time>{msg.time}</time>
                  </div>
                </div>
              </div>
            ))}

            {loading && (
              <div className="flex justify-start" role="status" aria-label="Generating response">
                <div className="bg-slate-50 border border-slate-200 rounded-2xl rounded-bl-sm px-4 py-3 flex space-x-1.5">
                  <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce"></div>
                  <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{animationDelay: '0.15s'}}></div>
                  <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{animationDelay: '0.3s'}}></div>
                </div>
              </div>
            )}
            <div ref={feedEndRef} />
          </div>

          {/* Input */}
          <form onSubmit={handleQuery} className="p-3 border-t border-slate-200 bg-slate-50/50" aria-label="Send a query">
            <div className="flex gap-2">
              <label htmlFor="query-input" className="sr-only">Type your query</label>
              <input
                id="query-input"
                type="text"
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder="Report incident or request routing..."
                disabled={loading}
                className="flex-1 bg-white border border-slate-200 rounded-xl px-4 py-3 text-slate-900 text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 transition min-h-[44px]"
              />
              <button
                type="submit"
                disabled={loading || !query.trim()}
                aria-label="Send query"
                className="bg-blue-600 hover:bg-blue-700 text-white rounded-xl px-5 py-3 text-sm font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed shadow-sm min-h-[44px] min-w-[44px]"
              >
                Send
              </button>
            </div>
          </form>
        </section>

        {/* Status Panel — visible on wider screens */}
        <div className="hidden lg:block w-72 shrink-0">
          <StatusPanel role={role} />
        </div>
      </main>
    </div>
  );
}
