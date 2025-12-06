"""Device authentication service for Epic Games accounts.

Uses Device Code flow for authentication:
1. Bot gets client credentials token first
2. Bot requests a device code from Epic Games
3. User visits Epic Games activate page and enters the code
4. Bot polls Epic Games until user completes login
5. Exchange for device auth credentials for future logins

This is the most user-friendly approach - no copying authorization codes.
"""
import asyncio
import logging
import aiohttp
import base64
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)

# Epic Games OAuth endpoints
EPIC_TOKEN_URL = "https://account-public-service-prod.ol.epicgames.com/account/api/oauth/token"
EPIC_DEVICE_CODE_URL = "https://account-public-service-prod03.ol.epicgames.com/account/api/oauth/deviceAuthorization"
EPIC_EXCHANGE_URL = "https://account-public-service-prod.ol.epicgames.com/account/api/oauth/exchange"
EPIC_DEVICE_AUTH_CREATE_URL = "https://account-public-service-prod.ol.epicgames.com/account/api/public/account/{account_id}/deviceAuth"

# fortniteNewSwitchGameClient - supports device_code flow
SWITCH_CLIENT_ID = "98f7e42c2e3a4f86a74eb43fbb41ed39"
SWITCH_CLIENT_SECRET = "0a2449a2-001a-451e-afec-3e812901c4d7"
SWITCH_TOKEN = base64.b64encode(f"{SWITCH_CLIENT_ID}:{SWITCH_CLIENT_SECRET}".encode()).decode()

# fortniteIOSGameClient - has deviceAuths permission (but currently disabled)
IOS_CLIENT_ID = "3446cd72694c4a4485d81b77adbb2141"
IOS_CLIENT_SECRET = "9209d4a5e25a457fb9b07489d313b41a"
IOS_TOKEN = base64.b64encode(f"{IOS_CLIENT_ID}:{IOS_CLIENT_SECRET}".encode()).decode()

# fortniteAndroidGameClient - has deviceAuths permission
ANDROID_CLIENT_ID = "3f69e56c7649492c8cc29f1af08a8a12"
ANDROID_CLIENT_SECRET = "b51ee9cb12234f50a69efa67ef53812e"
ANDROID_TOKEN = base64.b64encode(f"{ANDROID_CLIENT_ID}:{ANDROID_CLIENT_SECRET}".encode()).decode()


class DeviceCodeSession:
    """Represents an active device code authentication session."""
    
    def __init__(self, device_code: str, user_code: str, verification_uri: str, 
                 expires_in: int, interval: int):
        self.device_code = device_code
        self.user_code = user_code
        self.verification_uri = verification_uri
        self.expires_in = expires_in
        self.interval = interval
        self._cancelled = False
    
    def cancel(self):
        """Cancel this session."""
        self._cancelled = True
    
    @property
    def is_cancelled(self) -> bool:
        return self._cancelled


