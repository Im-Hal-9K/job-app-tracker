"""Gmail API integration for fetching job-related emails."""

import base64
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

TOKEN_PATH = os.getenv('GMAIL_TOKEN_PATH', 'config/token.json')
CREDS_PATH = os.getenv('GMAIL_CREDS_PATH', 'config/gmail_credentials.json')

# Labels to scan - comma-separated list, defaults to INBOX
# Can include: INBOX, STARRED, SENT, or custom labels like "Jobs", "Applications"
GMAIL_LABELS = os.getenv('GMAIL_LABELS', 'INBOX')


class GmailService:
    """Gmail API service wrapper."""

    def __init__(self):
        self.service = None
        self._labels_cache = None

    def authenticate(self) -> bool:
        """
        Authenticate with Gmail API.

        Returns:
            True if authentication successful, False otherwise.
        """
        creds = None

        if os.path.exists(TOKEN_PATH):
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Refreshing expired token...")
                try:
                    creds.refresh(Request())
                    with open(TOKEN_PATH, 'w') as token:
                        token.write(creds.to_json())
                except Exception as e:
                    logger.error(f"Failed to refresh token: {e}")
                    return False
            elif os.path.exists(CREDS_PATH):
                logger.info("Running OAuth flow...")
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
                    creds = flow.run_local_server(port=0)
                    with open(TOKEN_PATH, 'w') as token:
                        token.write(creds.to_json())
                except Exception as e:
                    logger.error(f"OAuth flow failed: {e}")
                    return False
            else:
                logger.error(f"No credentials found at {CREDS_PATH}")
                return False

        try:
            self.service = build('gmail', 'v1', credentials=creds)
            return True
        except Exception as e:
            logger.error(f"Failed to build Gmail service: {e}")
            return False

    def is_configured(self) -> bool:
        """Check if Gmail credentials are configured."""
        return os.path.exists(TOKEN_PATH) or os.path.exists(CREDS_PATH)

    def get_labels(self) -> list[dict[str, str]]:
        """
        Get all available Gmail labels.

        Returns:
            List of label objects with 'id' and 'name'.
        """
        if self._labels_cache:
            return self._labels_cache

        if not self.service:
            if not self.authenticate():
                return []

        try:
            response = self.service.users().labels().list(userId='me').execute()
            labels = response.get('labels', [])
            self._labels_cache = [{'id': l['id'], 'name': l['name']} for l in labels]
            return self._labels_cache
        except HttpError as e:
            logger.error(f"Failed to get labels: {e}")
            return []

    def get_label_id(self, label_name: str) -> Optional[str]:
        """
        Get label ID by name.

        Args:
            label_name: The label name (e.g., "Jobs", "INBOX")

        Returns:
            The label ID, or None if not found.
        """
        labels = self.get_labels()
        for label in labels:
            if label['name'].lower() == label_name.lower():
                return label['id']
        return None

    def fetch_messages(
        self,
        since_hours: int = 24,
        max_results: int = 100,
        labels: Optional[list[str]] = None
    ) -> list[dict[str, Any]]:
        """
        Fetch messages from specified labels.

        Args:
            since_hours: Only fetch emails from the last N hours.
            max_results: Maximum number of messages to return.
            labels: List of label names to scan. Defaults to GMAIL_LABELS env var.

        Returns:
            List of message objects with 'id' and 'threadId'.
        """
        if not self.service:
            if not self.authenticate():
                return []

        # Use provided labels or fall back to env config
        if labels is None:
            labels = [l.strip() for l in GMAIL_LABELS.split(',') if l.strip()]

        time_threshold = (datetime.now() - timedelta(hours=since_hours)).strftime('%Y/%m/%d')
        query = f"after:{time_threshold}"

        all_messages = []
        seen_ids = set()

        # Fetch from each label
        for label_name in labels:
            # Convert label name to ID (for custom labels)
            if label_name.upper() in ['INBOX', 'SENT', 'SPAM', 'TRASH', 'DRAFT', 'STARRED', 'UNREAD', 'IMPORTANT']:
                label_ids = [label_name.upper()]
            else:
                label_id = self.get_label_id(label_name)
                if not label_id:
                    logger.warning(f"Label not found: {label_name}")
                    continue
                label_ids = [label_id]

            try:
                logger.info(f"Fetching from label: {label_name}")
                response = self.service.users().messages().list(
                    userId='me',
                    labelIds=label_ids,
                    q=query,
                    maxResults=max_results
                ).execute()

                messages = response.get('messages', [])
                for msg in messages:
                    if msg['id'] not in seen_ids:
                        seen_ids.add(msg['id'])
                        all_messages.append(msg)

                logger.info(f"Fetched {len(messages)} messages from {label_name}")

            except HttpError as e:
                logger.error(f"Gmail API error for label {label_name}: {e}")

        logger.info(f"Total unique messages fetched: {len(all_messages)}")
        return all_messages

    def get_message_content(self, message_id: str) -> dict[str, Any]:
        """
        Get full message content.

        Args:
            message_id: Gmail message ID.

        Returns:
            Dictionary with 'snippet', 'subject', 'from', 'body', 'date', 'thread_id'.
        """
        if not self.service:
            return {}

        try:
            message = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()

            payload = message.get('payload', {})
            headers = payload.get('headers', [])

            # Extract headers
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), '')
            from_addr = next((h['value'] for h in headers if h['name'].lower() == 'from'), '')

            # Extract body
            body = self._extract_body(payload)

            # Parse date
            internal_date = int(message.get('internalDate', 0)) / 1000
            email_date = datetime.fromtimestamp(internal_date) if internal_date else None

            # Get labels for this message
            label_ids = message.get('labelIds', [])

            return {
                'id': message_id,
                'thread_id': message.get('threadId', ''),
                'snippet': message.get('snippet', ''),
                'subject': subject,
                'from': from_addr,
                'body': body[:4000] if body else '',  # Truncate for API limits
                'date': email_date,
                'labels': label_ids
            }

        except HttpError as e:
            logger.error(f"Failed to get message {message_id}: {e}")
            return {}

    def _extract_body(self, payload: dict) -> str:
        """Extract plain text body from message payload."""
        parts = payload.get('parts', [])
        body = ""

        if parts:
            for part in parts:
                if part.get('mimeType') == 'text/plain':
                    data = part.get('body', {}).get('data', '')
                    if data:
                        body += base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        else:
            data = payload.get('body', {}).get('data', '')
            if data:
                body = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')

        return body


# Singleton instance
gmail_service = GmailService()
