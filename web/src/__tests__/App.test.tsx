import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import App from '../App';
import { signInWithEmailAndPassword, onAuthStateChanged } from 'firebase/auth';

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });


  it('renders login screen when unauthenticated', async () => {
    render(<App />);
    
    await waitFor(() => {
      expect(screen.getByText(/OmniCrew AI/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Sign In/i })).toBeInTheDocument();
    });
  });

  it('calls signInWithEmailAndPassword on form submit', async () => {
    render(<App />);
    
    await waitFor(() => {
      expect(screen.getByLabelText(/Email/i)).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText(/Email/i), { target: { value: 'medic@omnicrew.test' } });
    fireEvent.change(screen.getByLabelText(/Password/i), { target: { value: 'password123' } });
    
    fireEvent.click(screen.getByRole('button', { name: /Sign In/i }));

    await waitFor(() => {
      expect(signInWithEmailAndPassword).toHaveBeenCalled();
    });
  });
});
