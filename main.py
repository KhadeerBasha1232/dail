import requests
import json
from datetime import datetime
import random
import time

# Your GitHub personal access token
token = 'your_personal_access_token'  # Replace with your GitHub token

# GitHub repository details
owner = 'KhadeerBasha1232'
repo = 'daily-repo'
branch = 'main'  # Replace with the branch you want to commit to

# GitHub API URLs
base_url = f'https://api.github.com/repos/{owner}/{repo}'
headers = {
    'Authorization': f'token {token}',
    'Accept': 'application/vnd.github.v3+json'
}

# Function to get the latest commit details from the branch
def get_latest_commit():
    url = f'{base_url}/branches/{branch}'
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()['commit']

# Function to create a new commit with an empty tree
def create_empty_commit(commit_sha):
    # Create a new empty commit object
    commit_message = f'Empty commit - {datetime.now().isoformat()}'
    data = {
        'message': commit_message,
        'tree': commit_sha,  # Use the latest commit SHA for the empty commit
        'parents': [commit_sha]
    }
    
    url = f'{base_url}/git/commits'
    response = requests.post(url, headers=headers, data=json.dumps(data))
    response.raise_for_status()
    
    return response.json()

# Function to update the reference of the branch (point it to the new commit)
def update_branch_reference(new_commit_sha):
    url = f'{base_url}/git/refs/heads/{branch}'
    data = {
        'sha': new_commit_sha
    }
    
    response = requests.patch(url, headers=headers, data=json.dumps(data))
    response.raise_for_status()
    print(f"Successfully pushed the empty commit to {branch} branch.")

# Main function to create and push the empty commit
def commit_and_push_empty():
    try:
        # Step 1: Get the latest commit SHA from the branch
        print("Getting the latest commit from the branch...")
        latest_commit = get_latest_commit()
        commit_sha = latest_commit['sha']

        # Step 2: Create the empty commit using the latest commit's SHA
        print("Creating the empty commit...")
        empty_commit = create_empty_commit(commit_sha)

        # Step 3: Update the branch reference to point to the new empty commit
        print("Updating the branch reference...")
        update_branch_reference(empty_commit['sha'])
        print("Empty commit successfully created and pushed.")

    except requests.exceptions.RequestException as e:
        print(f"Error during API request: {e}")
    except Exception as e:
        print(f"Error: {e}")

# Function to run the commit periodically with a random interval (between 1 and 3 hours)
def run_periodically():
    while True:
        # Generate a random time interval between 1 and 3 hours (in seconds)
        interval = random.randint(1, 3) * 60 * 60
        print(f"Next commit will be made after {interval / 3600} hours...")

        # Wait for the random interval before committing
        time.sleep(interval)

        # Make the commit
        commit_and_push_empty()

if __name__ == '__main__':
    run_periodically()
