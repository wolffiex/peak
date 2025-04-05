from __future__ import print_function
import os.path
import os
import base64
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from .cache import cached

# Enable non-HTTPS redirect URIs for development
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

# Scope for read-only Gmail access
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def authenticate():
    """Authenticate with Gmail API and return the service object."""
    creds = None
    # Load existing token
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    # If no valid token, start auth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Use a specific redirect URI that must match your OAuth consent screen configuration
            REDIRECT_URI = "http://localhost:8080/"

            flow = InstalledAppFlow.from_client_secrets_file(
                "peak_client_secret.json", SCOPES, redirect_uri=REDIRECT_URI
            )

            # Generate auth URL
            auth_url, _ = flow.authorization_url(
                access_type="offline", prompt="consent", include_granted_scopes="true"
            )

            print(f"Please go to this URL and authorize the app:\n{auth_url}\n")
            print(
                f"After authorization, you'll be redirected to a URL starting with: {REDIRECT_URI}"
            )
            print("Copy the entire redirect URL and paste it here:")
            redirect_url = input("Enter the full redirect URL: ")

            # Extract code from the redirect URL
            token = flow.fetch_token(authorization_response=redirect_url)

            # Process scope - could be string or list
            scope = token.get("scope", "")
            if isinstance(scope, str):
                scopes = scope.split(" ")
            else:
                scopes = scope

            # Convert the token to Credentials object
            creds = Credentials(
                token=token.get("access_token"),
                refresh_token=token.get("refresh_token"),
                token_uri=flow.client_config["token_uri"],
                client_id=flow.client_config["client_id"],
                client_secret=flow.client_config["client_secret"],
                scopes=scopes,
            )

        # Save the credentials for the next run
        with open("token.json", "w") as token_file:
            token_file.write(creds.to_json())

    # Build and return Gmail API client
    return build("gmail", "v1", credentials=creds)


@cached(300)  # Cache for 5 minutes
def get_beach_buzz():
    """Fetch the most recent 'The Beach Buzz' email and return its details."""
    service = authenticate()
    print("Fetching most recent email with 'The Beach Buzz' in subject...")

    query = 'subject:"The Beach Buzz"'
    results = (
        service.users().messages().list(userId="me", q=query, maxResults=1).execute()
    )

    messages = results.get("messages", [])
    if not messages:
        print("No emails found with 'The Beach Buzz' in subject.")
        return None

    # Get the first message (most recent)
    msg_id = messages[0]["id"]
    message = service.users().messages().get(userId="me", id=msg_id).execute()

    # Extract body content
    if "parts" in message["payload"]:
        for part in message["payload"]["parts"]:
            if part["mimeType"] == "text/plain":
                body = part["body"].get("data", "")
                if body:
                    return base64.urlsafe_b64decode(body).decode("utf-8")
    elif "body" in message["payload"] and "data" in message["payload"]["body"]:
        body = message["payload"]["body"]["data"]
        return base64.urlsafe_b64decode(body).decode("utf-8")


def main():
    """Main function that authenticates and fetches The Beach Buzz email."""
    # Get and display Beach Buzz email
    buzz = get_beach_buzz()
    print(buzz)


if __name__ == "__main__":
    main()
