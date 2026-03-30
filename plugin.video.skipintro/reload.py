import requests
import json

# Define the Kodi JSON-RPC URL
url = "http://localhost:1984/jsonrpc"
headers = {"Content-Type": "application/json"}

# Function to stop the current video
def stop_video():
    payload = {
        "jsonrpc": "2.0",
        "method": "Player.Stop",
        "params": {"playerid": 1},
        "id": 1
    }
    response = requests.post(url, headers=headers, json=payload)
    return response.json()

# Function to disable an add-on
def disable_addon(addon_id):
    payload = {
        "jsonrpc": "2.0",
        "method": "Addons.SetAddonEnabled",
        "params": {"addonid": addon_id, "enabled": False},
        "id": 2
    }
    response = requests.post(url, headers=headers, json=payload)
    return response.json()

# Function to enable an add-on
def enable_addon(addon_id):
    payload = {
        "jsonrpc": "2.0",
        "method": "Addons.SetAddonEnabled",
        "params": {"addonid": addon_id, "enabled": True},
        "id": 3
    }
    response = requests.post(url, headers=headers, json=payload)
    return response.json()

# Example usage
stop_video_response = stop_video()
print("Stop Video Response:", stop_video_response)

addon_id = "plugin.video.skipintro"  # Replace with your add-on ID
disable_addon_response = disable_addon(addon_id)
print("Disable Add-on Response:", disable_addon_response)

enable_addon_response = enable_addon(addon_id)
print("Enable Add-on Response:", enable_addon_response)
