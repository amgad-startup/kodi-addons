"""Module for interactive stream processing."""

from iptv_toolkit.core import config
from iptv_toolkit.xtream.catalog_manager import CatalogManager
from collections import defaultdict

def get_user_selection(options, prompt="Enter selection (comma-separated IDs or 'all')"):
    """Get user selection from a list of options."""
    while True:
        selection = input(f"\n{prompt}: ").strip().lower()
        if selection == 'all':
            return [opt['id'] for opt in options]
        try:
            # Convert input to strings for comparison since API returns string IDs
            ids = [str(id.strip()) for id in selection.split(',')]
            # Extract valid IDs, handling both 'category_id' and 'id' keys
            valid_ids = []
            for opt in options:
                if 'category_id' in opt:
                    valid_ids.append(str(opt['category_id']))
                elif 'id' in opt:
                    valid_ids.append(str(opt['id']))
            invalid_ids = [id for id in ids if id not in valid_ids]
            if not invalid_ids:
                return ids
            print(f"\nInvalid ID(s): {invalid_ids}")
            print(f"Valid IDs are: {sorted(valid_ids)}")
            print("Please try again.")
        except ValueError:
            print("Invalid input. Please enter comma-separated numbers or 'all'")

def get_filter_reason(cat_name, catalog_manager):
    """Get the reason why a category is filtered."""
    if any(keyword.lower() in cat_name.lower() for keyword in catalog_manager.filtering_config['excluded_keywords']):
        return "Excluded keyword"
    
    has_arabic = bool(catalog_manager.filtering_config['language_rules']['arabic_regex'])
    has_english = bool(catalog_manager.filtering_config['language_rules']['english_regex'])
    
    if has_arabic and has_english and not catalog_manager.filtering_config['language_rules']['allow_mixed']:
        return "Mixed language"
    elif has_arabic and not catalog_manager.filtering_config['language_rules']['allow_arabic_only']:
        return "Arabic-only"
    elif has_english and not catalog_manager.filtering_config['language_rules']['allow_english_only']:
        return "English-only"
    return ""

def process_interactively(api, processor, stream_type):
    """Process streams interactively by category and title."""
    print(f"\nFetching {stream_type} categories...")
    category_map, categories = api.get_categories(stream_type)
    
    if not categories:
        print(f"No categories found for {stream_type}")
        return
        
    # Initialize CatalogManager for filtering check
    catalog_manager = CatalogManager()
    
    # Display categories with stream counts and filter status
    print("\nAvailable categories:")
    streams = api.get_stream_list(stream_type)
    if not streams:
        print("No streams found")
        return
        
    # Create a mapping of category IDs for validation
    valid_category_ids = {cat['category_id'] for cat in categories}
    
    # Statistics counters
    stats = defaultdict(lambda: {"categories": 0, "streams": 0})
    total_categories = len(categories)
    total_included_categories = 0
    total_included_streams = 0
    total_filtered_streams = 0
    
    # Print header
    print("\n{:<6} {:<35} {:<8} {:<12} {:<20}".format("ID", "Category Name", "Streams", "Status", "Filter Reason"))
    print("-" * 81)
    
    for cat in categories:
        cat_id = cat['category_id']
        cat_name = cat['category_name']
        cat_streams = [s for s in streams if s['category_id'] == cat_id]
        stream_count = len(cat_streams)
        
        # Check if category will be filtered
        will_be_filtered = not catalog_manager._should_include_category(cat_name)
        status = "❌ FILTERED" if will_be_filtered else "✓ INCLUDED"
        
        # Get filter reason if filtered
        reason = get_filter_reason(cat_name, catalog_manager) if will_be_filtered else ""
        
        # Extract tags for the category
        tags = catalog_manager._extract_tags_from_category(cat_name)
        
        # Update statistics
        if will_be_filtered:
            stats[reason]["categories"] += 1
            stats[reason]["streams"] += stream_count
            total_filtered_streams += stream_count
        else:
            total_included_categories += 1
            total_included_streams += stream_count
        
        # Print category info in table format
        print("{:<6} {:<35} {:<8} {:<12} {:<20}".format(
            cat_id,
            cat_name[:32] + "..." if len(cat_name) > 32 else cat_name,
            stream_count,
            status,
            reason
        ))
        
        # Print tags if category is included
        if not will_be_filtered and tags:
            print("{:<6} └─ Tags: {}".format("", ", ".join(tags)))
    
    # Print summary
    print("\n" + "=" * 60)
    print("FILTERING SUMMARY")
    print("=" * 60)
    print(f"Total Categories: {total_categories} ({total_included_categories} included, {total_categories - total_included_categories} filtered)")
    print(f"Total Streams: {total_included_streams + total_filtered_streams} ({total_included_streams} included, {total_filtered_streams} filtered)")
    
    if stats:
        print("\nBreakdown by Filter Reason:")
        for reason, counts in stats.items():
            print(f"- {reason}:")
            print(f"  • Categories: {counts['categories']}")
            print(f"  • Streams: {counts['streams']}")
    print("=" * 60)
    
    while True:
        try:
            # Get category selection
            selected_cats = get_user_selection(
                categories, 
                "\nEnter category IDs to process (comma-separated or 'all', CTRL+C to exit)"
            )
            
            # Validate selected categories exist
            invalid_cats = [cat_id for cat_id in selected_cats if cat_id not in valid_category_ids]
            if invalid_cats:
                print(f"\nWarning: The following category IDs do not exist: {invalid_cats}")
                continue
            
            # Process each selected category
            for cat_id in selected_cats:
                cat_name = next(c['category_name'] for c in categories if c['category_id'] == cat_id)
                cat_streams = [s for s in streams if s['category_id'] == cat_id]
                
                if not cat_streams:
                    print(f"\nNo streams found in category {cat_name}")
                    continue
                    
                # Display streams in category
                print(f"\nStreams in category {cat_name}:")
                for stream in cat_streams:
                    # Handle different possible ID keys
                    stream_id = stream.get('stream_id') or stream.get('series_id') or stream.get('id')
                    if not stream_id:
                        print("Warning: Stream found with no ID")
                        continue
                    print(f"ID: {stream_id} - {stream.get('name', 'Unnamed')}")
                
                # Get stream selection
                selected_streams = get_user_selection(
                    [{'id': s.get('stream_id') or s.get('series_id') or s.get('id')} for s in cat_streams],
                    "\nEnter stream IDs to process (comma-separated or 'all')"
                )
                
                # Filter and process selected streams
                to_process = [s for s in cat_streams 
                            if str(s.get('stream_id') or s.get('series_id') or s.get('id')) in selected_streams]
                if to_process:
                    print(f"\nProcessing {len(to_process)} streams from {cat_name}...")
                    output_file = config.OUTPUT_FILES.get(stream_type)
                    output_folder = config.OUTPUT_DIRS.get(stream_type)
                    print(f"Using output file: {output_file}")
                    print(f"Stream type: {stream_type}")
                    print(f"Selected streams IDs: {selected_streams}")
                    print(f"First stream data: {to_process[0]}")
                    processor.process_streams_in_batches(to_process, stream_type, output_folder, output_file)
                else:
                    print(f"\nNo streams to process from selection")
                
            # Ask if user wants to process more categories
            again = input("\nProcess more categories? (y/n): ").lower().strip()
            if again != 'y':
                break
                
        except KeyboardInterrupt:
            print("\nInteractive mode cancelled")
            break
