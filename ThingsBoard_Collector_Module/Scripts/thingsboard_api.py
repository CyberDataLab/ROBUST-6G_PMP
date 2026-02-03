#!/usr/bin/env python3
"""
ThingsBoard API client for retrieving device alarms and telemetry.
"""

import requests
import logging
import time
from typing import Optional, Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)


class ThingsBoardClient:
    """
    Client for interacting with ThingsBoard REST API with automatic token refresh.
    """
    
    def __init__(self, host: str, port: int = 80, username: str = "tenant@thingsboard.org", 
                 password: str = "tenant", use_https: bool = False):
        """
        Initialize ThingsBoard client.
        
        Args:
            host: ThingsBoard server hostname or IP
            port: ThingsBoard server port (default 80)
            username: ThingsBoard username
            password: ThingsBoard password
            use_https: Use HTTPS instead of HTTP
        """
        protocol = "https" if use_https else "http"
        self.base_url = f"{protocol}://{host}:{port}"
        self.username = username
        self.password = password
        self.token: Optional[str] = None
        self.session = requests.Session()
        self.last_auth_time: float = 0
        self.auth_refresh_interval: int = 7200  # 2 hours in seconds
        
    def authenticate(self) -> bool:
        """
        Authenticate with ThingsBoard and retrieve JWT token.
        
        Returns:
            True if authentication successful, False otherwise
        """
        url = f"{self.base_url}/api/auth/login"
        payload = {
            "username": self.username,
            "password": self.password
        }
        
        try:
            response = self.session.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                verify=False,
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            self.token = data.get("token")
            
            if not self.token:
                logger.error("Authentication successful but no token received")
                return False
            
            self.last_auth_time = time.time()
            logger.info("✅ ThingsBoard authentication successful")
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Authentication failed: {e}")
            return False
    
    def _ensure_authenticated(self) -> bool:
        """
        Ensure that there is a valid token, re-authenticating if necessary.
        
        Returns:
            True if authenticated, False otherwise
        """
        if not self.token or (time.time() - self.last_auth_time) > self.auth_refresh_interval:
            logger.info("Token expired or missing, re-authenticating...")
            return self.authenticate()
        return True
    
    def _handle_request_with_retry(self, request_func, max_retries: int = 3) -> Optional[Dict]:
        """
        Execute a request with automatic retry and re-authentication on 401.
        
        Args:
            request_func: Function that performs the actual request
            max_retries: Maximum number of retry attempts
            
        Returns:
            Response JSON or None if all retries failed
        """
        retry_delays = [5, 15, 30]  # Exponential backoff
        
        for attempt in range(max_retries):
            try:
                if not self._ensure_authenticated():
                    logger.error("Failed to authenticate before request")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delays[min(attempt, len(retry_delays) - 1)])
                        continue
                    return None
                
                response = request_func()
                
                # Error 401 (expired token)
                if response.status_code == 401:
                    logger.warning("Got 401, re-authenticating...")
                    self.token = None  # Force re-auth
                    if attempt < max_retries - 1:
                        continue
                    return None
                
                response.raise_for_status()
                return response.json()
                
            except requests.exceptions.Timeout:
                logger.warning(f"Request timeout (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(retry_delays[min(attempt, len(retry_delays) - 1)])
                    continue
                return None
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delays[min(attempt, len(retry_delays) - 1)])
                    continue
                return None
        
        return None
    
    def get_device_id_by_name(self, device_name: str) -> Optional[str]:
        """
        Retrieve Device ID by device name.
        
        Args:
            device_name: Name of the device in ThingsBoard
            
        Returns:
            Device ID (UUID) or None if not found
        """
        def _request():
            url = f"{self.base_url}/api/tenant/devices"
            params = {"deviceName": device_name}
            headers = {"X-Authorization": f"Bearer {self.token}"}
            return self.session.get(url, params=params, headers=headers, verify=False, timeout=10)
        
        data = self._handle_request_with_retry(_request)
        
        if not data:
            return None
        
        devices = data.get("data", [])
        if not devices:
            logger.warning(f"⚠️  Device '{device_name}' not found")
            return None
        
        device_id = devices[0].get("id", {}).get("id")
        logger.info(f"✅ Device ID found: {device_id}")
        return device_id
    
    def get_alarms(self, entity_id: str, entity_type: str = "DEVICE", 
                   status: str = "ACTIVE_UNACK", page_size: int = 50,
                   start_ts: Optional[int] = None, end_ts: Optional[int] = None) -> Optional[Dict]:
        """
        Retrieve alarms for a specific entity with automatic retry.
        
        Args:
            entity_id: Entity UUID (e.g., device ID)
            entity_type: Type of entity (DEVICE, ASSET, etc.)
            status: Alarm status filter (ACTIVE_UNACK, ACTIVE_ACK, CLEARED_ACK, ANY)
            page_size: Number of alarms to retrieve per page
            start_ts: Start timestamp in milliseconds (optional)
            end_ts: End timestamp in milliseconds (optional)
            
        Returns:
            JSON response with alarms or None if request fails
        """
        def _request():
            url = f"{self.base_url}/api/alarm/{entity_type}/{entity_id}"
            params = {
                "pageSize": page_size,
                "page": 0,
                "status": status,
                "fetchOriginator": "true"
            }
            
            if start_ts:
                params["startTime"] = start_ts
            if end_ts:
                params["endTime"] = end_ts
            
            headers = {"X-Authorization": f"Bearer {self.token}"}
            return self.session.get(url, params=params, headers=headers, verify=False, timeout=10)
        
        data = self._handle_request_with_retry(_request)
        
        if data:
            alarm_count = data.get("totalElements", 0)
            logger.debug(f"Retrieved {alarm_count} alarm(s) for entity {entity_id}")
        
        return data
    
    def get_telemetry(self, entity_id: str, entity_type: str = "DEVICE",
                      keys: Optional[List[str]] = None, 
                      start_ts: Optional[int] = None, 
                      end_ts: Optional[int] = None) -> Optional[Dict]:
        """
        Retrieve telemetry data for a specific entity.
        
        Args:
            entity_id: Entity UUID
            entity_type: Type of entity (DEVICE, ASSET, etc.)
            keys: List of telemetry keys to retrieve (None = all)
            start_ts: Start timestamp in milliseconds
            end_ts: End timestamp in milliseconds
            
        Returns:
            JSON response with telemetry data or None if request fails
        """
        def _request():
            url = f"{self.base_url}/api/plugins/telemetry/{entity_type}/{entity_id}/values/timeseries"
            params = {}
            
            if keys:
                params["keys"] = ",".join(keys)
            if start_ts:
                params["startTs"] = start_ts
            if end_ts:
                params["endTs"] = end_ts
            
            headers = {"X-Authorization": f"Bearer {self.token}"}
            return self.session.get(url, params=params, headers=headers, verify=False, timeout=10)
        
        data = self._handle_request_with_retry(_request)
        
        if data:
            logger.info(f"✅ Retrieved telemetry data for entity {entity_id}")
        
        return data


def datetime_to_epoch_ms(dt: datetime) -> int:
    """
    Convert datetime object to epoch timestamp in milliseconds.
    
    Args:
        dt: datetime object
        
    Returns:
        Timestamp in milliseconds
    """
    return int(dt.timestamp() * 1000)