"""Device authentication service for Epic Games accounts."""
import asyncio
import logging
import aiohttp
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Epic Games OAuth endpoints
EPIC_DEVICE_AUTH_URL = "https://www.epicgames.com/id/api/redirect?clientId=3446cd72694c4a4485d81b77adbb2141&responseType=code"
EPIC_TOKEN_URL = "https://account-public-service-prod.ol.epicgames.com/account/api/oauth/token"
EPIC_DEVICE_AUTH_CREATE_URL = "https://account-public-service-prod.ol.epicgames.com/account/api/public/account/{account_id}/deviceAuth"

# Fortnite client credentials (public launcher token)
FORTNITE_CLIENT_ID = "3446cd72694c4a4485d81b77adbb2141"
FORTNITE_CLIENT_SECRET = "9209d4a5e25a457fb9b07489d313b41a"


class DeviceAuthService:
    """Service for handling Epic Games device auth flow."""
    
    @staticmethod
    def get_auth_url() -> str:
        """Get the URL for users to authorize their Epic account."""
        return EPIC_DEVICE_AUTH_URL
    
    @staticmethod
    async def exchange_code_for_device_auth(
        authorization_code: str
    ) -> Tuple[bool, Optional[dict], Optional[str]]:
        """
        Exchange authorization code for device auth credentials.
        
        Args:
            authorization_code: The code from Epic's OAuth redirect
            
        Returns:
            Tuple of (success, credentials_dict, error_message)
            credentials_dict contains: device_id, account_id, secret, display_name
        """
        try:
            async with aiohttp.ClientSession() as session:
                # Step 1: Exchange code for access token
                auth_header = aiohttp.BasicAuth(FORTNITE_CLIENT_ID, FORTNITE_CLIENT_SECRET)
                
                token_data = {
                    "grant_type": "authorization_code",
                    "code": authorization_code
                }
                
                async with session.post(
                    EPIC_TOKEN_URL,
                    data=token_data,
                    auth=auth_header
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Token exchange failed: {error_text}")
                        return False, None, "Failed to exchange authorization code. It may have expired."
                    
                    token_response = await response.json()
                
                access_token = token_response.get("access_token")
                account_id = token_response.get("account_id")
                display_name = token_response.get("displayName", "Unknown")
                
                if not access_token or not account_id:
                    return False, None, "Invalid response from Epic Games"
                
                # Step 2: Create device auth credentials
                headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                }
                
                device_auth_url = EPIC_DEVICE_AUTH_CREATE_URL.format(account_id=account_id)
                
                async with session.post(
                    device_auth_url,
                    headers=headers,
                    json={}
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Device auth creation failed: {error_text}")
                        return False, None, "Failed to create device authentication"
                    
                    device_auth = await response.json()
                
                credentials = {
                    "device_id": device_auth.get("deviceId"),
                    "account_id": device_auth.get("accountId"),
                    "secret": device_auth.get("secret"),
                    "display_name": display_name
                }
                
                if not all([credentials["device_id"], credentials["account_id"], credentials["secret"]]):
                    return False, None, "Incomplete device auth credentials received"
                
                logger.info(f"Successfully created device auth for {display_name}")
                return True, credentials, None
                
        except aiohttp.ClientError as e:
            logger.error(f"Network error during device auth: {e}")
            return False, None, "Network error while communicating with Epic Games"
        except Exception as e:
            logger.error(f"Unexpected error during device auth: {e}")
            return False, None, f"Unexpected error: {str(e)}"
    
    @staticmethod
    async def verify_device_auth(
        device_id: str,
        account_id: str,
        secret: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify that device auth credentials are still valid.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            async with aiohttp.ClientSession() as session:
                auth_header = aiohttp.BasicAuth(FORTNITE_CLIENT_ID, FORTNITE_CLIENT_SECRET)
                
                token_data = {
                    "grant_type": "device_auth",
                    "device_id": device_id,
                    "account_id": account_id,
                    "secret": secret
                }
                
                async with session.post(
                    EPIC_TOKEN_URL,
                    data=token_data,
                    auth=auth_header
                ) as response:
                    if response.status == 200:
                        return True, None
                    elif response.status == 400:
                        return False, "Device auth has expired or been revoked"
                    elif response.status == 403:
                        return False, "Account may be banned or restricted"
                    else:
                        return False, f"Verification failed with status {response.status}"
                        
        except Exception as e:
            logger.error(f"Error verifying device auth: {e}")
            return False, f"Verification error: {str(e)}"


# Global instance
device_auth_service = DeviceAuthService()
