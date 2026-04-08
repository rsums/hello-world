# Substack Archive Extractor

Extract one or more Substack publications' posts and notes archive (with engagement data) to CSV. Each user gets a separate output folder with their own CSVs.

## Setup

```bash
pip install -r requirements.txt
```

## Authentication

This script requires a `connect.sid` session cookie from your Substack login:

1. Log into [substack.com](https://substack.com) in your browser
2. Open Developer Tools (`F12`) > **Application** > **Cookies** > `substack.com`
3. Copy the value of the `connect.sid` cookie

Pass it via `--cookie` flag or `SUBSTACK_SID` environment variable.

## Usage

```bash
# Extract a single user
python extract.py mattstoller --cookie "s%3A..."

# Extract multiple users at once (separate CSVs per user)
python extract.py mattstoller platformer slow-boring --cookie "s%3A..."

# Using environment variable
export SUBSTACK_SID="s%3A..."
python extract.py mattstoller platformer

# Posts only, no body content (metadata + engagement only)
python extract.py mattstoller --posts-only --no-content

# Notes only
python extract.py mattstoller --notes-only

# Custom output directory and request delay
python extract.py mattstoller platformer --output-dir ./my-archive --delay 2.0
```

## Output Structure

```
output/
  mattstoller/
    posts.csv
    notes.csv
  platformer/
    posts.csv
    notes.csv
```

## Options

| Flag | Description | Default |
|---|---|---|
| `subdomains` | One or more Substack subdomains | required |
| `--cookie` | `connect.sid` cookie value | `SUBSTACK_SID` env var |
| `--output-dir` | Base output directory (each subdomain gets a subfolder) | `./output/` |
| `--posts-only` | Skip notes extraction | off |
| `--notes-only` | Skip posts extraction | off |
| `--no-content` | Omit body content from CSV | off |
| `--delay` | Seconds between API requests | `1.0` |

## CSV Schemas

### `posts.csv`

| Column | Description |
|---|---|
| `id` | Substack internal post ID |
| `title` | Post title |
| `subtitle` | Post subtitle |
| `date` | Publication timestamp (ISO 8601) |
| `url` | Canonical URL to the post |
| `slug` | URL slug |
| `type` | Post type (newsletter, podcast, etc.) |
| `audience` | Visibility (everyone, only_paid, etc.) |
| `is_reply` | Whether this post is a reply to another |
| `parent_id` | ID of the parent post (if reply) |
| `parent_url` | URL of the parent post (if reply) |
| `like_count` | Number of likes |
| `comment_count` | Number of comments |
| `reaction_count` | Number of reactions |
| `word_count` | Word count of post body |
| `content_text` | Plain text content (omitted with `--no-content`) |
| `content_html` | Raw HTML content (omitted with `--no-content`) |

### `notes.csv`

| Column | Description |
|---|---|
| `id` | Note ID |
| `date` | Publication timestamp (ISO 8601) |
| `url` | URL to the note |
| `is_reply` | Whether this note is a reply |
| `is_restack` | Whether this note is a restack of another post/note |
| `parent_id` | ID of the parent note/post |
| `parent_url` | URL of the parent note/post |
| `like_count` | Number of likes |
| `comment_count` | Number of comments |
| `restack_count` | Number of restacks |
| `content_text` | Plain text content (omitted with `--no-content`) |

## Notes

- Rate limiting: the script defaults to 1 request/second. Increase `--delay` if you hit rate limits.
- The `connect.sid` cookie typically stays valid for months.
- Excel may truncate cells longer than 32,767 characters. Use `--no-content` for metadata-only exports.
- This uses Substack's unofficial API, which may change without notice.
- The notes API field names are less stable than posts. The script tries multiple known patterns and logs response keys for debugging.
