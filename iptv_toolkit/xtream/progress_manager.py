"""Module for managing processing progress."""

import json
import os

class ProgressManager:
    @staticmethod
    def load_progress(stream_type):
        """Load progress for the given stream type."""
        filename = f".{stream_type}_progress.json"
        if os.path.exists(filename):
            try:
                with open(filename, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return {"processed": 0, "processed_ids": []}
        return {"processed": 0, "processed_ids": []}

    @staticmethod
    def save_progress(stream_type, progress):
        """Save progress for the given stream type."""
        filename = f".{stream_type}_progress.json"
        try:
            with open(filename, 'w') as f:
                if isinstance(progress, dict):
                    if "processed_ids" not in progress:
                        progress["processed_ids"] = []
                    json.dump(progress, f)
                else:
                    json.dump({"processed": progress, "processed_ids": []}, f)
        except Exception as e:
            print(f"Error saving progress: {str(e)}")
