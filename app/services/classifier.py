"""Email classification for job applications - with keyword fallback."""

import logging
import os
import re
from typing import Optional

from dotenv import load_dotenv

load_dotenv(dotenv_path='config/.env')

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Job-related keywords for fallback classification
JOB_SENDERS = [
    'linkedin', 'indeed', 'glassdoor', 'ziprecruiter', 'monster', 'dice',
    'greenhouse.io', 'lever.co', 'workday', 'icims', 'jobvite', 'smartrecruiters',
    'breezy.hr', 'ashbyhq', 'jazz.co', 'applytojob', 'myworkdayjobs',
    'taleo', 'successfactors', 'ultipro', 'adp', 'bamboohr'
]

JOB_SENDER_PREFIXES = [
    'hr@', 'recruiting@', 'careers@', 'talent@', 'jobs@', 'hiring@',
    'recruitment@', 'noreply@', 'no-reply@', 'apply@', 'applications@'
]

JOB_SUBJECT_KEYWORDS = [
    'application', 'interview', 'position', 'role', 'opportunity', 'candidate',
    'job', 'offer', 'hiring', 'apply', 'applied', 'resume', 'cv',
    'thank you for applying', 'next steps', 'schedule', 'assessment',
    'phone screen', 'technical interview', 'onsite', 'final round'
]

JOB_BODY_KEYWORDS = [
    'thank you for your interest', 'received your application',
    'reviewed your application', 'reviewed your resume', 'your application for',
    'we regret to inform', 'moving forward with other candidates',
    'unfortunately', 'not moving forward', 'position has been filled',
    'pleased to invite', 'schedule an interview', 'next steps in our process',
    'would like to schedule', 'technical assessment', 'coding challenge',
    'offer of employment', 'pleased to offer', 'job offer',
    'excited to extend', 'compensation package', 'start date',
    'background check', 'reference check', 'onboarding'
]

# Status detection patterns
STATUS_PATTERNS = {
    'declined': [
        r'regret to inform', r'not moving forward', r'other candidates',
        r'unfortunately', r'position has been filled', r'decided not to',
        r'will not be moving', r'not selected', r'rejected'
    ],
    'interviewing': [
        r'schedule.{0,20}interview', r'interview.{0,10}scheduled',
        r'phone screen', r'technical interview', r'onsite interview',
        r'zoom meeting', r'video call', r'would like to meet',
        r'please join', r'calendar invite', r'final round'
    ],
    'screening': [
        r'phone screen', r'initial call', r'quick chat',
        r'recruiter call', r'introductory call', r'learn more about you'
    ],
    'offer': [
        r'offer of employment', r'pleased to offer', r'job offer',
        r'offer letter', r'compensation', r'start date',
        r'excited to extend', r'welcome to the team'
    ],
    'applied': [
        r'received your application', r'thank you for applying',
        r'application.{0,10}received', r'successfully submitted',
        r'application confirmation'
    ]
}


class KeywordClassifier:
    """Classify emails using keyword matching - no API required."""

    def is_job_related(self, sender: str, subject: str, snippet: str) -> bool:
        """Check if email is job-related based on keywords."""
        sender_lower = sender.lower()
        subject_lower = subject.lower()
        snippet_lower = snippet.lower()
        combined = f"{subject_lower} {snippet_lower}"

        # Check sender domain
        for job_sender in JOB_SENDERS:
            if job_sender in sender_lower:
                return True

        # Check sender prefix
        for prefix in JOB_SENDER_PREFIXES:
            if prefix in sender_lower:
                return True

        # Check subject keywords
        for keyword in JOB_SUBJECT_KEYWORDS:
            if keyword in subject_lower:
                return True

        # Check body keywords (need at least 2 matches for body)
        body_matches = sum(1 for kw in JOB_BODY_KEYWORDS if kw in combined)
        if body_matches >= 2:
            return True

        return False

    def detect_status(self, content: str) -> str:
        """Detect application status from email content."""
        content_lower = content.lower()

        # Check patterns in priority order
        for status, patterns in STATUS_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, content_lower):
                    return status

        return 'applied'  # Default status

    def extract_company(self, sender: str, subject: str, body: str) -> str:
        """Try to extract company name from email."""
        # Common patterns: "Company Name <email@company.com>"
        match = re.match(r'^([^<]+)\s*<', sender)
        if match:
            name = match.group(1).strip()
            # Filter out generic names
            if name.lower() not in ['hr', 'recruiting', 'careers', 'talent', 'jobs', 'noreply', 'no-reply']:
                return name

        # Try domain from email
        domain_match = re.search(r'@([^.]+)\.', sender)
        if domain_match:
            domain = domain_match.group(1)
            # Filter out email providers and ATS
            if domain.lower() not in ['gmail', 'yahoo', 'hotmail', 'outlook', 'greenhouse', 'lever', 'workday']:
                return domain.title()

        return "Unknown Company"

    def classify_email(self, sender: str, subject: str, body: str) -> Optional[dict]:
        """Classify email and extract details."""
        if not self.is_job_related(sender, subject, body[:500]):
            return None

        company = self.extract_company(sender, subject, body)
        status = self.detect_status(f"{subject} {body}")

        return {
            'company': company,
            'job_title': 'Unknown',  # Hard to extract without AI
            'location': 'Unknown',
            'status': status
        }


