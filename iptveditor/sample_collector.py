import json
import logging
from api import TMDBApi, IPTVEditorApi

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

def save_response(data, filename):
    with open(f'samples/{filename}', 'w') as f:
        json.dump(data, f, indent=2)
    logging.info(f"Saved response to samples/{filename}")

def main():
    logger = setup_logging()
    tmdb_api = TMDBApi()
    iptv_api = IPTVEditorApi()

    # Collect TMDB search response
    logger.info("Getting TMDB search response...")
    search_result = tmdb_api.search_show("Breaking Bad")
    save_response(search_result, "tmdb/search_show.json")

    # Collect TMDB details response
    show_id = search_result['id']
    logger.info(f"Getting TMDB details for show ID {show_id}...")
    details_result = tmdb_api.get_show_details(show_id)
    save_response(details_result, "tmdb/show_details.json")

    # Collect IPTV Editor episodes response
    logger.info("Getting IPTV Editor episodes response...")
    episodes_result = iptv_api.get_episodes(3816)  # Using a known series ID
    save_response(episodes_result, "iptveditor/episodes.json")

    # Collect IPTV Editor update show response
    logger.info("Getting IPTV Editor update show response...")
    update_result = iptv_api.update_show(3816, show_id, 1)  # Using sample IDs
    save_response(update_result, "iptveditor/update_show.json")

if __name__ == "__main__":
    main()
