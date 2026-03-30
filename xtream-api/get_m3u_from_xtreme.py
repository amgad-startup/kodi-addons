"""Script to generate M3U playlists from Xtream Codes API."""

import argparse
import config
from api_client import XtreamCodesAPI
from stream_processor import StreamProcessor

def get_processing_info(api, args):
    """Get processing information."""
    auth_data = api.authenticate()
    if not auth_data:
        print("Authentication failed")
        return None
    
    print("Authentication successful")
    return auth_data

def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description='Generate M3U playlists from Xtream Codes API')
    parser.add_argument('--url', default=config.API_URL,
                      help='Base URL for the Xtream Codes API')
    parser.add_argument('--username', default=config.USERNAME,
                      help='Username for authentication')
    parser.add_argument('--password', default=config.PASSWORD,
                      help='Password for authentication')
    parser.add_argument('--timeout', type=int, default=config.DEFAULT_TIMEOUT,
                      help='Timeout for API requests in seconds')
    parser.add_argument('--types', nargs='+', default=config.DEFAULT_STREAM_TYPES,
                      help='Types of streams to process (live_streams, vod, series)')
    parser.add_argument('--skip-series', action='store_true',
                      help='Skip processing series (faster)')
    parser.add_argument('--fresh', action='store_true',
                      help='Start fresh run (cleans existing folders and starts from beginning)')
    parser.add_argument('--name', type=str,
                      help='Filter content by name (case-insensitive partial match)')
    parser.add_argument('--interactive', action='store_true',
                      help='Run in interactive mode (select categories and streams)')
    
    args = parser.parse_args()
    
    # # Remove series from types if skip-series is set
    # if args.skip_series and 'series' in args.types:
    #     args.types.remove('series')
    
    print(f"\nStarting with arguments:")
    print(f"URL: {args.url}")
    print(f"Timeout: {args.timeout}")
    print(f"Types: {args.types}")
    print(f"Mode: {'Fresh run' if args.fresh else 'Resume'}")
    
    # Initialize API client
    api = XtreamCodesAPI(args.url, args.username, args.password, args.timeout)
    
    # Get processing info
    if not get_processing_info(api, args):
        return
    
    # Initialize stream processor
    processor = StreamProcessor(api, fresh_run=args.fresh, name_filter=args.name)
    
    # Import interactive processor if needed
    if args.interactive:
        from interactive_processor import process_interactively
    
    if args.interactive:
        # Let user select stream type in interactive mode
        while True:
            print("\nAvailable stream types:")
            for i, stype in enumerate(args.types, 1):
                print(f"{i}. {stype}")
            try:
                choice = input("\nSelect stream type (number) or 'q' to quit: ").strip().lower()
                if choice == 'q':
                    break
                idx = int(choice) - 1
                if 0 <= idx < len(args.types):
                    stream_type = args.types[idx]
                    if stream_type in config.OUTPUT_FILES:
                        process_interactively(api, processor, stream_type)
                    else:
                        print(f"Unknown stream type: {stream_type}")
                else:
                    print("Invalid selection. Please try again.")
            except ValueError:
                print("Invalid input. Please enter a number or 'q'.")
    else:
        # Process each stream type in non-interactive mode
        for stream_type in args.types:
            if stream_type not in config.OUTPUT_FILES:
                print(f"Unknown stream type: {stream_type}")
                continue
            
            streams = api.get_stream_list(stream_type)
            if streams:
                processor.process_streams_in_batches(streams, stream_type, config.OUTPUT_FILES[stream_type])
            else:
                print(f"No {stream_type} streams found")

if __name__ == "__main__":
    main()
