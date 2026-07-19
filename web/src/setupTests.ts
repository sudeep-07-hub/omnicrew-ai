import '@testing-library/jest-dom';
import { vi } from 'vitest';

// Mock Firebase
vi.mock('firebase/auth', () => ({
  signInWithEmailAndPassword: vi.fn().mockResolvedValue({}),
  onAuthStateChanged: vi.fn((auth, callback) => {
    // Start unauthenticated by default
    callback(null);
    return () => {};
  }),
  signOut: vi.fn(),
  getAuth: vi.fn(),
}));

vi.mock('./lib/firebase', () => ({
  auth: {},
}));

// Mock API
vi.mock('./lib/api', () => ({
  sendQuery: vi.fn(),
  fetchTelemetry: vi.fn(),
}));

// Mock scrollIntoView
window.HTMLElement.prototype.scrollIntoView = vi.fn();
