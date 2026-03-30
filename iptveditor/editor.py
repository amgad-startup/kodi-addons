import logging
import os
from typing import Dict, List
from collections import defaultdict

from config import STATE_FILE, CATEGORIES_FILE, SHOWS_FILE
from utils import load_json_file, save_json_file, detect_language, arabic_to_english, should_process_title
from api import TMDBApi, IPTVEditorApi
from database import cache_manager

class IPTVEditor:
    def __init__(self, batch_size: int = 10):
        self.logger = logging.getLogger(__name__)
        self.batch_size = batch_size
        
        # Initialize API clients
        self.tmdb_api = TMDBApi()
        self.iptv_api = IPTVEditorApi()
        
        # Initialize data
        self.categories = []
        self.shows = []
        self.shows_by_category = defaultdict(list)
        self.not_found_shows = []  # Track shows not found in TMDB
        
        # Load initial data
        self.load_data()
        self.load_state()
        self.load_not_found_shows()
        
        # Initialize not_found_shows.json if it doesn't exist
        self.save_not_found_shows()

    def load_state(self) -> None:
        """Load the processing state from file"""
        try:
            state = load_json_file(STATE_FILE)
            self.state = state
            self.logger.debug(f"Loaded state: {state}")
        except FileNotFoundError:
            self.state = {
                'current_category_id': None,
                'last_processed_index': 0
            }
            self.logger.debug("Starting new processing session")

    def save_state(self) -> None:
        """Save the current processing state to file"""
        save_json_file(STATE_FILE, self.state)
        self.logger.debug(f"Saved state: {self.state}")

    def load_not_found_shows(self) -> None:
        """Load existing not found shows from file"""
        try:
            if os.path.exists('not_found_shows.json'):
                data = load_json_file('not_found_shows.json', raise_on_error=False)
                if data and 'shows' in data:
                    self.not_found_shows = data['shows']
                    self.logger.debug(f"Loaded {len(self.not_found_shows)} existing not found shows")
                else:
                    self.not_found_shows = []
            else:
                self.not_found_shows = []
                self.logger.debug("Starting with empty not found shows list")
        except Exception as e:
            self.logger.error(f"Error loading not found shows: {str(e)}")
            self.not_found_shows = []

    def save_not_found_shows(self) -> None:
        """Save shows that weren't found in TMDB to a file"""
        not_found_data = {
            'total': len(self.not_found_shows),
            'shows': self.not_found_shows
        }
        save_json_file('not_found_shows.json', not_found_data)
        if self.not_found_shows:
            self.logger.info(f"Saved {len(self.not_found_shows)} not found shows to not_found_shows.json")

    def save_api_data_to_files(self, categories: List[Dict], shows: List[Dict]) -> None:
        """Save API data to JSON files"""
        # Save categories
        categories_data = {'items': categories}
        save_json_file(CATEGORIES_FILE, categories_data)
        self.logger.info(f"Saved {len(categories)} categories to {CATEGORIES_FILE}")

        # Save shows
        shows_data = {'items': shows}
        save_json_file(SHOWS_FILE, shows_data)
        self.logger.info(f"Saved {len(shows)} shows to {SHOWS_FILE}")

    def load_data(self) -> None:
        """Load categories and shows data"""
        try:
            # Try to load from local files first
            try:
                self.logger.debug("Attempting to load from local files")
                self.categories = load_json_file(CATEGORIES_FILE)['items']
                self.shows = load_json_file(SHOWS_FILE)['items']
                self.logger.info("Successfully loaded data from local files")
            except FileNotFoundError:
                # If files don't exist, fetch from API and save
                self.logger.info("Local files not found, fetching from API")
                self.categories = self.iptv_api.get_categories()
                self.shows = self.iptv_api.get_shows()
                self.save_api_data_to_files(self.categories, self.shows)
            
            # Filter shows to only include those with Arabic titles
            self.shows = [show for show in self.shows if should_process_title(show['name'])]
            self.logger.info(f"Filtered to {len(self.shows)} shows with Arabic titles")
            
            # Group shows by category
            for show in self.shows:
                self.shows_by_category[show['category']].append(show)
            
            self.logger.debug(f"Loaded {len(self.categories)} categories and {len(self.shows)} shows")
        except Exception as e:
            self.logger.error(f"Failed to load data: {str(e)}")
            raise

    def process_show(self, show: Dict) -> bool:
        """Process a single show. Returns True if successful, False otherwise."""
        show_id = show['id']
        show_name = show['name']
        category_id = show['category']
        
        self.logger.debug(f"Processing show: {show_name} (ID: {show_id})")
        
        try:
            # Skip non-Arabic titles
            if not should_process_title(show_name):
                self.logger.debug(f"Skipping non-Arabic title: {show_name}")
                return False
                
            # Get show info from TMDB
            show_info = self.tmdb_api.search_show(show_name)
            
            # If not found, try transliteration for Arabic shows
            transliterated_name = None
            if not show_info and detect_language(show_name) == 'ar':
                transliterated_name = arabic_to_english(show_name)
                show_info = self.tmdb_api.search_show(transliterated_name)
            
            if not show_info:
                self.logger.debug(f"Could not find show '{show_name}' on TMDB")
                # Add to not found shows list with relevant info
                category_name = next((c['name'] for c in self.categories if c['id'] == category_id), "Unknown Category")
                not_found_info = {
                    'id': show_id,
                    'name': show_name,  # Original name will be preserved as-is
                    'category_id': category_id,
                    'category_name': category_name
                }
                # Add transliterated name if it was attempted
                if transliterated_name:
                    not_found_info['transliterated_name'] = transliterated_name
                
                # Check if show is already in not_found_shows
                if not any(s['id'] == show_id for s in self.not_found_shows):
                    self.not_found_shows.append(not_found_info)
                    self.logger.debug(f"Added show {show_name} to not found list")
                    # Save after each new not found show
                    self.save_not_found_shows()
                
                self.logger.info("✗")
                return False
            
            show_tmdb_id = show_info['id']
            self.logger.debug(f"TMDB match - ID: {show_tmdb_id}, Name: {show_info.get('name')}")
            
            # Get detailed show information
            show_details = self.tmdb_api.get_show_details(show_tmdb_id)
            self.logger.debug(f"Retrieved show details from TMDB")
            
            # Get show episodes
            episodes = self.iptv_api.get_episodes(show_id)
            self.logger.debug(f"Retrieved {len(episodes) if episodes else 0} episodes")
            
            # Update the show
            result = self.iptv_api.update_show(show_id, show_tmdb_id, category_id)
            if result:
                self.logger.info("✓")
            else:
                self.logger.info("✗")
            return result
            
        except Exception as e:
            self.logger.debug(f"Error processing show '{show_name}': {str(e)}")
            # Add to not found shows list with error info
            category_name = next((c['name'] for c in self.categories if c['id'] == category_id), "Unknown Category")
            not_found_info = {
                'id': show_id,
                'name': show_name,
                'category_id': category_id,
                'category_name': category_name,
                'error': str(e)
            }
            
            # Check if show is already in not_found_shows
            if not any(s['id'] == show_id for s in self.not_found_shows):
                self.not_found_shows.append(not_found_info)
                self.logger.debug(f"Added show {show_name} to not found list (error: {str(e)})")
                # Save after each new not found show
                self.save_not_found_shows()
            
            self.logger.info("✗")
            return False

    def process_shows(self) -> None:
        """Process shows by category in batches"""
        remaining_batch = self.batch_size
        
        while remaining_batch > 0:
            # Get current category or start with first category
            current_category_id = self.state.get('current_category_id')
            if current_category_id is None:
                current_category_id = self.categories[0]['id']
                self.state['current_category_id'] = current_category_id
                self.state['last_processed_index'] = 0
                self.save_state()
            
            # Get category info
            category = next((c for c in self.categories if c['id'] == current_category_id), None)
            if not category:
                self.logger.error(f"Category {current_category_id} not found")
                return
            
            # Get shows for current category
            category_shows = self.shows_by_category[current_category_id]
            if not category_shows:
                self.logger.info(f"No shows found in category {category['name']}")
                # Move to next category
                next_category_idx = next((i for i, c in enumerate(self.categories) if c['id'] == current_category_id), -1) + 1
                if next_category_idx < len(self.categories):
                    self.state['current_category_id'] = self.categories[next_category_idx]['id']
                    self.state['last_processed_index'] = 0
                    self.save_state()
                    continue
                else:
                    break
            
            start_idx = self.state['last_processed_index']
            shows_left_in_category = len(category_shows) - start_idx
            
            if shows_left_in_category == 0:
                # Move to next category if current one is complete
                next_category_idx = next((i for i, c in enumerate(self.categories) if c['id'] == current_category_id), -1) + 1
                if next_category_idx < len(self.categories):
                    self.state['current_category_id'] = self.categories[next_category_idx]['id']
                    self.state['last_processed_index'] = 0
                    self.save_state()
                    continue
                else:
                    break
            
            # Process either remaining_batch or shows left in category, whichever is smaller
            batch_size = min(remaining_batch, shows_left_in_category)
            end_idx = start_idx + batch_size
            
            self.logger.info(f"Processing category: {category['name']} ({start_idx + 1}-{end_idx} of {len(category_shows)} shows)")
            
            try:
                for i in range(start_idx, end_idx):
                    show = category_shows[i]
                    self.logger.info(f"[{i + 1}/{len(category_shows)}] {show['name']} ", extra={'terminator': ''})
                    
                    try:
                        self.process_show(show)
                    except Exception as e:
                        self.logger.debug(f"Failed to process show: {str(e)}")
                    finally:
                        # Update state regardless of success/failure
                        self.state['last_processed_index'] = i + 1
                        self.save_state()
                
                # Update remaining batch count
                remaining_batch -= batch_size
                
                # If we've processed all shows in this category, prepare to move to next
                if end_idx >= len(category_shows):
                    next_category_idx = next((i for i, c in enumerate(self.categories) if c['id'] == current_category_id), -1) + 1
                    if next_category_idx < len(self.categories):
                        self.state['current_category_id'] = self.categories[next_category_idx]['id']
                        self.state['last_processed_index'] = 0
                        self.save_state()
                    else:
                        break
            finally:
                # Report cache statistics
                cache_manager.report_stats()
                
                # Print processing summary using root logger to access all handlers
                root_logger = logging.getLogger()
                for handler in root_logger.handlers:
                    if isinstance(handler, logging.Handler) and hasattr(handler, 'get_summary'):
                        summary = handler.get_summary()
                        if summary:
                            # Use root logger to ensure message goes through all handlers
                            root_logger.info(summary)
