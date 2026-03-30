import requests

class XtreamCodesAPI:
    def __init__(self, base_url, username, password):
        self.base_url = base_url
        self.username = username
        self.password = password

    def authenticate(self):
        """Authenticate and retrieve general account information to check connection."""
        auth_url = f"{self.base_url}/player_api.php?username={self.username}&password={self.password}"
        
        response = requests.get(auth_url)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("user_info", {}).get("auth") == 1:
                print("Authentication successful")
                return True
            else:
                raise Exception("Authentication failed: Invalid credentials")
        else:
            raise Exception(f"Failed to connect to API: {response.status_code} - {response.text}")

    def get_m3u_url(self, category):
        """Generate the M3U URL for live, movies, or series."""
        return f"{self.base_url}/get.php?username={self.username}&password={self.password}&type={category}&output=m3u8"

    def get_m3u_content(self, category):
        """Fetch the actual M3U content for live, movies, or series."""
        m3u_url = self.get_m3u_url(category)
        response = requests.get(m3u_url)
        
        if response.status_code == 200:
            return response.text
        else:
            raise Exception(f"Failed to retrieve {category} M3U: {response.status_code} - {response.text}")

# Usage example
def main():
    # Replace with your Xtream Codes API URL, username, and password
    base_url = "http://ismarter.xyz:2095"  # Example: "http://example.com"
    username = "truman322"
    password = "867977867866"
    
    api = XtreamCodesAPI(base_url, username, password)
    
    # Authenticate
    if api.authenticate():
        try:
            # Get M3U playlist URLs for live, movies, and series
            live_m3u = api.get_m3u_content("live")
            print("Live M3U Playlist:\n", live_m3u)
            
            movies_m3u = api.get_m3u_content("movie")
            print("Movies M3U Playlist:\n", movies_m3u)
            
            series_m3u = api.get_m3u_content("series")
            print("Series M3U Playlist:\n", series_m3u)
            
        except Exception as e:
            print("Error:", e)

if __name__ == "__main__":
    main()
