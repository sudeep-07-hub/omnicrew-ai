import { auth } from './firebase';

export interface QueryRequest {
  query: string;
  location: string;
  language: string;
}

export interface QueryResponse {
  response: string;
  language: string;
  agent_used: string;
  confidence: number;
  session_id: string;
  telemetry_snapshot?: Record<string, unknown> | null;
}

export interface TelemetryData {
  gate_id?: string;
  turnstile_count?: number;
  crowd_density?: number;
  temperature_c?: number;
  humidity_pct?: number;
  notes?: string;
  timestamp?: string;
  alerts?: string[];
  status?: string;
}

const API_BASE = import.meta.env.VITE_API_URL || '/api';

async function getAuthHeaders(): Promise<Record<string, string>> {
  const user = auth.currentUser;
  if (!user) {
    throw new Error('Not authenticated');
  }
  const token = await user.getIdToken();
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
  };
}

export async function sendQuery(request: QueryRequest): Promise<QueryResponse> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE}/query`, {
    method: 'POST',
    headers,
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    let errorMsg = 'An error occurred';
    try {
      const err = await response.json();
      errorMsg = err.detail || errorMsg;
    } catch {
      errorMsg = `HTTP Error ${response.status}`;
    }
    throw new Error(errorMsg);
  }

  return response.json();
}

export async function fetchTelemetry(): Promise<TelemetryData> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE}/telemetry`, { headers });

  if (!response.ok) {
    throw new Error(`Telemetry fetch failed: ${response.status}`);
  }

  return response.json();
}
