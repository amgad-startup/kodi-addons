"""Module for file and directory operations."""

import os
import shutil

def get_dir_size(path):
    """Get directory size in human readable format."""
    total = 0
    try:
        for entry in os.scandir(path):
            if entry.is_file():
                total += entry.stat().st_size
            elif entry.is_dir():
                total += get_dir_size(entry.path)
    except Exception:
        return 0
    return total

def format_size(size):
    """Format size in bytes to human readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"

def handle_existing_folders(*folders):
    """Handle existing folders with user interaction.
    
    Args:
        *folders: Paths to check
        
    Returns:
        bool: True if operation should proceed, False if cancelled
    """
    existing = []
    for folder in folders:
        if os.path.exists(folder):
            size = get_dir_size(folder)
            existing.append((folder, size))
    
    if not existing:
        return True
        
    print("\nExisting folders found:")
    for folder, size in existing:
        print(f"- {folder} ({format_size(size)})")
    
    while True:
        choice = input("\nHow would you like to proceed?\n"
                      "1. Delete existing folders and start fresh\n"
                      "2. Keep existing folders and add to them\n"
                      "3. Cancel operation\n"
                      "Choice (1-3): ").strip()
        
        if choice == '1':
            print("\nDeleting existing folders...")
            for folder, _ in existing:
                try:
                    shutil.rmtree(folder)
                    print(f"Deleted: {folder}")
                except Exception as e:
                    print(f"Error deleting {folder}: {str(e)}")
                    return False
            return True
        elif choice == '2':
            print("\nKeeping existing folders...")
            return True
        elif choice == '3':
            print("\nOperation cancelled.")
            return False
        else:
            print("\nInvalid choice. Please enter 1, 2, or 3.")

def safe_create_dir(path):
    """Safely create directory and all parent directories."""
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except Exception as e:
        print(f"Error creating directory {path}: {str(e)}")
        return False

def safe_remove_dir(path):
    """Safely remove directory and all contents."""
    try:
        if os.path.exists(path):
            shutil.rmtree(path)
        return True
    except Exception as e:
        print(f"Error removing directory {path}: {str(e)}")
        return False
