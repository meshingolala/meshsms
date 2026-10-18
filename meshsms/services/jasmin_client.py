import logging
import uuid
from typing import Optional
import httpx

from meshsms.config import settings

logger = logging.getLogger("meshsms.jasmin_client")


class JasminRouterError(Exception):
    """Exception raised when Jasmin SMS Gateway returns an error or fails."""
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class JasminClient:
    """Client for Jasmin SMS Gateway HTTP API."""

    def __init__(
        self,
        send_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        dlr_url: Optional[str] = None,
        mock_mode: Optional[bool] = None,
    ):
        self.send_url = send_url or settings.JASMIN_SEND_URL
        self.username = username or settings.JASMIN_USER
        self.password = password or settings.JASMIN_PASS
        self.dlr_url = dlr_url or settings.PUBLIC_DLR_CALLBACK_URL
        self.mock_mode = settings.MOCK_JASMIN if mock_mode is None else mock_mode

    async def send_sms(
        self,
        sender_id: str,
        recipient: str,
        content: str,
        coding: int = 0,
        dlr_url: Optional[str] = None,
        dlr_level: int = 2,
        priority: int = 0,
    ) -> str:
        """
        Sends an SMS via Jasmin HTTP API.
        
        Returns the carrier/Jasmin message ID on success.
        Raises JasminRouterError on failure.
        """
        if self.mock_mode:
            mock_id = f"jasmin_mock_{uuid.uuid4().hex[:12]}"
            logger.info("MOCK_JASMIN active: Simulated Jasmin message ID %s", mock_id)
            return mock_id

        # Clean recipient to remove leading plus if present
        clean_to = recipient.lstrip("+")
        callback_url = dlr_url or self.dlr_url

        params = {
            "username": self.username,
            "password": self.password,
            "to": clean_to,
            "from": sender_id,
            "content": content,
            "coding": coding,
            "dlr": "yes",
            "dlr-url": callback_url,
            "dlr-level": dlr_level,
            "dlr-method": "POST",
            "priority": priority,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.send_url, params=params)

            resp_text = response.text.strip()

            # Jasmin returns 'Success "<msgid>"' on 200 OK
            if response.status_code == 200 and resp_text.startswith("Success"):
                # Extract message id between quotes
                try:
                    jasmin_msgid = resp_text.split('"')[1]
                    logger.info("Jasmin accepted message: %s -> %s", recipient, jasmin_msgid)
                    return jasmin_msgid
                except IndexError:
                    raise JasminRouterError(f"Malformed success response from Jasmin: {resp_text}")
            else:
                logger.error("Jasmin returned error (HTTP %s): %s", response.status_code, resp_text)
                raise JasminRouterError(
                    f"SMPP Router Error: {resp_text or response.status_code}",
                    status_code=502,
                )

        except httpx.RequestError as exc:
            logger.error("Failed to connect to Jasmin HTTP API at %s: %s", self.send_url, exc)
            raise JasminRouterError(
                f"Failed to connect to Jasmin SMS Gateway: {str(exc)}",
                status_code=503,
            )


jasmin_client = JasminClient()
