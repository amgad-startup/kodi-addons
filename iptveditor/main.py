import argparse
import logging
from utils import setup_logging
from editor import IPTVEditor
from config import DEFAULT_BATCH_SIZE

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='IPTV Editor Show Processor')
    parser.add_argument(
        '--batch-size',
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f'Number of shows to process in one run (default: {DEFAULT_BATCH_SIZE})'
    )
    
    # Parse arguments
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logging()
    
    try:
        # Initialize and run editor
        editor = IPTVEditor(batch_size=args.batch_size)
        editor.process_shows()
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        exit(1)

if __name__ == "__main__":
    main()
