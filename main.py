import threading
import requests
import json
from datetime import datetime
import random
import time

# Define user details as objects
users = [
    {
        "token": "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",  # Replace with first GitHub token
        "owner": "KhadeerBasha1232", 
        "repo": "daily-repo",
        "branch": "main",
    },
    {
        "token": "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",  # Replace with second GitHub token
        "owner": "MuktharBashaShaik",
        "repo": "daily-repo",
        "branch": "main",
    },
]

# Function to get headers for authentication
def get_headers(token):
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

# Function to get the latest commit details from the branch
def get_latest_commit(user):
    url = f"https://api.github.com/repos/{user['owner']}/{user['repo']}/branches/{user['branch']}"
    response = requests.get(url, headers=get_headers(user["token"]))
    response.raise_for_status()
    return response.json()["commit"]

# Function to get the tree SHA from the latest commit
def get_tree_sha(user, commit_sha):
    url = f"https://api.github.com/repos/{user['owner']}/{user['repo']}/git/commits/{commit_sha}"
    response = requests.get(url, headers=get_headers(user["token"]))
    response.raise_for_status()
    return response.json()["tree"]["sha"]

# Function to create a new commit with an empty tree
def create_empty_commit(user, tree_sha, commit_sha):
    commit_message = f"Empty commit - {datetime.now().isoformat()}"
    data = {
        "message": commit_message,
        "tree": tree_sha,
        "parents": [commit_sha],
    }
    url = f"https://api.github.com/repos/{user['owner']}/{user['repo']}/git/commits"
    response = requests.post(url, headers=get_headers(user["token"]), data=json.dumps(data))
    response.raise_for_status()
    return response.json()

# Function to update the reference of the branch (point it to the new commit)
def update_branch_reference(user, new_commit_sha):
    url = f"https://api.github.com/repos/{user['owner']}/{user['repo']}/git/refs/heads/{user['branch']}"
    data = {"sha": new_commit_sha}
    response = requests.patch(url, headers=get_headers(user["token"]), data=json.dumps(data))
    response.raise_for_status()
    print(f"Successfully pushed the empty commit to {user['branch']} in {user['repo']}.")

# Function to commit and push an empty commit using a user object
def commit_and_push_empty(user):
    try:
        print(f"Fetching latest commit for {user['owner']}...")
        latest_commit = get_latest_commit(user)
        commit_sha = latest_commit["sha"]

        tree_sha = get_tree_sha(user, commit_sha)

        print(f"Creating empty commit for {user['owner']}...")
        empty_commit = create_empty_commit(user, tree_sha, commit_sha)

        print(f"Updating branch reference for {user['owner']}...")
        update_branch_reference(user, empty_commit["sha"])
        print(f"Empty commit pushed successfully for {user['owner']}.")

    except requests.exceptions.RequestException as e:
        print(f"Error during API request for {user['owner']}: {e}")
    except Exception as e:
        print(f"Error: {e}")

# Function to run the commit periodically for both accounts
def run_periodically():
    while True:
        print("Starting commits for both users...")

        # Run commits for both users
        for user in users:
            commit_and_push_empty(user)

        # Generate a random time interval between 1 minute (60 seconds) and 4 hours (14400 seconds)
        interval = random.randint(1, 240) * 60
        print(f"Next commits in {interval / 60} minutes...")
        time.sleep(interval)


urls = [
    "https://quaint-albertine-clustercompany-99d4f8b7.koyeb.app/",
    "https://kb-help.onrender.com/"
]

def keep_flask_alive():
    while True:
        for url in urls:
            try:
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"[{current_time}] Pinging {url}...")

                response = requests.get(url, timeout=10)
                print(f"[{current_time}] Pinged {url}: {response.status_code}, Text: {response.text}")
            except requests.exceptions.RequestException as e:
                print(f"[{current_time}] Error pinging {url}: {e}")

        time.sleep(300)  # Ping every 5 minutes



if __name__ == "__main__":
    commit_thread = threading.Thread(target=run_periodically)  # Remove daemon=True
    commit_thread.start()

    flask_thread = threading.Thread(target=keep_flask_alive)  # Remove daemon=True
    flask_thread.start()

    # Prevent the main thread from exiting
    commit_thread.join()
    flask_thread.join()
