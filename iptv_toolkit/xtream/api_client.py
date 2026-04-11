"""Module for interacting with Xtream Codes API."""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from time import sleep
from iptv_toolkit.core import config
from iptv_toolkit.xtream.catalog_manager import CatalogManager
from iptv_toolkit.xtream.cache_manager import CacheManager, cache_response

class XtreamCodesAPI:
    def __init__(self, base_url, username, password, timeout=None):
        """Initialize the API client."""
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.timeout = timeout or config.API_CONFIG['timeout']
        self.catalog_manager = CatalogManager()
        self.cache_manager = CacheManager()
        
        # Setup session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=config.API_CONFIG['retry']['total'],
            backoff_factor=config.API_CONFIG['retry']['backoff_factor'],
            status_forcelist=config.API_CONFIG['retry']['status_forcelist'],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Cache for categories
        self.categories = {
            'live_streams': {},
            'vod': {},
            'series': {}
        }
        
        # Cache for category info including tags
        self.category_info = {
            'live_streams': {},
            'vod': {},
            'series': {}
        }

    @cache_response('auth')
    def authenticate(self):
        """Authenticate and retrieve general account information.

        Returns ``None`` and prints a diagnostic on failure. Different panels
        signal bad credentials differently — some return 200 with
        ``{"user_info": {"auth": 0}}``, others return 404, others return an
        HTML "Access Denied" page. We try to distinguish these cases so the
        user knows whether to renew, change URL, or check network.
        """
        print("\nAttempting authentication...")
        auth_url = f"{self.base_url}/player_api.php"
        params = {"username": self.username, "password": self.password}

        try:
            response = self.session.get(auth_url, params=params, timeout=self.timeout)
        except requests.exceptions.SSLError as e:
            print(f"Authentication error: TLS handshake failed — try http:// instead of https://, "
                  f"or check the panel's real port. ({e})")
            return None
        except requests.exceptions.ConnectTimeout:
            print(f"Authentication error: connection to {self.base_url} timed out after "
                  f"{self.timeout}s. Panel may be down or port is blocked.")
            return None
        except requests.exceptions.ConnectionError as e:
            print(f"Authentication error: cannot reach {self.base_url}. "
                  f"Check the URL and network. ({e})")
            return None
        except Exception as e:
            print(f"Authentication error: unexpected failure — {type(e).__name__}: {e}")
            return None

        if response.status_code == 200:
            try:
                data = response.json()
            except ValueError:
                print(f"Authentication error: panel returned 200 but non-JSON body "
                      f"(first 120 chars): {response.text[:120]!r}. "
                      f"URL is probably not an Xtream panel endpoint.")
                return None
            user_info = (data or {}).get('user_info', {}) if isinstance(data, dict) else {}
            if user_info.get('auth') == 0:
                print(f"Authentication error: panel rejected credentials (auth=0). "
                      f"Username/password wrong.")
                return None
            status = user_info.get('status')
            if status and status.lower() not in ('active', 'trial'):
                exp = user_info.get('exp_date', 'unknown')
                print(f"Authentication error: subscription status is {status!r} "
                      f"(expires: {exp}). Renew with your provider.")
                return None
            print("Authentication successful")
            return data

        if response.status_code == 404:
            print(f"Authentication error: panel returned 404 for player_api.php with "
                  f"credentials. On many panels this means the subscription is expired "
                  f"or the credentials are invalid. Check with your provider.")
            return None
        if response.status_code in (401, 403):
            print(f"Authentication error: HTTP {response.status_code} — credentials "
                  f"rejected or IP blocked.")
            return None
        if 500 <= response.status_code < 600:
            print(f"Authentication error: panel returned HTTP {response.status_code}. "
                  f"Server error on their side; try again later.")
            return None
        print(f"Authentication error: unexpected HTTP {response.status_code}.")
        return None

    @cache_response('categories')
    def get_categories(self, stream_type):
        """Get categories for the specified stream type."""
        if self.categories[stream_type]:
            return self.categories[stream_type]
            
        print(f"Fetching {stream_type} categories...")
        url = f"{self.base_url}/player_api.php"
        
        actions = {
            "live_streams": "get_live_categories",
            "vod": "get_vod_categories",
            "series": "get_series_categories"
        }
        
        params = {
            "username": self.username,
            "password": self.password,
            "action": actions.get(stream_type)
        }
        
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            if response.status_code == 200:
                categories = response.json()
                if categories:
                    # Create mapping of category_id to category_name
                    self.categories[stream_type] = {
                        str(cat['category_id']): cat['category_name']
                        for cat in categories
                    }
                    
                    # Process and cache category info with tags
                    for cat in categories:
                        cat_id = str(cat['category_id'])
                        cat_info = {
                            'name': cat['category_name'],
                            'tags': self.catalog_manager._extract_tags_from_category(cat['category_name'])
                        }
                        self.category_info[stream_type][cat_id] = cat_info
                    
                    print(f"Got {len(categories)} categories for {stream_type}")
                    return self.categories[stream_type], categories
            return {}, []
        except Exception as e:
            print(f"Error fetching categories: {str(e)}")
            return {}, []

    def get_category_name(self, stream_type, category_id):
        """Get category name for the given category ID."""
        if not self.categories[stream_type]:
            self.get_categories(stream_type)
        return self.categories[stream_type].get(str(category_id), "Uncategorized")

    def get_category_info(self, stream_type, category_id):
        """Get category information including tags."""
        if not self.category_info[stream_type]:
            self.get_categories(stream_type)
        return self.category_info[stream_type].get(str(category_id), {
            'name': 'Uncategorized',
            'tags': []
        })

    @cache_response('streams')
    def get_stream_list(self, stream_type):
        """Get list of streams for the specified type."""
        print(f"\nFetching {stream_type} list...")
        url = f"{self.base_url}/player_api.php"
        
        actions = {
            "live_streams": "get_live_streams",
            "vod": "get_vod_streams",
            "series": "get_series"
        }
        
        params = {
            "username": self.username,
            "password": self.password,
            "action": actions.get(stream_type, f"get_{stream_type}")
        }
        
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            if response.status_code == 200:
                streams = response.json()
                if streams:
                    print(f"Successfully got {len(streams)} {stream_type}")
                    # Fetch categories if not already cached
                    if not self.categories[stream_type]:
                        category_map, categories = self.get_categories(stream_type)
                        # Compare with previous catalog
                        self.catalog_manager.compare_catalogs(stream_type, streams, categories)
                    else:
                        category_map = self.categories[stream_type]
                    # Add category_name to each stream
                    for stream in streams:
                        category_id = str(stream.get('category_id', ''))
                        stream['category_name'] = category_map.get(category_id, "Uncategorized")
                    return streams
                return None
            return None
        except Exception as e:
            print(f"Error fetching {stream_type} list: {str(e)}")
            return None

    @cache_response('movie')
    def get_movie_info(self, movie_id, retries=None):
        """Get detailed information about a movie."""
        url = f"{self.base_url}/player_api.php"
        params = {
            "username": self.username,
            "password": self.password,
            "action": "get_vod_info",
            "vod_id": movie_id
        }
        
        retry_total = retries or config.API_CONFIG['retry']['total']
        for attempt in range(retry_total):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, dict):
                        return data
                    return None
                elif response.status_code != 429:  # If not rate limited, don't retry
                    break
                sleep(2 ** attempt)  # Exponential backoff
            except Exception as e:
                if attempt < retries - 1:
                    sleep(2 ** attempt)
                continue
        return None

    @cache_response('series')
    def get_series_info(self, series_id, pbar=None, retries=None):
        """Get detailed information about a series including seasons."""
        url = f"{self.base_url}/player_api.php"
        params = {
            "username": self.username,
            "password": self.password,
            "action": "get_series_info",
            "series_id": series_id
        }
        
        retry_total = retries or config.API_CONFIG['retry']['total']
        for attempt in range(retry_total):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
                if response.status_code == 200:
                    data = response.json()
                    return data
                elif response.status_code != 429:  # If not rate limited, don't retry
                    break
                sleep(2 ** attempt)  # Exponential backoff
            except Exception as e:
                if attempt < retries - 1:
                    sleep(2 ** attempt)
                continue
        return None

    @cache_response('episodes')
    def get_series_episodes(self, series_id, season_num, pbar=None, retries=None):
        """Get episodes for a specific season of a series."""
        url = f"{self.base_url}/player_api.php"
        params = {
            "username": self.username,
            "password": self.password,
            "action": "get_series_episodes",
            "series_id": series_id,
            "season": season_num
        }
        
        retry_total = retries or config.API_CONFIG['retry']['total']
        for attempt in range(retry_total):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list):
                        return data
                    elif isinstance(data, dict):
                        if "episodes" in data:
                            return data["episodes"]
                    return None
                elif response.status_code != 429:  # If not rate limited, don't retry
                    break
                sleep(2 ** attempt)  # Exponential backoff
            except Exception as e:
                if attempt < retries - 1:
                    sleep(2 ** attempt)
                continue
        return None
