import os
import re
import json
import argparse
from iptv_toolkit.m3u.file_ops import (
    count_media_entries, 
    handle_existing_folders, 
    safe_create_dir,
    safe_remove_dir
)
from iptv_toolkit.m3u.media_processor import MediaProcessor

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Process M3U files for Kodi')
    parser.add_argument('--delete-folders', action='store_true',
                      help='Automatically delete existing folders without prompting')
    parser.add_argument('--all', action='store_true',
                      help='Process all titles without prompting for count')
    parser.add_argument('--resume', action='store_true',
                      help='Resume from last processed entry')
    return parser.parse_args()

def get_num_to_process(media_count, media_type, m3u_file, process_all=False):
    """Get the number of entries to process from user input"""
    if process_all:
        return media_count
        
    while True:
        try:
            num_input = input(
                f"How many {media_type} would you like to process from '{m3u_file}'? "
                f"(Enter 'all' or a number 1-{media_count}): "
            ).strip().lower()
            
            if num_input == 'all':
                return media_count
            elif num_input.isdigit() and 0 < int(num_input) <= media_count:
                return int(num_input)
            else:
                print(f"Please enter 'all' or a number between 1 and {media_count}")
        except KeyboardInterrupt:
            print("\nOperation cancelled by user.")
            return None
        except Exception as e:
            print(f"Invalid input. Please try again: {str(e)}")

