from firebase_functions import https_fn, params
from a2wsgi import ASGIMiddleware
from app.main import app as fastapi_app

# The LLM API key should be injected as a secret via Secret Manager
google_api_key = params.SecretParam("OMNICREW_GOOGLE_API_KEY")

# Wrap FastAPI (ASGI) for the Firebase WSGI handler
wsgi_app = ASGIMiddleware(fastapi_app)

@https_fn.on_request(
    min_instances=0, 
    secrets=[google_api_key],
    region="us-central1"
)
def omnicrew_api(req: https_fn.Request) -> https_fn.Response:
    # Firebase Hosting rewrite passes the original request path (e.g. /api/query).
    # FastAPI expects /query. Strip the /api prefix from the WSGI environment.
    environ = req.environ.copy()
    path_info = environ.get("PATH_INFO", "")
    
    if path_info.startswith("/api"):
        environ["SCRIPT_NAME"] = "/api"
        environ["PATH_INFO"] = path_info[4:]
        
    with wsgi_app.request_context(environ):
        return wsgi_app.full_dispatch_request()