class DeviceAuthService:
    """Service for handling Epic Games device auth flow.
    
    Uses device_code flow for user-friendly authentication.
    Bot generates a code, user enters it on Epic's website.
    """
    
    def __init__(self):
        self._active_sessions: Dict[str, DeviceCodeSession] = {}
    
    async def start_device_code_flow(self, discord_id: str) -> Tuple[bool, Optional[DeviceCodeSession], Optional[str]]:
        """
        Start a device code authentication flow.
        
        Args:
            discord_id: The Discord user ID starting the flow
            
        Returns:
            Tuple of (success, session, error_message)
        """
        try:
            async with aiohttp.ClientSession() as session:
                # Step 1: Get client credentials token first
                logger.info("Getting client credentials token...")
                
                client_creds_headers = {
                    "Authorization": f"Basic {SWITCH_TOKEN}",
                    "Content-Type": "application/x-www-form-urlencoded"
                }
                
                async with session.post(
                    EPIC_TOKEN_URL,
                    headers=client_creds_headers,
                    data={"grant_type": "client_credentials"}
                ) as response:
                    response_text = await response.text()
                    
                    if response.status != 200:
                        logger.error(f"Client credentials failed: {response_text}")
                        return False, None, f"Failed to get client token: {response_text[:200]}"
                    
                    client_token_data = await response.json()
                
                client_access_token = client_token_data.get("access_token")
                if not client_access_token:
                    return False, None, "Failed to get client access token"
                
                logger.info("Got client credentials, requesting device code...")
                
                # Step 2: Request device code with the client token
                device_code_headers = {
                    "Authorization": f"Bearer {client_access_token}",
                    "Content-Type": "application/x-www-form-urlencoded"
                }
                
                async with session.post(
                    EPIC_DEVICE_CODE_URL,
                    headers=device_code_headers,
                    data={"prompt": "login"}
                ) as response:
                    response_text = await response.text()
                    
                    if response.status != 200:
                        logger.error(f"Device code request failed: {response_text}")
                        
                        if "unsupported_grant_type" in response_text:
                            return False, None, "Device code flow not supported by this client."
                        
                        return False, None, f"Failed to start authentication: {response_text[:200]}"
                    
                    data = await response.json()
                
                # Build verification URI
                verification_uri = data.get("verification_uri_complete")
                if not verification_uri:
                    # Build it manually if not provided
                    base_uri = data.get("verification_uri", "https://www.epicgames.com/activate")
                    user_code = data.get("user_code")
                    verification_uri = f"{base_uri}?userCode={user_code}"
                
                device_code_session = DeviceCodeSession(
                    device_code=data.get("device_code"),
                    user_code=data.get("user_code"),
                    verification_uri=verification_uri,
                    expires_in=data.get("expires_in", 600),
                    interval=data.get("interval", 5)
                )
                
                # Store session
                self._active_sessions[discord_id] = device_code_session
                
                logger.info(f"Started device code flow for {discord_id}, code: {device_code_session.user_code}")
                
                return True, device_code_session, None
                
        except Exception as e:
            logger.error(f"Error starting device code flow: {e}")
            return False, None, str(e)
    
    async def poll_for_completion(
        self, 
        discord_id: str,
        on_status_update: Optional[callable] = None
    ) -> Tuple[bool, Optional[dict], Optional[str]]:
        """
        Poll Epic Games until user completes login or session expires.
        
        Args:
            discord_id: The Discord user ID
            on_status_update: Optional callback for status updates
            
        Returns:
            Tuple of (success, credentials_dict, error_message)
        """
        session = self._active_sessions.get(discord_id)
        if not session:
            return False, None, "No active authentication session found."
        
        try:
            async with aiohttp.ClientSession() as http_session:
                start_time = asyncio.get_event_loop().time()
                
                while True:
                    # Check if cancelled
                    if session.is_cancelled:
                        return False, None, "Authentication cancelled."
                    
                    # Check if expired
                    elapsed = asyncio.get_event_loop().time() - start_time
                    if elapsed >= session.expires_in:
                        return False, None, "Authentication timed out. Please try again."
                    
                    # Poll for token
                    headers = {
                        "Authorization": f"Basic {SWITCH_TOKEN}",
                        "Content-Type": "application/x-www-form-urlencoded"
                    }
                    
                    data = {
                        "grant_type": "device_code",
                        "device_code": session.device_code
                    }
                    
                    async with http_session.post(
                        EPIC_TOKEN_URL,
                        headers=headers,
                        data=data
                    ) as response:
                        response_text = await response.text()
                        
                        if response.status == 200:
                            # Success! User completed login
                            token_response = await response.json()
                            
                            # Now get device auth credentials
                            result = await self._create_device_auth(
                                http_session,
                                token_response.get("access_token"),
                                token_response.get("account_id"),
                                token_response.get("displayName", "Unknown")
                            )
                            
                            # Clean up session
                            if discord_id in self._active_sessions:
                                del self._active_sessions[discord_id]
                            
                            return result
                        
                        elif response.status == 400:
                            try:
                                error_data = await response.json()
                                error_code = error_data.get("errorCode", "")
                                
                                if "authorization_pending" in error_code:
                                    # Still waiting for user
                                    if on_status_update:
                                        remaining = int(session.expires_in - elapsed)
                                        await on_status_update(f"Waiting for login... ({remaining}s remaining)")
                                    
                                elif "slow_down" in error_code:
                                    # Polling too fast
                                    await asyncio.sleep(session.interval * 2)
                                    continue
                                    
                                elif "expired_token" in error_code or "expired" in error_code:
                                    if discord_id in self._active_sessions:
                                        del self._active_sessions[discord_id]
                                    return False, None, "The code has expired. Please try again."
                                    
                                elif "access_denied" in error_code:
                                    if discord_id in self._active_sessions:
                                        del self._active_sessions[discord_id]
                                    return False, None, "Access was denied. Please try again."
                                    
                                else:
                                    logger.warning(f"Unexpected error during poll: {error_code}")
                                    
                            except Exception:
                                pass
                        
                        else:
                            logger.error(f"Unexpected poll response: {response.status} - {response_text}")
                    
                    # Wait before next poll
                    await asyncio.sleep(session.interval)
                    
        except Exception as e:
            logger.error(f"Error polling for completion: {e}")
            if discord_id in self._active_sessions:
                del self._active_sessions[discord_id]
            return False, None, str(e)
    
    async def _create_device_auth(
        self, 
        http_session: aiohttp.ClientSession,
        switch_access_token: str,
        account_id: str,
        display_name: str
    ) -> Tuple[bool, Optional[dict], Optional[str]]:
        """
        Create device auth credentials.
        
        Try creating device auth directly with Switch token first.
        If that fails (Switch might not have deviceAuths permission), 
        fall back to exchange code flow with Android.
        """
        try:
            # First, try creating device auth directly with Switch token
            logger.info("Attempting to create device auth with Switch client...")
            
            device_auth_headers = {
                "Authorization": f"Bearer {switch_access_token}",
                "Content-Type": "application/json"
            }
            
            device_auth_url = EPIC_DEVICE_AUTH_CREATE_URL.format(account_id=account_id)
            
            async with http_session.post(
                device_auth_url,
                headers=device_auth_headers,
                json={}
            ) as response:
                response_text = await response.text()
                
                if response.status == 200:
                    # Switch works! Use it
                    device_auth = await response.json()
                    
                    credentials = {
                        "device_id": device_auth.get("deviceId"),
                        "account_id": device_auth.get("accountId"),
                        "secret": device_auth.get("secret"),
                        "display_name": display_name,
                        "client_token": SWITCH_TOKEN  # Store Switch token since it was used
                    }
                    
                    logger.info(f"Successfully created device auth with Switch client for {display_name}")
                    return True, credentials, None
                
                elif "permission" in response_text.lower() or response.status == 403:
                    # Switch doesn't have permission, fall back to Android
                    logger.info("Switch client doesn't have deviceAuths permission, trying Android...")
                else:
                    logger.warning(f"Switch device auth failed ({response.status}): {response_text[:200]}")
            
            # Fallback: Get exchange code and use Android client
            logger.info("Getting exchange code for Android fallback...")
            
            exchange_headers = {
                "Authorization": f"Bearer {switch_access_token}",
            }
            
            async with http_session.get(
                EPIC_EXCHANGE_URL,
                headers=exchange_headers
            ) as response:
                if response.status != 200:
                    response_text = await response.text()
                    logger.error(f"Exchange code request failed: {response_text}")
                    return False, None, f"Failed to get exchange code: {response_text[:200]}"
                
                exchange_response = await response.json()
            
            exchange_code = exchange_response.get("code")
            if not exchange_code:
                return False, None, "Failed to get exchange code from Epic Games"
            
            logger.info("Got exchange code, authenticating with Android client...")
            
            # Exchange for Android token (has deviceAuths permission)
            android_token_data = {
                "grant_type": "exchange_code",
                "exchange_code": exchange_code,
            }
            
            android_headers = {
                "Authorization": f"Basic {ANDROID_TOKEN}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            async with http_session.post(
                EPIC_TOKEN_URL,
                data=android_token_data,
                headers=android_headers
            ) as response:
                if response.status != 200:
                    response_text = await response.text()
                    logger.error(f"Android token exchange failed: {response_text}")
                    
                    if "client_disabled" in response_text:
                        return False, None, "Android client is currently disabled by Epic Games. Please try again later."
                    
                    return False, None, f"Failed to get Android token: {response_text[:200]}"
                
                android_token_response = await response.json()
            
            android_access_token = android_token_response.get("access_token")
            if not android_access_token:
                return False, None, "Failed to get Android access token"
            
            logger.info("Got Android token, creating device auth...")
            
            # Create device auth credentials using Android token
            device_auth_headers = {
                "Authorization": f"Bearer {android_access_token}",
                "Content-Type": "application/json"
            }
            
            async with http_session.post(
                device_auth_url,
                headers=device_auth_headers,
                json={}
            ) as response:
                response_text = await response.text()
                if response.status != 200:
                    logger.error(f"Device auth creation failed (status {response.status}): {response_text}")
                    
                    if "permission" in response_text.lower():
                        return False, None, "This client doesn't have permission to create device auth."
                    
                    return False, None, f"Failed to create device auth: {response_text[:200]}"
                
                device_auth = await response.json()
            
            credentials = {
                "device_id": device_auth.get("deviceId"),
                "account_id": device_auth.get("accountId"),
                "secret": device_auth.get("secret"),
                "display_name": display_name,
                "client_token": ANDROID_TOKEN  # Store the Android client token
            }
            
            logger.info(f"Successfully created device auth with Android client for {display_name}")
            
            return True, credentials, None
            
        except Exception as e:
            logger.error(f"Error creating device auth: {e}")
            return False, None, str(e)
    
    def cancel_session(self, discord_id: str) -> bool:
        """Cancel an active session for a user."""
        session = self._active_sessions.get(discord_id)
        if session:
            session.cancel()
            del self._active_sessions[discord_id]
            return True
        return False
    
    async def verify_device_auth(
        self,
        device_id: str,
        account_id: str,
        secret: str,
        client_token: Optional[str] = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Verify that device auth credentials are still valid.
        
        Args:
            device_id: The device ID
            account_id: The Epic account ID
            secret: The device auth secret
            client_token: Optional client token (defaults to iOS)
            
        Returns:
            Tuple of (valid, display_name, error_message)
        """
        token = client_token or ANDROID_TOKEN
        
        try:
            async with aiohttp.ClientSession() as session:
                data = {
                    "grant_type": "device_auth",
                    "device_id": device_id,
                    "account_id": account_id,
                    "secret": secret
                }
                
                headers = {
                    "Authorization": f"Basic {token}",
                    "Content-Type": "application/x-www-form-urlencoded"
                }
                
                async with session.post(
                    EPIC_TOKEN_URL,
                    data=data,
                    headers=headers
                ) as response:
                    if response.status == 200:
                        token_data = await response.json()
                        return True, token_data.get("displayName", "Unknown"), None
                    else:
                        response_text = await response.text()
                        logger.error(f"Device auth verification failed: {response_text}")
                        
                        if "invalid_grant" in response_text:
                            return False, None, "Device auth credentials are invalid or expired."
                        elif "client_disabled" in response_text:
                            return False, None, "Epic Games client is currently disabled."
                        
                        return False, None, f"Verification failed: {response_text[:100]}"
                        
        except Exception as e:
            logger.error(f"Error verifying device auth: {e}")
            return False, None, str(e)


# Global service instance
device_auth_service = DeviceAuthService()
