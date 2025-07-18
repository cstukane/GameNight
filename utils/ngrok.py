import requests
import subprocess
import time
import atexit
import sys

# This will hold the ngrok process object
ngrok_process = None

def cleanup_ngrok():
    """Ensure the ngrok process is terminated when the script exits."""
    global ngrok_process
    if ngrok_process:
        print("Shutting down ngrok tunnel...")
        ngrok_process.terminate()
        ngrok_process.wait() # Wait for the process to actually terminate
        print("ngrok tunnel shut down.")

# Register the cleanup function to be called on script exit
atexit.register(cleanup_ngrok)

def get_public_url(port=3000, retries=5, delay=2):
    """
    Checks for an existing ngrok tunnel. If not found, it starts one.
    Returns the public URL or None if it fails.
    
    Args:
        port (int): The local port your web service is running on.
        retries (int): Number of times to check for the URL after starting ngrok.
        delay (int): Seconds to wait between retries.
    """
    global ngrok_process

    # 1. First, try to get the URL from an already running ngrok instance
    try:
        print("Checking for existing ngrok tunnel...")
        response = requests.get("http://127.0.0.1:4040/api/tunnels")
        response.raise_for_status()
        tunnels = response.json()["tunnels"]
        https_tunnel = next((t for t in tunnels if t["proto"] == "https" and t["config"]["addr"].endswith(str(port))), None)
        if https_tunnel:
            print(f"✅ Found existing ngrok tunnel: {https_tunnel['public_url']}")
            return https_tunnel['public_url']
        print("Found ngrok, but no tunnel for the correct port. Starting a new one.")
    except requests.exceptions.ConnectionError:
        print("ngrok not running. Attempting to start it...")
    except Exception as e:
        print(f"An error occurred while checking for ngrok: {e}")

    # 2. If no tunnel was found, start ngrok as a subprocess
    try:
        # Use Popen to run ngrok in the background and silence its output
        command = ["ngrok", "http", str(port)]
        ngrok_process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"Started ngrok process for port {port}. Waiting for it to initialize...")
        time.sleep(delay) # Give ngrok a moment to start up
    except FileNotFoundError:
        print("❌ CRITICAL: 'ngrok' command not found. Make sure ngrok is installed and in your system's PATH.")
        sys.exit(1) # Exit because we can't proceed
    except Exception as e:
        print(f"❌ Failed to start ngrok: {e}")
        return None

    # 3. Poll the API to get the new tunnel's URL
    for i in range(retries):
        print(f"Attempting to fetch URL (try {i+1}/{retries})...")
        try:
            response = requests.get("http://127.0.0.1:4040/api/tunnels")
            response.raise_for_status()
            tunnels = response.json()["tunnels"]
            https_tunnel = next((t for t in tunnels if t["proto"] == "https"), None)
            if https_tunnel:
                public_url = https_tunnel['public_url']
                print(f"✅ ngrok tunnel is live at: {public_url}")
                return public_url
        except requests.exceptions.ConnectionError:
            # This is expected for a moment while ngrok starts
            pass
        except Exception as e:
            print(f"An error occurred while polling ngrok: {e}")
        
        time.sleep(delay)

    # 4. If we finish the loop without a URL, give up
    print("❌ Failed to get public URL from ngrok after multiple attempts.")
    cleanup_ngrok() # Clean up the failed process
    return None