# OmniCrew AI

> **GenAI-powered decision-support co-pilot for stadium ground staff.**

OmniCrew AI enables ground staff — medics, ushers, security, and command-center operators — to issue natural-language queries and receive localized, actionable instructions fused with live telemetry from IoT sensors.

## Live Environments

- **Web Application**: [https://omnicrew-ai-2026.web.app](https://omnicrew-ai-2026.web.app)
- **API Documentation**: [https://omnicrew-ai.onrender.com/docs](https://omnicrew-ai.onrender.com/docs)

### Test Accounts

Use any of these pre-configured accounts to log in and test the different agent personas:

| Email | Password | Role / Location |
| :--- | :--- | :--- |
| `medic@omnicrew.test` | `OmniMedic2026!` | 🏥 Medic (Gate-A) |
| `usher@omnicrew.test` | `OmniUsher2026!` | 🎫 Usher (Gate-C) |
| `security@omnicrew.test` | `OmniSecurity2026!` | 🛡️ Security (Gate-B) |
| `cmdctr@omnicrew.test` | `OmniCommand2026!` | 📡 Command Center (HQ) |

## Project Structure

- `app/`: FastAPI backend and LangGraph agents.
- `web/`: React + Vite frontend application.
- `tests/`: Pytest suite for backend validation.
- `scripts/`: Development and deployment utilities.

## Getting Started Locally

1. Create a Python virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
2. Run the backend API:
   ```bash
   uvicorn app.main:app --reload
   ```
3. Run the frontend development server:
   ```bash
   cd web
   npm install
   npm run dev
   ```

## Tech Stack

- **Backend**: Python, FastAPI, LangGraph, Google Gemini 2.0 Flash
- **Frontend**: React, TypeScript, TailwindCSS, Vite
- **Auth & Hosting**: Firebase Auth, Firebase Hosting, Render
