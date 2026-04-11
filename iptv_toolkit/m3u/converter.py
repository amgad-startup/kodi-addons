import os
import re
from collections import defaultdict

def is_english_name(text):
    # Return False for empty strings
    if not text:
        return False
        
    # If text ends with مدبلج, consider it Arabic regardless
    if text.strip().endswith('مدبلج'):
        return False
        
    # Remove common non-letter characters, spaces, and numbers
    cleaned_text = re.sub(r'[0-9\s\-_\(\)\[\]\.]+', '', text)
    if not cleaned_text:
        return False
    
    # If the text contains any Arabic characters, consider it non-English
    if any('\u0600' <= c <= '\u06FF' for c in text):
        return False
        
    # Count English letters vs non-English characters
    english_chars = sum(1 for c in cleaned_text if c.isascii() and c.isalpha())
    total_chars = len(cleaned_text)
    
    # Consider it English if more than 80% of characters are English letters
    return english_chars / total_chars > 0.8 if total_chars > 0 else False

def extract_show_info(stream_name):
    # Extract show name, season, and episode info from titles like "Show Name S01 E01"
    pattern = r"(.*?)(?:\s+S(\d+)\s+E(\d+))"
    match = re.match(pattern, stream_name)
    
    if match:
        show_name = match.group(1).strip()
        season = match.group(2)
        episode = match.group(3)
        return show_name, season, episode
    return None, None, None

def sanitize_filename(filename):
    # Remove invalid characters for filenames
    invalid = '<>:"/\\|?*'
    for char in invalid:
        filename = filename.replace(char, '')
    return filename.strip()

def safe_create_dir(dir_path):
    """Safely create directory and handle potential errors"""
    try:
        os.makedirs(dir_path, exist_ok=True)
        return True
    except Exception as e:
        print(f"Error creating directory {dir_path}: {str(e)}")
        return False

def safe_write_file(file_path, content):
    """Safely write content to file and handle potential errors"""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    except Exception as e:
        print(f"Error writing file {file_path}: {str(e)}")
        return False

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

