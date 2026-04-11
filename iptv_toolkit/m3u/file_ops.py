import os
import shutil
import stat
import time

def handle_remove_readonly(func, path, exc):
    """Handle read-only files during directory removal"""
    excvalue = exc[1]
    if func in (os.rmdir, os.remove, os.unlink) and excvalue.errno == errno.EACCES:
        # Change the file to be readable, writable, and executable
        os.chmod(path, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
        # Try again
        func(path)
    else:
        raise

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

def safe_remove_dir(dir_path):
    """Safely remove directory and all its contents with retries"""
    if not os.path.exists(dir_path):
        return True

    print(f"Removing: {dir_path}")
    max_retries = 3
    retry_delay = 1  # seconds

    for attempt in range(max_retries):
        try:
            # First try to change permissions
            for root, dirs, files in os.walk(dir_path):
                for d in dirs:
                    os.chmod(os.path.join(root, d), stat.S_IRWXU)
                for f in files:
                    os.chmod(os.path.join(root, f), stat.S_IRWXU)
            
            # Then remove the directory
            shutil.rmtree(dir_path, onerror=handle_remove_readonly)
            print("Successfully removed directory.")
            return True
            
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"Retry {attempt + 1}/{max_retries}: Failed to remove directory. Waiting {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                print(f"Error removing directory {dir_path} after {max_retries} attempts: {str(e)}")
                return False
    
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

def get_dir_size(dir_path):
    """Get the total size of a directory in bytes"""
    total_size = 0
    try:
        for dirpath, dirnames, filenames in os.walk(dir_path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    total_size += os.path.getsize(fp)
                except (OSError, IOError):
                    continue
    except Exception:
        pass
    return total_size

def format_size(size):
    """Format size in bytes to human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"

def handle_existing_folders(grouped_dir, flat_dir):
    """
    Handle existing output folders
    Returns True if processing should continue, False if cancelled
    """
    existing_dirs = []
    if os.path.exists(grouped_dir):
        size = format_size(get_dir_size(grouped_dir))
        existing_dirs.append(f"- Grouped directory ({size}): {grouped_dir}")
    if os.path.exists(flat_dir):
        size = format_size(get_dir_size(flat_dir))
        existing_dirs.append(f"- Flat directory ({size}): {flat_dir}")
        
    if existing_dirs:
        print("\nWARNING: Existing output folders found:")
        for dir_info in existing_dirs:
            print(dir_info)
            
        while True:
            try:
                choice = input("\nChoose an option:\n"
                             "1. Delete old content and start fresh\n"
                             "2. Keep old content and add to it\n"
                             "3. Cancel operation\n"
                             "Enter choice (1-3): ").strip()
                
                if choice == "1":
                    print("\nRemoving old content...")
                    success = True
                    if os.path.exists(grouped_dir):
                        success = success and safe_remove_dir(grouped_dir)
                    if os.path.exists(flat_dir):
                        success = success and safe_remove_dir(flat_dir)
                        
                    if success:
                        print("Old content removed successfully.")
                        return True
                    else:
                        print("Failed to remove old content. Operation cancelled.")
                        return False
                elif choice == "2":
                    print("\nKeeping existing content. New files will be added to existing folders.")
                    return True
                elif choice == "3":
                    print("\nOperation cancelled by user.")
                    return False
                else:
                    print("Please enter 1, 2, or 3")
            except KeyboardInterrupt:
                print("\nOperation cancelled by user.")
                return False
    return True
