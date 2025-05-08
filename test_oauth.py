import asyncio
import webbrowser
import requests
import sys
import json
from uuid import UUID
import re

# This script helps test the OAuth flow without a frontend
# Usage: python test_oauth.py <project_id> <jwt_token>


def check_channel_status(channel_id, jwt_token):
    base_url = "http://localhost:8000/api/v1"
    headers = {"Authorization": f"Bearer {jwt_token}"}

    try:
        # Check channel status
        status_url = f"{base_url}/channels/{channel_id}"
        response = requests.get(status_url, headers=headers)

        if response.status_code == 200:
            data = response.json()
            print("\nChannel status:")
            print(f"  ID: {data['id']}")
            print(f"  Connected: {data['is_connected']}")
            print(f"  Auth data present: {'Yes' if data['auth_data'] else 'No'}")
            return data
        else:
            print(f"Error checking channel status: {response.text}")
            return None
    except Exception as e:
        print(f"Error: {str(e)}")
        return None


def main():
    # if len(sys.argv) < 3:
    #     sys.exit(1)

    # project_id = sys.argv[1]
    # jwt_token = sys.argv[2]
    project_id = "d349900a-c26a-40e2-89d6-f7da8273ec8d"  # Replace with your project ID
    jwt_token = "eyJhbGciOiJSUzI1NiIsImNhdCI6ImNsX0I3ZDRQRDIyMkFBQSIsImtpZCI6Imluc18yd04zOVRadWFyVnRSNWQ3WVpLZUNaTTFjdmkiLCJ0eXAiOiJKV1QifQ.eyJhcHBfbWV0YWRhdGEiOnt9LCJhdWQiOiJmYXN0YXBpIiwiYXpwIjoiaHR0cHM6Ly9kaXJlY3QtbW9sZS0xNi5hY2NvdW50cy5kZXYiLCJlbWFpbCI6ImNhbHNvbjEyM0BnbWFpbC5jb20iLCJleHAiOjE3Nzc5MjE0NzIsImlhdCI6MTc0NjM4NTQ3MiwiaXNzIjoiaHR0cHM6Ly9kaXJlY3QtbW9sZS0xNi5jbGVyay5hY2NvdW50cy5kZXYiLCJqdGkiOiJhNTUzNDJhNWZkZTMwNTYyY2FkYiIsIm5iZiI6MTc0NjM4NTQ2Nywicm9sZSI6ImF1dGhlbnRpY2F0ZWQiLCJzdWIiOiJ1c2VyXzJ3ZHhQRXU3Q0tWQmFQUlJSa2FIMGlJbHB4byIsInVzZXJfaWQiOiJ1c2VyXzJ3ZHhQRXU3Q0tWQmFQUlJSa2FIMGlJbHB4byIsInVzZXJfbWV0YWRhdGEiOnt9fQ.VKbwj5lREAHvQyF3kx9EnFPxindugCdmdg_DQiSx_iOP0ipGEpNoqCuLpbsFazzbJ16EdxQegZ82ZOsyaewhIeGgbcN-lJkyT-1jpBOvZYwRqmIceZFnvuNsHKsnRxMtmvG48WB1-FIPjaOwvJCWjJSUBl8DwPwG2vLYn5AuJscyeQzmO2kl1EQV1EtuwjHcq4uLIdwwtEWwTOhK8duc1gigpcx1jOt1hqYgUFL6eMwN41J_Dyn3CuCq-FgbauzT1yh3L95M_9mhrxDA8LpfuvxMYb5DiVRLCAiSqneS5s7InCmNL3pnjrW-ZDzdx1PM4xyfCLs5_MJyKBdBagLxxA"
    print(f"Usage: python test_oauth.py {project_id} | {jwt_token}")

    # API base URL
    base_url = "http://localhost:8000/api/v1"

    # Headers for authorization
    headers = {"Authorization": f"Bearer {jwt_token}"}

    try:
        # Initialize OAuth flow
        init_url = f"{base_url}/oauth/gmail/initialize/{project_id}"
        print(f"Calling: {init_url}")

        response = requests.post(init_url, headers=headers)

        if response.status_code != 200:
            print(f"Error initializing OAuth: {response.text}")
            sys.exit(1)

        # Get the authorization URL
        auth_url = response.json()["auth_url"]
        print(f"\nAuthorization URL: {auth_url}\n")

        # Open the browser for the user to complete OAuth
        webbrowser.open(auth_url)

        print("Browser opened for OAuth authorization.")
        print("After you complete the OAuth flow in your browser, the callback will be processed automatically.")
        print("You can check your Supabase database to verify the channel was updated with auth data.")

        input("\nPress Enter after you've completed the OAuth authorization in your browser...")

        # Extract channel_id from the auth_url
        channel_id_match = re.search(r"state=([^&]+)", auth_url)
        if channel_id_match:
            channel_id = channel_id_match.group(1)
            print(f"Channel ID: {channel_id}")

            # Check channel status
            channel_data = check_channel_status(channel_id, jwt_token)

            if channel_data and channel_data["is_connected"]:
                print("\n✅ Gmail channel connected successfully!")
            else:
                print("\n❌ Gmail channel connection failed or not completed.")
        else:
            print("Could not extract channel ID from authorization URL")

    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
