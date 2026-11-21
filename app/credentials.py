"""Only app-owned credentials in the native macOS Keychain; no file fallback."""
import sys


class CredentialError(ValueError):
    pass


class NativeCredentialStore:
    service = 'LocalFirst OpenAI'

    def backend(self):
        if sys.platform != 'darwin':
            raise CredentialError('In-app key storage is currently available on macOS. Environment-based setup still works.')
        from keyring.backends.macOS import Keyring
        return Keyring()

    def get(self, credential_id):
        try:
            return self.backend().get_password(self.service, credential_id)
        except CredentialError:
            raise
        except Exception as exc:
            raise CredentialError('Could not read the OpenAI connection from macOS Keychain. Unlock Keychain and reconnect.') from exc

    def set(self, credential_id, key):
        try:
            self.backend().set_password(self.service, credential_id, key)
        except CredentialError:
            raise
        except Exception as exc:
            raise CredentialError('Could not save the connection in macOS Keychain. Your key was not saved in the chat database.') from exc

    def delete(self, credential_id):
        try:
            self.backend().delete_password(self.service, credential_id)
        except Exception:
            # Cleanup of an obsolete app-owned reference must not break a new connection.
            pass