class EmailClassifier:
    """Classify emails using OpenAI with keyword fallback."""

    def __init__(self):
        self.client = None
        self.keyword_classifier = KeywordClassifier()

        if OPENAI_API_KEY:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=OPENAI_API_KEY)
            except ImportError:
                logger.warning("OpenAI package not installed, using keyword classifier")

    def is_configured(self) -> bool:
        """Check if any classifier is available (always true with keyword fallback)."""
        return True

    def is_openai_configured(self) -> bool:
        """Check if OpenAI is specifically configured."""
        return self.client is not None

    def is_job_related(self, sender: str = "", subject: str = "", snippet: str = "") -> bool:
        """
        Quick check if email is job-related.
        Uses OpenAI if available, falls back to keywords.
        """
        # Always try keyword classifier first - it's fast and free
        if self.keyword_classifier.is_job_related(sender, subject, snippet):
            return True

        # If keywords didn't match but OpenAI is available, try that
        if self.client:
            try:
                from openai import APIError, RateLimitError
                from tenacity import retry, stop_after_attempt, wait_exponential

                response = self.client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Determine if this email snippet is related to a job application "
                                "(e.g., application confirmation, rejection, interview invite, offer). "
                                "Return only 'Yes' or 'No'."
                            )
                        },
                        {"role": "user", "content": f"From: {sender}\nSubject: {subject}\n\n{snippet}"}
                    ],
                    max_tokens=10
                )
                result = response.choices[0].message.content.strip().lower()
                return result == 'yes'
            except Exception as e:
                logger.warning(f"OpenAI check failed, using keyword result: {e}")

        return False

    def classify_email(self, sender: str, subject: str, body: str) -> Optional[dict]:
        """
        Extract job application details from email.
        Uses OpenAI if available, falls back to keywords.
        """
        # Try OpenAI first if configured
        if self.client:
            try:
                from openai import APIError

                email_content = f"From: {sender}\nSubject: {subject}\n\n{body}"

                response = self.client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {
                            "role": "system",
                            "content": """You are an expert at analyzing job application emails.
Analyze this email and extract job application details.

If this is NOT a job application email, respond with exactly: NOT_JOB_EMAIL

If it IS job-related, respond in this exact format:
Company: [company name or "Unknown"]
Job Title: [job title or "Unknown"]
Location: [location or "Remote" or "Unknown"]
Status: [one of: Applied, Screening, Interviewing, Offer, Declined, Withdrawn]

Status definitions:
- Applied: Application received/confirmed
- Screening: Phone screen or initial review scheduled
- Interviewing: Interview scheduled or completed
- Offer: Job offer received
- Declined: Rejection received
- Withdrawn: You withdrew the application"""
                        },
                        {"role": "user", "content": email_content}
                    ],
                    max_tokens=200
                )

                result = response.choices[0].message.content.strip()

                if result == "NOT_JOB_EMAIL":
                    return None

                # Parse the response
                details = {}
                for line in result.splitlines():
                    line = line.strip()
                    if ':' in line:
                        key, value = line.split(':', 1)
                        key = key.strip().lower().replace(' ', '_')
                        details[key] = value.strip()

                # Normalize status
                status_map = {
                    'applied': 'applied',
                    'screening': 'screening',
                    'interviewing': 'interviewing',
                    'offer': 'offer',
                    'declined': 'declined',
                    'rejected': 'declined',
                    'withdrawn': 'withdrawn'
                }

                if 'status' in details:
                    raw_status = details['status'].lower()
                    for key, value in status_map.items():
                        if key in raw_status:
                            details['status'] = value
                            break

                if details.get('company'):
                    return details

            except Exception as e:
                logger.warning(f"OpenAI classification failed, using keyword fallback: {e}")

        # Fall back to keyword classifier
        return self.keyword_classifier.classify_email(sender, subject, body)


# Singleton instance
classifier = EmailClassifier()
