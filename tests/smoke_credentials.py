"""Opt-in native Keychain check using one temporary, synthetic app-owned entry."""
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.credentials import NativeCredentialStore


store = NativeCredentialStore()
store.service = 'LocalFirst Integration Test'
identifier, value = 'test-' + uuid4().hex, 'synthetic-' + uuid4().hex
try:
    store.set(identifier, value)
    assert store.get(identifier) == value
finally:
    store.delete(identifier)
assert store.get(identifier) is None
print('PASS: native Keychain stored/read/deleted a temporary synthetic entry. No existing credentials accessed.')
