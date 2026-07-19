import pytest
from app.utils.security import (
    validate_api_key_format,
    hash_api_key,
    mask_pii_for_logging,
)

def test_validate_api_key_format():
    assert validate_api_key_format("1234567890123456") == True
    assert validate_api_key_format("short") == False
    assert validate_api_key_format("invalid!character123456") == False

def test_hash_api_key(monkeypatch):
    from app.config import Settings
    
    mock_settings = Settings(
        firebase_project_id="test",
        google_api_key="test",
        edge_api_url="http://test",
        hmac_secret="test-secret"
    )
    
    hashed = hash_api_key("my-api-key", settings=mock_settings)
    assert hashed != "my-api-key"
    assert len(hashed) == 64  # SHA256 length

def test_mask_pii_for_logging_short():
    assert mask_pii_for_logging("12") == "12"
    assert mask_pii_for_logging("j@f") == "j@f"
    
def test_mask_pii_for_logging_normal():
    assert mask_pii_for_logging("+1-555-123-4567") == "+*************7"
    assert mask_pii_for_logging("john.doe@fifa.org") == "j***************g"