def create_strm_files():
    current_directory = os.getcwd()
    m3u_files = [f for f in os.listdir(current_directory) if f.endswith(".m3u")]
    
    if not m3u_files:
        print("No .m3u files found in the current directory.")
        return
    
    for m3u_file in m3u_files:
        m3u_file_path = os.path.join(current_directory, m3u_file)
        
        # Validate file exists and is readable
        if not os.path.isfile(m3u_file_path):
            print(f"Error: File '{m3u_file}' not found or not accessible.")
            continue
            
        # Check if the file is for TV shows or movies
        is_tvshows = 'tvshows' in m3u_file.lower() or 'shows' in m3u_file.lower()
        list_name = os.path.splitext(m3u_file)[0]
        
        # Create both grouped and flat output directories
        list_output_dir_grouped = os.path.join(current_directory, list_name)
        list_output_dir_flat = os.path.join(current_directory, f"{list_name.replace('-final', '-flat')}")
        
        if not safe_create_dir(list_output_dir_grouped) or not safe_create_dir(list_output_dir_flat):
            print(f"Skipping '{m3u_file}' due to directory creation errors.")
            continue

        # Count media entries
        media_count = count_media_entries(m3u_file_path)
        if media_count == 0:
            print(f"No valid media entries found in '{m3u_file}'.")
            continue
            
        media_type = "shows" if is_tvshows else "movies"
        print(f"\n'{m3u_file}' contains {media_count} {media_type}.")

        # Prompt for the number of entries to process
        while True:
            try:
                num_input = input(f"How many {media_type} would you like to process from '{m3u_file}'? (Enter 'all' or a number): ").strip().lower()
                if num_input == 'all':
                    num_to_process = media_count
                    break
                elif num_input.isdigit() and 0 < int(num_input) <= media_count:
                    num_to_process = int(num_input)
                    break
                else:
                    print(f"Please enter 'all' or a number between 1 and {media_count}")
            except KeyboardInterrupt:
                print("\nOperation cancelled by user.")
                return
            except Exception as e:
                print(f"Invalid input. Please try again: {str(e)}")

        stream_name, group_title, tvg_name = None, None, None
        processed_count = 0
        skipped_english_count = 0
        error_count = 0
        total_processed = 0

        try:
            with open(m3u_file_path, 'r', encoding='utf-8') as file:
                # Process files and create folders
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
                        total_processed += 1
                        
                        # Skip if the name is in English
                        if is_english_name(tvg_name):
                            skipped_english_count += 1
                            print(f"Processed {processed_count}/{num_to_process} {media_type} (Skipped {skipped_english_count} English names)...", end='\r')
                            continue

                        success = False
                        if is_tvshows:
                            # Extract show name, season, and episode info for TV shows
                            show_name, season, episode = extract_show_info(tvg_name)
                            if show_name and season and episode:
                                # Create grouped structure (with group-title)
                                group_dir = os.path.join(list_output_dir_grouped, sanitize_filename(group_title))
                                show_dir_grouped = os.path.join(group_dir, sanitize_filename(show_name))
                                season_dir_grouped = os.path.join(show_dir_grouped, f"Season {season.zfill(2)}")
                                
                                # Create flat structure (without group-title)
                                show_dir_flat = os.path.join(list_output_dir_flat, sanitize_filename(show_name))
                                season_dir_flat = os.path.join(show_dir_flat, f"Season {season.zfill(2)}")
                                
                                if safe_create_dir(season_dir_grouped) and safe_create_dir(season_dir_flat):
                                    # Create the strm filename with season and episode
                                    strm_filename = f"S{season.zfill(2)}E{episode.zfill(2)}.strm"
                                    strm_file_path_grouped = os.path.join(season_dir_grouped, strm_filename)
                                    strm_file_path_flat = os.path.join(season_dir_flat, strm_filename)

                                    # Write both .strm files
                                    if safe_write_file(strm_file_path_grouped, line) and safe_write_file(strm_file_path_flat, line):
                                        success = True
                            else:
                                print(f"\nSkipping '{tvg_name}' as it doesn't match TV show format.")
                        else:
                            # For movies, create a directory for each movie
                            group_dir = os.path.join(list_output_dir_grouped, sanitize_filename(group_title))
                            movie_dir_grouped = os.path.join(group_dir, sanitize_filename(tvg_name))
                            movie_dir_flat = os.path.join(list_output_dir_flat, sanitize_filename(tvg_name))
                            
                            if safe_create_dir(movie_dir_grouped) and safe_create_dir(movie_dir_flat):
                                # Create .strm files in both locations
                                strm_filename = "movie.strm"
                                strm_file_path_grouped = os.path.join(movie_dir_grouped, strm_filename)
                                strm_file_path_flat = os.path.join(movie_dir_flat, strm_filename)

                                # Write both .strm files
                                if safe_write_file(strm_file_path_grouped, line) and safe_write_file(strm_file_path_flat, line):
                                    success = True
                        
                        if success:
                            processed_count += 1
                        else:
                            error_count += 1
                            
                        print(f"Processed {processed_count}/{num_to_process} {media_type} (Skipped {skipped_english_count} English names)...", end='\r')
                        
                        # Stop processing if the specified limit is reached
                        if processed_count >= num_to_process:
                            break
                        
                        # Reset variables for the next entry
                        stream_name, group_title, tvg_name = None, None, None

        except Exception as e:
            print(f"\nError processing file: {str(e)}")
        finally:
            print(f"\nCompleted processing '{m3u_file}':")
            print(f"- Successfully created: {processed_count} files")
            print(f"- Skipped English names: {skipped_english_count}")
            print(f"- Errors encountered: {error_count}")
            print(f"- Total processed: {total_processed}")
            print(f"Grouped structure in: '{list_output_dir_grouped}'")
            print(f"Flat structure in: '{list_output_dir_flat}'")

if __name__ == "__main__":
    try:
        create_strm_files()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
    except Exception as e:
        print(f"An unexpected error occurred: {str(e)}")