def load_progress():
    """Load progress from progress file"""
    try:
        if os.path.exists('.m3u2strm_progress'):
            with open('.m3u2strm_progress', 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading progress: {str(e)}")
    return {}

def save_progress(m3u_file, entry_index, processed_count):
    """Save progress to progress file"""
    try:
        progress = load_progress()
        progress[m3u_file] = {
            'entry_index': entry_index,
            'processed_count': processed_count
        }
        with open('.m3u2strm_progress', 'w') as f:
            json.dump(progress, f)
    except Exception as e:
        print(f"Error saving progress: {str(e)}")

def process_entries(m3u_file_path, processor, num_to_process, is_tvshows, resume_data=None):
    """Process entries from the M3U file"""
    stream_name = group_title = tvg_name = None
    current_line = None
    total_entries = 0
    
    # If resuming, set the processed count
    if resume_data is not None:
        entry_index = resume_data.get('entry_index', 0)
        processed_count = resume_data.get('processed_count', 0)
        processor.processed_count = processed_count
        print(f"\nResuming from entry {entry_index} (successfully processed: {processed_count})")
    else:
        entry_index = 0
        processed_count = 0
    
    with open(m3u_file_path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if not line:  # Skip empty lines
                continue
                
            if line.startswith("#EXTINF:"):
                current_line = line
                tvg_name = None
                group_title = None
                
                # Extract tvg-name
                tvg_name_match = re.search(r'tvg-name="([^"]+)"', line)
                if tvg_name_match:
                    tvg_name = tvg_name_match.group(1)
                
                # Extract group-title
                group_title_match = re.search(r'group-title="([^"]+)"', line)
                if group_title_match:
                    group_title = group_title_match.group(1)
                
                # If no tvg-name found, try to extract from the title part
                if not tvg_name and ',' in line:
                    title_part = line.split(',', 1)[1].strip()
                    tvg_name = title_part

            elif line.startswith("http") and current_line:
                total_entries += 1
                
                # Skip entries we've already processed when resuming
                if total_entries <= entry_index:
                    current_line = None
                    tvg_name = None
                    group_title = None
                    continue
                
                # Ensure we have the minimum required information
                if tvg_name:
                    if not group_title:
                        group_title = "Ungrouped"  # Default group if none specified
                    
                    success = processor.process_entry(tvg_name, group_title, line, is_tvshows)
                    print(processor.get_progress_message(num_to_process, tvg_name), end='\r')
                    
                    # Save progress after each entry
                    save_progress(os.path.basename(m3u_file_path), total_entries, processor.processed_count)
                    
                    if processor.processed_count >= num_to_process:
                        break
                
                current_line = None
                tvg_name = None
                group_title = None

def print_completion_summary(processor, m3u_file):
    """Print the completion summary"""
    for line in processor.get_completion_summary(m3u_file):
        print(line)

def get_processing_info(m3u_files, args):
    """Get processing information for all files upfront"""
    processing_info = {}
    total_to_process = 0
    
    print("\nChecking M3U files...")
    for m3u_file in m3u_files:
        m3u_file_path = os.path.join(os.getcwd(), m3u_file)
        
        # Validate file exists and is readable
        if not os.path.isfile(m3u_file_path):
            print(f"Error: File '{m3u_file}' not found or not accessible.")
            continue
            
        # Check if the file is for TV shows or movies
        is_tvshows = 'tvshows' in m3u_file.lower() or 'shows' in m3u_file.lower()
        media_type = "shows" if is_tvshows else "movies"
        
        # Count media entries
        media_count = count_media_entries(m3u_file_path)
        if media_count == 0:
            print(f"No valid media entries found in '{m3u_file}'.")
            continue
            
        print(f"\n'{m3u_file}' contains {media_count} {media_type}.")
        
        # If resuming, adjust the number to process based on what's already done
        if args.resume:
            progress = load_progress()
            if m3u_file in progress:
                already_processed = progress[m3u_file].get('processed_count', 0)
                if already_processed > 0:
                    print(f"Already processed: {already_processed} entries")
        
        # Get number of entries to process
        num_to_process = get_num_to_process(media_count, media_type, m3u_file, args.all)
        if num_to_process is None:
            return None
            
        total_to_process += num_to_process
            
        # Setup output directories paths
        output_dir_grouped = os.path.join(os.getcwd(), os.path.splitext(m3u_file)[0])
        output_dir_flat = os.path.join(os.getcwd(), f"{os.path.splitext(m3u_file)[0]}-flat")
        
        # Store processing info
        processing_info[m3u_file] = {
            'path': m3u_file_path,
            'is_tvshows': is_tvshows,
            'num_to_process': num_to_process,
            'output_dir_grouped': output_dir_grouped,
            'output_dir_flat': output_dir_flat,
            'media_type': media_type
        }
    
    if processing_info:
        print(f"\nTotal items to process: {total_to_process}")
    
    return processing_info

def process_m3u_file(m3u_file, info, file_num, total_files, args):
    """Process a single M3U file"""
    print(f"\nProcessing file {file_num}/{total_files}: {m3u_file} ({info['media_type']})")
    
    # Load progress data if resuming
    resume_data = None
    if args.resume:
        progress = load_progress()
        resume_data = progress.get(m3u_file)
        print(f"Found resume data: {resume_data}")
        
        # When resuming, just create directories if they don't exist
        if not os.path.exists(info['output_dir_grouped']):
            if not safe_create_dir(info['output_dir_grouped']):
                print(f"\nError creating directory: {info['output_dir_grouped']}")
                return
        if not os.path.exists(info['output_dir_flat']):
            if not safe_create_dir(info['output_dir_flat']):
                print(f"\nError creating directory: {info['output_dir_flat']}")
                return
    else:
        # Handle existing folders before any directory creation
        if not handle_existing_folders(info['output_dir_grouped'], info['output_dir_flat']):
            print(f"\nSkipping '{m3u_file}' as folder handling was cancelled.")
            return
        
        # Create the directories
        if not safe_create_dir(info['output_dir_grouped']) or not safe_create_dir(info['output_dir_flat']):
            print(f"\nSkipping '{m3u_file}' due to directory creation errors.")
            return

    # Initialize media processor
    processor = MediaProcessor(info['output_dir_grouped'], info['output_dir_flat'])
    
    try:
        process_entries(info['path'], processor, info['num_to_process'], info['is_tvshows'], resume_data)
        print("\n")  # Clear the progress line
        print_completion_summary(processor, m3u_file)
    except Exception as e:
        print(f"\nError processing file: {str(e)}")

def main():
    """Main entry point"""
    try:
        args = parse_args()
        
        current_directory = os.getcwd()
        m3u_files = [f for f in os.listdir(current_directory) if f.endswith(".m3u")]
        
        if not m3u_files:
            print("No .m3u files found in the current directory.")
            return
            
        # Get processing information for all files upfront
        processing_info = get_processing_info(m3u_files, args)
        if not processing_info:
            return
            
        print("\nStarting processing...")
        total_files = len(processing_info)
        for file_num, (m3u_file, info) in enumerate(processing_info.items(), 1):
            process_m3u_file(m3u_file, info, file_num, total_files, args)
            
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
    except Exception as e:
        print(f"An unexpected error occurred: {str(e)}")

if __name__ == "__main__":
    main()
