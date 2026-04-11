"""Module for managing and comparing stream catalogs."""

import json
import os
import re
from datetime import datetime
from iptv_toolkit.core.config import CONFIG

class CatalogManager:
    def __init__(self):
        """Initialize CatalogManager."""
        self.catalog_dir = "catalog"
        self._ensure_catalog_dir()
        self.filtering_config = CONFIG['filtering']['category']
        self.arabic_pattern = re.compile(self.filtering_config['language_rules']['arabic_regex'])
        self.english_pattern = re.compile(self.filtering_config['language_rules']['english_regex'])

    def _ensure_catalog_dir(self):
        """Ensure catalog directory exists."""
        if not os.path.exists(self.catalog_dir):
            os.makedirs(self.catalog_dir)

    def _get_catalog_path(self, stream_type, catalog_type):
        """Get path for catalog file."""
        return os.path.join(self.catalog_dir, f"{stream_type}_{catalog_type}.json")

    def _clean_text(self, text):
        """Clean text by removing extra spaces and special characters."""
        # Remove extra spaces
        text = ' '.join(text.split())
        # Remove special characters except hyphen between numbers
        text = re.sub(r'(?<!\d)-(?!\d)', '', text)
        # Remove spaces between numbers and hyphen
        text = re.sub(r'(\d)\s*-\s*(\d)', r'\1-\2', text)
        return text.strip()

    def _extract_tags_from_category(self, category_name):
        """Extract tags from a category name by splitting on language and delimiters."""
        tags = set()
        
        # Clean the category name
        category_name = self._clean_text(category_name)
        
        # First split by dash if present
        dash_parts = [part.strip() for part in category_name.split('-')]
        
        for part in dash_parts:
            # Find Arabic and English text in each part
            arabic_matches = re.finditer(self.arabic_pattern, part)
            english_matches = re.finditer(self.english_pattern, part)
            
            # Extract and clean Arabic text
            arabic_text = ' '.join(''.join(m.group()) for m in arabic_matches).strip()
            if arabic_text:
                tags.add(arabic_text)
            
            # Extract and clean English text
            english_text = ' '.join(''.join(m.group()) for m in english_matches).strip()
            if english_text:
                # Handle numbers specially
                number_pattern = re.compile(r'\d+(?:-\d+)?')
                numbers = number_pattern.findall(english_text)
                # Remove numbers from english_text
                english_text = number_pattern.sub('', english_text).strip()
                
                if english_text:
                    tags.add(english_text)
                
                # Add numbers as separate tags
                tags.update(numbers)
            
            # If no language-specific matches were found, add the whole part
            if not arabic_text and not english_text:
                clean_part = part.strip()
                if clean_part:
                    # Check if it's a number or contains only special characters
                    if re.match(r'^\d+(?:-\d+)?$', clean_part):
                        tags.add(clean_part)
                    else:
                        tags.add(clean_part)
        
        # Remove empty strings and return unique tags
        return sorted(tag for tag in tags if tag)

    def _should_include_category(self, category_name):
        """Check if a category should be included based on filtering rules."""
        # Check excluded keywords
        for keyword in self.filtering_config['excluded_keywords']:
            if keyword.lower() in category_name.lower():
                return False

        # Check language rules
        if not self.filtering_config['language_rules']['allow_mixed'] and \
           bool(self.arabic_pattern.search(category_name)) and \
           bool(self.english_pattern.search(category_name)):
            return False

        has_arabic = bool(self.arabic_pattern.search(category_name))
        has_english = bool(self.english_pattern.search(category_name))

        if has_arabic and not has_english:
            return self.filtering_config['language_rules']['allow_arabic_only']
        elif has_english and not has_arabic:
            return self.filtering_config['language_rules']['allow_english_only']
        elif has_arabic and has_english:
            return self.filtering_config['language_rules']['allow_mixed']

        return True

    def get_catalog(self, stream_type):
        """Get the current catalog for a stream type."""
        streams_path = self._get_catalog_path(stream_type, "streams")
        categories_path = self._get_catalog_path(stream_type, "categories")
        
        if not os.path.exists(streams_path) or not os.path.exists(categories_path):
            return None
            
        try:
            with open(streams_path, 'r', encoding='utf-8') as f:
                streams = json.load(f)
            with open(categories_path, 'r', encoding='utf-8') as f:
                categories = json.load(f)

            # Process categories and extract tags
            processed_categories = []
            for cat in categories['categories']:
                if self._should_include_category(cat.get('name', '')):
                    tags = self._extract_tags_from_category(cat.get('name', ''))
                    cat['tags'] = tags
                    processed_categories.append(cat)

            categories['categories'] = processed_categories

            return {
                'timestamp': streams['timestamp'],
                'streams': streams['streams'],
                'categories': categories['categories']
            }
        except Exception as e:
            print(f"Error reading catalog: {str(e)}")
            return None

    def save_catalog(self, stream_type, streams, categories):
        """Save current stream and category information."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Process categories and extract tags
        processed_categories = []
        for cat in categories:
            if self._should_include_category(cat.get('category_name', '')):
                tags = self._extract_tags_from_category(cat.get('category_name', ''))
                processed_categories.append({
                    "id": str(cat.get("category_id", "")),
                    "name": cat.get("category_name", ""),
                    "parent_id": str(cat.get("parent_id", "")),
                    "tags": tags
                })
        
        # Prepare streams catalog
        streams_catalog = {
            "timestamp": timestamp,
            "total_count": len(streams),
            "streams": [
                {
                    "id": str(s.get("stream_id") or s.get("series_id")),
                    "name": s.get("name", ""),
                    "category_id": str(s.get("category_id", "")),
                    "added": s.get("added", ""),
                    "container": s.get("container_extension", "mp4")
                }
                for s in streams
            ]
        }
        
        # Prepare categories catalog
        categories_catalog = {
            "timestamp": timestamp,
            "total_count": len(processed_categories),
            "categories": processed_categories
        }
        
        # Save catalogs
        with open(self._get_catalog_path(stream_type, "streams"), 'w', encoding='utf-8') as f:
            json.dump(streams_catalog, f, ensure_ascii=False, indent=2)
            
        with open(self._get_catalog_path(stream_type, "categories"), 'w', encoding='utf-8') as f:
            json.dump(categories_catalog, f, ensure_ascii=False, indent=2)

    def load_previous_catalog(self, stream_type):
        """Load previous catalog information."""
        streams_path = self._get_catalog_path(stream_type, "streams")
        categories_path = self._get_catalog_path(stream_type, "categories")
        
        streams_catalog = None
        categories_catalog = None
        
        if os.path.exists(streams_path):
            with open(streams_path, 'r', encoding='utf-8') as f:
                streams_catalog = json.load(f)
                
        if os.path.exists(categories_path):
            with open(categories_path, 'r', encoding='utf-8') as f:
                categories_catalog = json.load(f)
                
        return streams_catalog, categories_catalog

    def compare_catalogs(self, stream_type, current_streams, current_categories):
        """Compare current and previous catalogs to identify changes."""
        previous_streams, previous_categories = self.load_previous_catalog(stream_type)
        
        if not previous_streams or not previous_categories:
            print(f"\nNo previous catalog found for {stream_type}")
            self.save_catalog(stream_type, current_streams, current_categories)
            return
            
        # Convert current data to sets for comparison
        current_stream_ids = {str(s.get("stream_id") or s.get("series_id")) for s in current_streams}
        current_category_ids = {str(cat.get("category_id")) for cat in current_categories}
        
        # Convert previous data to sets
        previous_stream_ids = {s["id"] for s in previous_streams["streams"]}
        previous_category_ids = {cat["id"] for cat in previous_categories["categories"]}
        
        # Find differences
        new_streams = current_stream_ids - previous_stream_ids
        removed_streams = previous_stream_ids - current_stream_ids
        new_categories = current_category_ids - previous_category_ids
        removed_categories = previous_category_ids - current_category_ids
        
        # Print comparison results
        print(f"\nCatalog comparison for {stream_type}:")
        print(f"Previous catalog from: {previous_streams['timestamp']}")
        print(f"Streams: {len(current_streams)} (Previously: {previous_streams['total_count']})")
        print(f"Categories: {len(current_categories)} (Previously: {previous_categories['total_count']})")
        
        if new_streams:
            print(f"\nNew streams added: {len(new_streams)}")
            for stream in current_streams:
                stream_id = str(stream.get("stream_id") or stream.get("series_id"))
                if stream_id in new_streams:
                    print(f"- {stream.get('name', '')} ({stream_id})")
                    
        if removed_streams:
            print(f"\nStreams removed: {len(removed_streams)}")
            for stream in previous_streams["streams"]:
                if stream["id"] in removed_streams:
                    print(f"- {stream['name']} ({stream['id']})")
                    
        if new_categories:
            print(f"\nNew categories added: {len(new_categories)}")
            for cat in current_categories:
                if str(cat.get("category_id")) in new_categories:
                    print(f"- {cat.get('category_name', '')} ({cat.get('category_id')})")
                    
        if removed_categories:
            print(f"\nCategories removed: {len(removed_categories)}")
            for cat in previous_categories["categories"]:
                if cat["id"] in removed_categories:
                    print(f"- {cat['name']} ({cat['id']})")
        
        # Save current catalog
        self.save_catalog(stream_type, current_streams, current_categories)
