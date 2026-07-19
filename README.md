# OmniCrew AI

> **GenAI-powered decision-support co-pilot for stadium ground staff.**

OmniCrew AI enables ground staff — medics, ushers, security, and command-center operators — to issue natural-language queries and receive localized, actionable instructions fused with live telemetry from IoT sensors.

## Live Environments

- **Web Application**: [https://omnicrew-ai-2026.web.app](https://omnicrew-ai-2026.web.app)
- **API Documentation**: [https://omnicrew-ai.onrender.com/docs](https://omnicrew-ai.onrender.com/docs)

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
