# IPTV Editor

[Previous sections remain unchanged until Using the Cache in Other Projects]

#### Using the Cache in Other Projects

The cache database (cache.db) can be used to retrieve show metadata in other projects:

1. Copy the database file:

```bash
cp cache.db /path/to/your/project/
```

2. Use in Python code:

```python
from database import CacheManager

# Initialize cache manager
cache = CacheManager()

# Search for show metadata by title
metadata = cache.search_by_title("Show Title")
if metadata:
    print(f"Found cached metadata: {metadata}")

# List all cached titles
titles = cache.list_cached_titles()
print(f"Available titles: {titles}")
```

The metadata includes:

Basic Information:

- Show ID
- Title
- Overview in English (overview_en)
- Overview in Arabic (overview_ar)
- First air date
- Last air date
- Episode runtime (in minutes)
- Number of episodes
- Number of seasons
- Status (e.g., "Ended", "Returning Series")
- Type
- Homepage URL
- In production status
- Tagline
- Original language
- Popularity score
- Vote average and count

Images and Media:

- Backdrops (with metadata):
  - File path
  - Width and height
  - Aspect ratio
  - Vote average and count
  - Language
- Posters (with metadata):
  - File path
  - Width and height
  - Aspect ratio
  - Vote average and count
  - Language
- Videos (trailers, teasers):
  - Name
  - Key (for YouTube)
  - Site (e.g., YouTube)
  - Type (Trailer, Teaser, etc.)
  - Official status
  - Language

Credits:

- Director
- Full crew list with:
  - Name
  - Job
  - Department
  - Profile image
- Top 10 cast members with:
  - Actor name
  - Character name
  - Profile image
  - Order
  - Known for department

Seasons:

- Details for each season:
  - Air date
  - Episode count
  - Name
  - Overview
  - Poster path
  - Season number

Additional Data:

- Genres (full genre information)
- Networks
- Production companies
- Production countries
- Spoken languages
- Keywords/tags
- Content ratings by country
- Watch providers (streaming platforms)
- Similar shows (top 5)
- Recommendations (top 5)
- External IDs:
  - IMDB ID
  - TVDB ID
  - Facebook ID
  - Instagram ID
  - Twitter ID

[Rest of the README remains unchanged]
