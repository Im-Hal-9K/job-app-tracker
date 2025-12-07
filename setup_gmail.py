#!/usr/bin/env python3
"""
Gmail OAuth Setup Script
========================
Run this script to complete Gmail OAuth setup before using the web app.

Usage: python setup_gmail.py
"""

import os
import sys
from pathlib import Path

# Add the app directory to path
sys.path.insert(0, str(Path(__file__).parent))

from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
TOKEN_PATH = 'config/token.json'
CREDS_PATH = 'config/gmail_credentials.json'


def main():
    print("""
╔═══════════════════════════════════════════╗
║         Gmail OAuth Setup                 ║
╚═══════════════════════════════════════════╝
""")

    # Check for credentials file
    if not os.path.exists(CREDS_PATH):
        print(f"❌ Error: {CREDS_PATH} not found!")
        print()
        print("Please download your OAuth credentials from Google Cloud Console")
        print("and save them as 'config/gmail_credentials.json'")
        print()
        print("Steps:")
        print("1. Go to https://console.cloud.google.com")
        print("2. APIs & Services → Credentials")
        print("3. Download your OAuth client JSON")
        print("4. Save as config/gmail_credentials.json")
        return 1

    # Check for existing token
    if os.path.exists(TOKEN_PATH):
        print("Found existing token. Testing...")
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
            if creds.valid:
                print("✓ Token is valid! Gmail is already configured.")
                return 0
            elif creds.expired and creds.refresh_token:
                print("Token expired, refreshing...")
                creds.refresh(Request())
                with open(TOKEN_PATH, 'w') as f:
                    f.write(creds.to_json())
                print("✓ Token refreshed! Gmail is configured.")
                return 0
        except Exception as e:
            print(f"Token invalid: {e}")
            print("Will run OAuth flow again...")
            os.remove(TOKEN_PATH)

    # Run OAuth flow
    print()
    print("Starting OAuth flow...")
    print("A browser window will open. Please sign in and grant access.")
    print()
    print("⚠️  Make sure you're signing in with an account that's")
    print("   added as a Test User in your Google Cloud Console!")
    print()

    try:
        flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
        creds = flow.run_local_server(
            port=8085,  # Use a fixed port
            prompt='consent',
            success_message='Gmail authorized! You can close this window and return to the terminal.'
        )

        # Save token
        Path('config').mkdir(exist_ok=True)
        with open(TOKEN_PATH, 'w') as f:
            f.write(creds.to_json())

        print()
        print("✓ Gmail OAuth complete!")
        print(f"✓ Token saved to {TOKEN_PATH}")
        print()
        print("You can now use Email Sync in Job Tracker.")
        return 0

    except Exception as e:
        print()
        print(f"❌ OAuth failed: {e}")
        print()
        print("Troubleshooting:")
        print("- Make sure your Gmail is added as a Test User")
        print("- Check that port 8085 isn't blocked by firewall")
        print("- Try running as administrator if on Windows")
        return 1


if __name__ == "__main__":
    sys.exit(main())
