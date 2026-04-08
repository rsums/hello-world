# Substack Archive Extractor

Extract a Substack publication's posts and notes archive (with engagement data) to CSV.

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
# Extract everything (posts + notes)
python extract.py mattstoller --cookie "s%3A..."

# Using environment variable
export SUBSTACK_SID="s%3A..."
python extract.py mattstoller

# Posts only, no body content (metadata + engagement only)
python extract.py mattstoller --posts-only --no-content

# Notes only
python extract.py mattstoller --notes-only

# Custom output directory and request delay
python extract.py mattstoller --output-dir ./my-archive --delay 2.0
```

## Options

| Flag | Description | Default |
|---|---|---|
| `subdomain` | Substack subdomain (e.g. `mattstoller`) | required |
| `--cookie` | `connect.sid` cookie value | `SUBSTACK_SID` env var |
| `--output-dir` | Output directory | `./output/<subdomain>/` |
| `--posts-only` | Skip notes extraction | off |
| `--notes-only` | Skip posts extraction | off |
| `--no-content` | Omit body content from CSV | off |
| `--delay` | Seconds between API requests | `1.0` |

## Output

### `posts.csv`

| Column | Description |
|---|---|
| `id` | Substack internal post ID |
| `title` | Post title |
| `subtitle` | Post subtitle |
| `date` | Publication date (ISO 8601) |
| `url` | Canonical URL |
| `slug` | URL slug |
| `type` | Post type (newsletter, podcast, etc.) |
| `audience` | Visibility (everyone, only_paid, etc.) |
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
| `date` | Publication date |
| `content_text` | Plain text content (omitted with `--no-content`) |
| `like_count` | Number of likes |
| `comment_count` | Number of comments |
| `restack_count` | Number of restacks |
| `url` | Note URL |

## Notes

- Rate limiting: the script defaults to 1 request/second. Increase `--delay` if you hit rate limits.
- The `connect.sid` cookie typically stays valid for months.
- Excel may truncate cells longer than 32,767 characters. Use `--no-content` for metadata-only exports.
- This uses Substack's unofficial API, which may change without notice.
