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

    # Fetch most recent email with "The Beach Buzz" in subject
    print("Fetching most recent email with 'The Beach Buzz' in subject...")

    query = 'subject:"The Beach Buzz"'
    results = (
        service.users().messages().list(userId="me", q=query, maxResults=1).execute()
    )

    messages = results.get("messages", [])
    if not messages:
        print("No emails found with 'The Beach Buzz' in subject.")
        return

    # Get the first message (most recent)
    msg_id = messages[0]["id"]
    message = service.users().messages().get(userId="me", id=msg_id).execute()

    # Display email details
    headers = {
        header["name"]: header["value"] for header in message["payload"]["headers"]
    }

    print("\n===== Latest 'The Beach Buzz' Email =====")
    print(f"From: {headers.get('From', 'Unknown')}")
    print(f"Subject: {headers.get('Subject', 'No Subject')}")
    print(f"Date: {headers.get('Date', 'Unknown')}")

    # Extract body content (this is simplified, might need more parsing based on MIME structure)
    if "parts" in message["payload"]:
        for part in message["payload"]["parts"]:
            if part["mimeType"] == "text/plain":
                body = part["body"].get("data", "")
                if body:
                    import base64

                    decoded_body = base64.urlsafe_b64decode(body).decode("utf-8")
                    print("\nMessage Body:")
                    print(decoded_body)
    elif "body" in message["payload"] and "data" in message["payload"]["body"]:
        body = message["payload"]["body"]["data"]
        import base64

        decoded_body = base64.urlsafe_b64decode(body).decode("utf-8")
        print("\nMessage Body:")
        print(decoded_body)


if __name__ == "__main__":
    main()
