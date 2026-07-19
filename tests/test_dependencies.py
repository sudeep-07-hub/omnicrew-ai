import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException, Request
from app.dependencies import verify_firebase_token

@pytest.mark.asyncio
async def test_verify_firebase_token_no_auth():
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {}
    with pytest.raises(HTTPException) as exc:
        await verify_firebase_token(request=mock_request)
    assert exc.value.status_code == 401

# The rest of verify_firebase_token tests will require mocking firebase-admin.
