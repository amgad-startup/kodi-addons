"""Main entry point for the Xtream Codes M3U playlist generator."""

import argparse
from iptv_toolkit.core import config
import os
import sqlite3
import shutil
import sys
from iptv_toolkit.xtream.api_client import XtreamCodesAPI
from iptv_toolkit.xtream.stream_processor import StreamProcessor
from iptv_toolkit.xtream.cache_manager import CacheManager
from iptv_toolkit.core.logger import get_logger, set_debug
from iptv_toolkit.core import utils

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Generate M3U playlists from Xtream Codes API')
    parser.add_argument('--max-titles', type=int, default=None,
                      help='Maximum number of titles to process in each stream type')
    parser.add_argument('--max-episodes', type=int, default=None,
                      help='Maximum number of episodes to process per series')
    parser.add_argument('--timeout', type=int, default=config.API_CONFIG['timeout'],
                      help='Timeout for API requests in seconds')
    parser.add_argument('--types', nargs='+', default=None,
                      help='Types of streams to process (live_streams, vod, series)')
    parser.add_argument('--skip-series', action='store_true',
                      help='Skip processing series (faster)')
    parser.add_argument('--clear-files', action='store_true',
                      help='Start fresh run (cleans existing folders and database)')
    parser.add_argument('--clear-cache', action='store_true',
                      help='Clear cache and logs')
    parser.add_argument('--name', type=str,
                      help='Filter content by name (case-insensitive partial match)')
    parser.add_argument('--mode', choices=['kodi', 'local'], default='local',
                      help='Mode of operation: kodi (direct database inserts) or local (create STRM/NFO files)')
    parser.add_argument('--retry-failed', action='store_true',
                      help='Retry processing previously failed streams')
    parser.add_argument('--interactive', action='store_true',
                      help='Run in interactive mode (select categories and streams)')
    parser.add_argument('--debug', action='store_true',
                      help='Enable debug logging')
    
    return parser.parse_args()

def clear_cache_and_logs():
    """Clear cache files and logs."""
    logger = get_logger(__name__)
    
    # Clear cache
    cache_manager = CacheManager()
    cache_manager.clear()
    print("Cache cleared successfully")
    
    # Clear logs
    program_dir = os.path.dirname(os.path.abspath(__file__))
    logs_dir = os.path.join(program_dir, '.logs')
    if os.path.exists(logs_dir):
        shutil.rmtree(logs_dir)
        os.makedirs(logs_dir)
        print("Logs cleared successfully")

def main():
    """Main entry point for the application."""
    args = parse_arguments()
    
    # Set debug mode in logger
    set_debug(args.debug)
    
    # Initialize logger with debug setting
    logger = get_logger(__name__)
    
    # Handle cache and logs clearing if requested
    if args.clear_cache:
        clear_cache_and_logs()
        # If only --clear-cache is used (no other processing flags), exit
        if not (args.types or args.retry_failed or args.interactive):
            sys.exit(0)
    
    # Check if API credentials are set
    if not all([config.API_CONFIG['url'], config.API_CONFIG['username'], config.API_CONFIG['password']]):
        logger.error("Error: API credentials not found in environment variables")
        logger.error("Please set XTREAM_API_URL, XTREAM_USERNAME, and XTREAM_PASSWORD environment variables")
        return
    
    # Set default types if none provided
    if args.types is None:
        args.types = config.STREAM_TYPES['default']
    
    logger.debug("Starting with arguments:")
    logger.debug(f"Max titles per type: {args.max_titles if args.max_titles else 'unlimited'}")
    logger.debug(f"Max episodes per series: {args.max_episodes if args.max_episodes else 'unlimited'}")
    logger.debug(f"Timeout: {args.timeout}")
    logger.debug(f"Types: {args.types}")
    logger.debug(f"Mode: {'Fresh run' if args.clear_files else 'Resume'}")
    logger.debug(f"Operation mode: {args.mode}")
    logger.debug(f"Full arguments: {args}")
    
    # Initialize API client
    api = XtreamCodesAPI(
        config.API_CONFIG['url'],
        config.API_CONFIG['username'],
        config.API_CONFIG['password'],
        timeout=args.timeout
    )
    
    # Authenticate
    print("\nAttempting authentication...")
    auth_data = api.authenticate()
    if not auth_data:
        logger.error("Authentication failed")
        return
    print("Authentication successful")
    
    # Initialize stream processor with keyword arguments
    processor = StreamProcessor(
        api_client=api,
        max_titles=args.max_titles,
        fresh_run=args.clear_files,
        max_episodes=args.max_episodes,
        mode=args.mode,
        types=args.types,
        name_filter=args.name
    )
    
    # Handle fresh run cleanup
    if args.clear_files:
        if args.mode == 'kodi':
            utils.clean_kodi_database()
        if not args.retry_failed:
            # Only clear failed streams if not retrying them
            processor.failed_tracker.clear_failed_streams()
    
    if args.retry_failed:
        # Process previously failed streams
        failed_streams = processor.failed_tracker.get_failed_streams()
        if failed_streams:
            logger.info(f"\nRetrying {len(failed_streams)} failed streams...")
            # Group failed streams by type for batch processing
            by_type = {}
            for failed in failed_streams:
                stream_type = failed['stream_type']
                if stream_type in args.types:
                    by_type.setdefault(stream_type, []).append(failed['stream'])
            
            # Process each type's failed streams
            for stream_type, streams in by_type.items():
                if args.max_titles:
                    streams = streams[:args.max_titles]
                processor.process_streams_in_batches(streams, stream_type, 
                                                   config.OUTPUT_FILES[stream_type])
            
            processor.failed_tracker.clear_failed_streams()
        else:
            logger.info("\nNo failed streams to retry")
    else:
        if args.interactive:
            # Let user choose stream type first
            print("\nAvailable stream types:")
            valid_types = [t for t in args.types if t in config.OUTPUT_FILES]
            for i, stream_type in enumerate(valid_types, 1):
                print(f"{i}. {stream_type}")
            
            while True:
                try:
                    choice = int(input("\nSelect stream type (number): ")) - 1
                    if 0 <= choice < len(valid_types):
                        from interactive_processor import process_interactively
                        process_interactively(api, processor, valid_types[choice])
                        break
                    else:
                        logger.warning("Invalid selection. Please try again.")
                except ValueError:
                    logger.warning("Please enter a number.")
        else:
            # Process each stream type
            for stream_type in args.types:
                if stream_type not in config.OUTPUT_FILES:
                    logger.error(f"Unknown stream type: {stream_type}")
                    continue
                
                print(f"\nProcessing {stream_type}...")
                streams = api.get_stream_list(stream_type)
                if streams:
                    print(f"Found {len(streams)} streams")
                    processor.process_streams_in_batches(streams, stream_type, config.OUTPUT_DIRS[stream_type], config.OUTPUT_FILES[stream_type])
                else:
                    logger.warning(f"No {stream_type} streams found")

if __name__ == "__main__":
    main()
