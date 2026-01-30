#!/usr/bin/env python3
"""
ThingsBoard API client for retrieving device alarms and telemetry.
"""

import requests
import logging
from typing import Optional, Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)


class ThingsBoardClient:
    """
    Client for interacting with ThingsBoard REST API.
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
                verify=False  # Disable SSL verification
            )
            response.raise_for_status()
            
            data = response.json()
            self.token = data.get("token")
            
            if not self.token:
                logger.error("Authentication successful but no token received")
                return False
                
            logger.info("✅ ThingsBoard authentication successful")
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Authentication failed: {e}")
            return False
    
    def get_device_id_by_name(self, device_name: str) -> Optional[str]:
        """
        Retrieve Device ID by device name.
        
        Args:
            device_name: Name of the device in ThingsBoard
            
        Returns:
            Device ID (UUID) or None if not found
        """
        if not self.token:
            logger.error("Not authenticated. Call authenticate() first.")
            return None
            
        url = f"{self.base_url}/api/tenant/devices"
        params = {"deviceName": device_name}
        headers = {"X-Authorization": f"Bearer {self.token}"}
        
        try:
            response = self.session.get(url, params=params, headers=headers, verify=False)
            response.raise_for_status()
            
            data = response.json()
            devices = data.get("data", [])
            
            if not devices:
                logger.warning(f"⚠️  Device '{device_name}' not found")
                return None
                
            device_id = devices[0].get("id", {}).get("id")
            logger.info(f"✅ Device ID found: {device_id}")
            return device_id
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Failed to retrieve device ID: {e}")
            return None
    
    def get_alarms(self, entity_id: str, entity_type: str = "DEVICE", 
                   status: str = "ACTIVE_UNACK", page_size: int = 50,
                   start_ts: Optional[int] = None, end_ts: Optional[int] = None) -> Optional[Dict]:
        """
        Retrieve alarms for a specific entity.
        
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
        if not self.token:
            logger.error("Not authenticated. Call authenticate() first.")
            return None
            
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
        
        try:
            response = self.session.get(url, params=params, headers=headers, verify=False)
            response.raise_for_status()
            
            data = response.json()
            alarm_count = data.get("totalElements", 0)
            logger.info(f"✅ Retrieved {alarm_count} alarm(s) for entity {entity_id}")
            return data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Failed to retrieve alarms: {e}")
            return None
    '''   
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
        if not self.token:
            logger.error("Not authenticated. Call authenticate() first.")
            return None
            
        url = f"{self.base_url}/api/plugins/telemetry/{entity_type}/{entity_id}/values/timeseries"
        params = {}
        
        if keys:
            params["keys"] = ",".join(keys)
        if start_ts:
            params["startTs"] = start_ts
        if end_ts:
            params["endTs"] = end_ts
            
        headers = {"X-Authorization": f"Bearer {self.token}"}
        
        try:
            response = self.session.get(url, params=params, headers=headers, verify=False)
            response.raise_for_status()
            
            data = response.json()
            logger.info(f"✅ Retrieved telemetry data for entity {entity_id}")
            return data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Failed to retrieve telemetry: {e}")
            return None
    '''

def datetime_to_epoch_ms(dt: datetime) -> int:
    """
    Convert datetime object to epoch timestamp in milliseconds.
    
    Args:
        dt: datetime object
        
    Returns:
        Timestamp in milliseconds
    """
    return int(dt.timestamp() * 1000)