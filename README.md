# OmniCrew AI

GenAI-powered decision-support co-pilot for stadium ground staff.

## Test Accounts (Login Credentials)

You can log in to the application using any of the following accounts to test different roles:

| Role | Email | Password | Location |
| :--- | :--- | :--- | :--- |
| **Medic** | `medic@omnicrew.test` | `OmniMedic2026!` | Gate-A |
| **Usher** | `usher@omnicrew.test` | `OmniUsher2026!` | Gate-C |
| **Security** | `security@omnicrew.test` | `OmniSecurity2026!` | Gate-B |
| **Command Center**| `cmdctr@omnicrew.test` | `OmniCommand2026!` | HQ |

## Live Links

- **Web Application:** [https://omnicrew-ai-2026.web.app](https://omnicrew-ai-2026.web.app)
- **API Documentation:** [https://omnicrew-ai.onrender.com/docs](https://omnicrew-ai.onrender.com/docs)

## Local Development

1. **Backend**:
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   uvicorn app.main:app --reload
   ```

2. **Frontend**:
   ```bash
   cd web
   npm install
   npm run dev
   ```

## Structure
- `app/`: FastAPI Backend & LangGraph Agents
- `web/`: React + Vite Frontend
- `tests/`: Pytest Suite
