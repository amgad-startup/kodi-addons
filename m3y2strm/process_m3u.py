import os
import re
import argparse
from media_processor import MediaProcessor

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Process M3U files with TMDB metadata')
    parser.add_argument('--all', action='store_true',
                      help='Process all entries without prompting')
    return parser.parse_args()

def get_num_to_process(media_count, media_type, m3u_file, process_all=False):
    """Get the number of entries to process"""
    if process_all:
        return media_count
        
    while True:
        try:
            num_input = input(
                f"\nHow many {media_type} would you like to process from '{m3u_file}'? "
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

def count_media_entries(file_path):
    """Count media entries in M3U file"""
    try:
        count = 0
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                if line.strip().startswith("http"):
                    count += 1
        return count
    except Exception as e:
        print(f"Error counting media entries: {str(e)}")
        return 0

def process_m3u_file(m3u_file_path, num_to_process, is_tvshows):
    """Process entries from the M3U file using MediaProcessor"""
    # Setup output directories
    base_name = os.path.splitext(os.path.basename(m3u_file_path))[0]
    output_dir_grouped = os.path.join(os.getcwd(), base_name)
    output_dir_flat = os.path.join(os.getcwd(), f"{base_name}-flat")
    
    # Initialize media processor
    processor = MediaProcessor(output_dir_grouped, output_dir_flat)
    
    stream_name = group_title = tvg_name = None
    with open(m3u_file_path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if line.startswith("#EXTINF:"):
                tvg_name_match = re.search(r'tvg-name="([^"]+)"', line)
                group_title_match = re.search(r'group-title="([^"]+)"', line)
                
                if tvg_name_match:
                    tvg_name = tvg_name_match.group(1)
                if group_title_match:
                    group_title = group_title_match.group(1)

            elif line.startswith("http") and tvg_name and group_title:
                processor.process_entry(tvg_name, group_title, line, is_tvshows)
                print(processor.get_progress_message(num_to_process, tvg_name))
                
                if processor.processed_count >= num_to_process:
                    break
                    
                stream_name = group_title = tvg_name = None

    print("\n")  # Clear the progress line
    for line in processor.get_completion_summary(m3u_file_path):
        print(line)

def main():
    """Main entry point"""
    try:
        args = parse_args()
        
        # Find M3U files in current directory
        m3u_files = [f for f in os.listdir() if f.endswith(".m3u")]
        if not m3u_files:
            print("No .m3u files found in the current directory.")
            return
            
        print("\nProcessing M3U files...")
        for m3u_file in m3u_files:
            # Check if file exists and is readable
            if not os.path.isfile(m3u_file):
                print(f"Error: File '{m3u_file}' not found or not accessible.")
                continue
                
            # Determine if it's TV shows or movies
            is_tvshows = 'tvshows' in m3u_file.lower() or 'shows' in m3u_file.lower()
            media_type = "shows" if is_tvshows else "movies"
            
            # Count entries
            media_count = count_media_entries(m3u_file)
            if media_count == 0:
                print(f"No valid media entries found in '{m3u_file}'.")
                continue
                
            print(f"\n'{m3u_file}' contains {media_count} {media_type}.")
            
            # Get number to process
            num_to_process = get_num_to_process(media_count, media_type, m3u_file, args.all)
            if num_to_process is None:
                continue
                
            # Process the file
            process_m3u_file(m3u_file, num_to_process, is_tvshows)
            
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
    except Exception as e:
        print(f"An unexpected error occurred: {str(e)}")

if __name__ == "__main__":
    main()
