from __future__ import print_function
import os.path
import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Enable non-HTTPS redirect URIs for development
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

# Scope for read-only Gmail access
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def main():
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

    # Build Gmail API client
    service = build("gmail", "v1", credentials=creds)

    # List Gmail labels
    results = service.users().labels().list(userId="me").execute()
    labels = results.get("labels", [])

    print("Labels:")
    for label in labels:
        print(f"- {label['name']}")


if __name__ == "__main__":
    main()
