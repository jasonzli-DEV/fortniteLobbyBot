"""Encryption module for securing Epic Games credentials."""
import json
import logging
from cryptography.fernet import Fernet, InvalidToken

from config import get_settings

logger = logging.getLogger(__name__)


class EncryptionService:
    """Service for encrypting and decrypting Epic credentials."""
    
    def __init__(self):
        settings = get_settings()
        self.fernet = Fernet(settings.encryption_key.encode())
    
    def encrypt_credentials(
        self,
        device_id: str,
        account_id: str,
        secret: str,
        client_token: str = None
    ) -> str:
        """
        Encrypt Epic Games device auth credentials.
        
        Args:
            device_id: Epic device ID
            account_id: Epic account ID
            secret: Device auth secret
            client_token: Optional client token used for auth
            
        Returns:
            Encrypted string containing all credentials
        """
        credentials = {
            "device_id": device_id,
            "account_id": account_id,
            "secret": secret
        }
        if client_token:
            credentials["client_token"] = client_token
        json_data = json.dumps(credentials)
        encrypted = self.fernet.encrypt(json_data.encode())
        return encrypted.decode()
    
    def decrypt_credentials(self, encrypted_data: str) -> dict:
        """
        Decrypt Epic Games device auth credentials.
        
        Args:
            encrypted_data: Encrypted credentials string
            
        Returns:
            Dictionary with device_id, account_id, and secret
            
        Raises:
            InvalidToken: If decryption fails
        """
        try:
            decrypted = self.fernet.decrypt(encrypted_data.encode())
            credentials = json.loads(decrypted.decode())
            return credentials
        except InvalidToken as e:
            logger.error("Failed to decrypt credentials: invalid token")
            raise
        except json.JSONDecodeError as e:
            logger.error("Failed to parse decrypted credentials")
            raise ValueError("Corrupted credential data") from e


# Global encryption service instance
encryption = EncryptionService()


def encrypt_credentials(device_id: str, account_id: str, secret: str, client_token: str = None) -> str:
    """Convenience function to encrypt credentials."""
    return encryption.encrypt_credentials(device_id, account_id, secret, client_token)


def decrypt_credentials(encrypted_data: str) -> dict:
    """Convenience function to decrypt credentials."""
    return encryption.decrypt_credentials(encrypted_data)
