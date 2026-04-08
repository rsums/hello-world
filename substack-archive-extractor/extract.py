#!/usr/bin/env python3
"""Extract a Substack user's posts and notes archive with engagement data."""

import argparse
import csv
import json
import os
import sys
import time
from html.parser import HTMLParser

import requests


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="Extract Substack publications' posts and notes to CSV.",
    )
    p.add_argument("subdomains", nargs="+", help="One or more Substack subdomains (e.g. 'mattstoller' 'platformer')")
    p.add_argument("--cookie", help="connect.sid cookie value (or set SUBSTACK_SID env var)")
    p.add_argument("--output-dir", help="Base output directory (default: ./output/; each subdomain gets its own subfolder)")
    p.add_argument("--posts-only", action="store_true", help="Skip notes extraction")
    p.add_argument("--notes-only", action="store_true", help="Skip posts extraction")
    p.add_argument("--no-content", action="store_true", help="Omit post/note body content from CSV")
    p.add_argument("--delay", type=float, default=1.0, help="Seconds between API requests (default: 1.0)")
    return p.parse_args()


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def get_session(cookie: str) -> requests.Session:
    s = requests.Session()
    s.cookies.set("connect.sid", cookie, domain=".substack.com")
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
    })
    return s


def api_get(session: requests.Session, url: str, params: dict | None = None,
            delay: float = 1.0, max_retries: int = 3) -> dict | list:
    for attempt in range(max_retries):
        try:
            resp = session.get(url, params=params, timeout=30)

            if resp.status_code in (401, 403) and attempt == 0:
                print(f"Authentication failed ({resp.status_code}). "
                      "Check your connect.sid cookie.", file=sys.stderr)
                sys.exit(1)

            if resp.status_code == 429:
                wait = delay * (2 ** (attempt + 1))
                print(f"Rate limited, waiting {wait:.0f}s...", file=sys.stderr)
                time.sleep(wait)
                continue

            resp.raise_for_status()
            time.sleep(delay)
            return resp.json()

        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                raise
            print(f"Request failed ({e}), retrying in {delay}s...", file=sys.stderr)
            time.sleep(delay)

    raise RuntimeError(f"Failed after {max_retries} attempts: {url}")


# ---------------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------------

POST_CSV_FIELDS = [
    "id", "title", "subtitle", "date", "url", "slug", "type", "audience",
    "is_reply", "parent_id", "parent_url",
    "like_count", "comment_count", "reaction_count", "word_count",
    "content_text", "content_html",
]

POST_CSV_FIELDS_NO_CONTENT = [
    "id", "title", "subtitle", "date", "url", "slug", "type", "audience",
    "is_reply", "parent_id", "parent_url",
    "like_count", "comment_count", "reaction_count", "word_count",
]


def fetch_posts(session: requests.Session, subdomain: str,
                delay: float) -> list[dict]:
    base = f"https://{subdomain}.substack.com/api/v1/archive"
    posts = []
    offset = 0
    limit = 25

    while True:
        print(f"Fetching posts... {len(posts)} collected (offset={offset})",
              file=sys.stderr)
        data = api_get(session, base, params={
            "sort": "new", "offset": offset, "limit": limit,
        }, delay=delay)

        if not data:
            break

        posts.extend(data)
        if len(data) < limit:
            break
        offset += limit

    print(f"Fetched {len(posts)} posts total.", file=sys.stderr)
    return posts


def fetch_post_content(session: requests.Session, subdomain: str,
                       slug: str, delay: float) -> str:
    url = f"https://{subdomain}.substack.com/api/v1/posts/{slug}"
    data = api_get(session, url, delay=delay)
    return data.get("body_html", "")


def extract_post_row(post: dict, include_content: bool = True,
                     session: requests.Session | None = None,
                     subdomain: str = "", delay: float = 1.0) -> dict:
    body_html = post.get("body_html", "") or ""

    # If archive didn't include body and we have a session, fetch individually
    if include_content and not body_html and session and subdomain:
        slug = post.get("slug", "")
        if slug:
            try:
                body_html = fetch_post_content(session, subdomain, slug, delay)
            except Exception as e:
                print(f"  Warning: couldn't fetch content for '{slug}': {e}",
                      file=sys.stderr)

    content_text = strip_html(body_html) if body_html else ""

    # Parent/reply detection - Substack uses various field names
    reply_to = (post.get("reply_to_post_id") or post.get("in_reply_to_id")
                or post.get("reply_to_id") or "")
    parent_canonical = post.get("reply_to_canonical_url", "") or ""
    # If reply_to exists but no canonical URL, try to construct one
    if reply_to and not parent_canonical:
        reply_slug = post.get("reply_to_slug", "")
        if reply_slug:
            pub = post.get("publishedBylines", [{}])
            pub_domain = pub[0].get("publication", {}).get("subdomain", "") if pub else ""
            if pub_domain:
                parent_canonical = f"https://{pub_domain}.substack.com/p/{reply_slug}"

    row = {
        "id": post.get("id", ""),
        "title": post.get("title", ""),
        "subtitle": post.get("subtitle", ""),
        "date": post.get("post_date", "") or post.get("publish_date", ""),
        "url": post.get("canonical_url", ""),
        "slug": post.get("slug", ""),
        "type": post.get("type", ""),
        "audience": post.get("audience", ""),
        "is_reply": bool(reply_to),
        "parent_id": reply_to,
        "parent_url": parent_canonical,
        "like_count": post.get("like_count", 0) or 0,
        "comment_count": post.get("comment_count", 0) or 0,
        "reaction_count": post.get("reaction_count", 0) or 0,
        "word_count": len(content_text.split()) if content_text else 0,
    }

    if include_content:
        row["content_text"] = content_text
        row["content_html"] = body_html

    return row


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------

NOTE_CSV_FIELDS = [
    "id", "date", "url",
    "is_reply", "is_restack", "parent_id", "parent_url",
    "like_count", "comment_count", "restack_count",
    "content_text",
]

NOTE_CSV_FIELDS_NO_CONTENT = [
    "id", "date", "url",
    "is_reply", "is_restack", "parent_id", "parent_url",
    "like_count", "comment_count", "restack_count",
]


def fetch_notes(session: requests.Session, subdomain: str,
                delay: float) -> list[dict]:
    """Fetch notes for a publication. Tries multiple known endpoint patterns."""
    notes = []

    # Strategy 1: /api/v1/reader/notes endpoint with publication filter
    # Strategy 2: /api/v1/notes on the subdomain
    endpoints = [
        f"https://{subdomain}.substack.com/api/v1/reader/notes",
        f"https://{subdomain}.substack.com/api/v1/notes",
    ]

    for endpoint in endpoints:
        print(f"Trying notes endpoint: {endpoint}", file=sys.stderr)
        try:
            notes = _fetch_notes_paginated(session, endpoint, delay)
            if notes:
                break
        except requests.exceptions.HTTPError as e:
            print(f"  Endpoint returned {e.response.status_code}, trying next...",
                  file=sys.stderr)
            continue
        except Exception as e:
            print(f"  Endpoint failed ({e}), trying next...", file=sys.stderr)
            continue

    if not notes:
        print("No notes found (the notes API may have changed, or this "
              "publication has no notes).", file=sys.stderr)

    return notes


def _fetch_notes_paginated(session: requests.Session, endpoint: str,
                           delay: float) -> list[dict]:
    notes = []
    params: dict = {}

    while True:
        print(f"Fetching notes... {len(notes)} collected", file=sys.stderr)
        data = api_get(session, endpoint, params=params, delay=delay)

        # Handle various response shapes
        if isinstance(data, list):
            items = data
            next_cursor = None
        elif isinstance(data, dict):
            # Try common field names for the notes array
            items = (data.get("notes") or data.get("items")
                     or data.get("results") or data.get("posts") or [])

            # Try common field names for pagination cursor
            paging = data.get("paging", {})
            next_cursor = (paging.get("next") or paging.get("cursor")
                           or data.get("next_cursor") or data.get("cursor"))

            # Log response keys on first call for debugging
            if not notes:
                print(f"  Response keys: {list(data.keys())}", file=sys.stderr)
                if paging:
                    print(f"  Paging keys: {list(paging.keys())}",
                          file=sys.stderr)
        else:
            break

        if not items:
            break

        notes.extend(items)

        if not next_cursor:
            break
        params["cursor"] = next_cursor

    print(f"Fetched {len(notes)} notes total.", file=sys.stderr)
    return notes


def extract_note_row(note: dict, include_content: bool = True) -> dict:
    body_json = note.get("body_json") or note.get("bodyJson")
    content_text = ""
    if body_json:
        if isinstance(body_json, str):
            try:
                body_json = json.loads(body_json)
            except json.JSONDecodeError:
                content_text = body_json
        if isinstance(body_json, dict):
            content_text = body_json_to_text(body_json)

    # Fall back to body or body_html
    if not content_text:
        content_text = strip_html(note.get("body_html", "") or
                                  note.get("body", "") or "")

    note_id = note.get("id", "")

    # Parent/reply detection for notes
    reply_to = (note.get("reply_to_post_id") or note.get("in_reply_to_id")
                or note.get("reply_to_id") or note.get("reply_comment_id") or "")
    restacked_id = (note.get("restacked_post_id") or note.get("restack_of_id")
                    or note.get("reposted_post_id") or "")

    parent_id = reply_to or restacked_id
    parent_url = (note.get("reply_to_canonical_url", "")
                  or note.get("restack_canonical_url", "")
                  or note.get("parent_canonical_url", "") or "")

    # Try to get parent URL from nested objects
    if not parent_url:
        parent_comment = note.get("reply_to_comment") or note.get("parent") or {}
        if isinstance(parent_comment, dict):
            parent_url = parent_comment.get("canonical_url", "") or ""
        restacked_post = note.get("restacked_post") or note.get("restack_of") or {}
        if not parent_url and isinstance(restacked_post, dict):
            parent_url = restacked_post.get("canonical_url", "") or ""

    row = {
        "id": note_id,
        "date": note.get("publish_date", "") or note.get("post_date", ""),
        "url": note.get("canonical_url", "") or "",
        "is_reply": bool(reply_to),
        "is_restack": bool(restacked_id),
        "parent_id": parent_id,
        "parent_url": parent_url,
        "like_count": note.get("like_count", 0) or 0,
        "comment_count": note.get("comment_count", 0) or 0,
        "restack_count": note.get("restack_count", 0) or 0,
    }

    if include_content:
        row["content_text"] = content_text

    return row


# ---------------------------------------------------------------------------
# Content parsing helpers
# ---------------------------------------------------------------------------

class _HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str):
        self._parts.append(data)

    def get_text(self) -> str:
        return "".join(self._parts)


def strip_html(html: str) -> str:
    if not html:
        return ""
    s = _HTMLStripper()
    s.feed(html)
    return s.get_text().strip()


def body_json_to_text(node: dict) -> str:
    """Recursively extract plain text from a ProseMirror/Tiptap document."""
    if not isinstance(node, dict):
        return ""

    node_type = node.get("type", "")

    # Text leaf node
    if node_type == "text":
        return node.get("text", "")

    # Recurse into children
    children = node.get("content", [])
    if not children:
        # Handle nodes like image, embed with no text content
        if node_type == "image":
            return "[image]"
        if node_type in ("embed", "attachment"):
            url = (node.get("attrs", {}).get("url", "")
                   or node.get("attrs", {}).get("src", ""))
            return f"[embed: {url}]" if url else "[embed]"
        return ""

    parts = [body_json_to_text(child) for child in children]

    # Block-level nodes get newlines between them
    block_types = {"doc", "paragraph", "heading", "blockquote",
                   "bulletList", "orderedList", "listItem",
                   "codeBlock", "horizontalRule"}
    if node_type in block_types:
        return "\n".join(p for p in parts if p)

    # Inline nodes get concatenated
    return "".join(parts)


# ---------------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------------

def write_csv(rows: list[dict], filepath: str, fieldnames: list[str]):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {filepath}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def extract_user(session: requests.Session, subdomain: str, out_dir: str,
                 include_content: bool, delay: float,
                 posts_only: bool, notes_only: bool):
    """Extract posts and/or notes for a single subdomain."""
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"Extracting: {subdomain}.substack.com", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    os.makedirs(out_dir, exist_ok=True)

    # --- Posts ---
    posts_rows = []
    if not notes_only:
        try:
            raw_posts = fetch_posts(session, subdomain, delay)

            # Check if archive includes body_html
            needs_individual_fetch = (
                include_content
                and raw_posts
                and not raw_posts[0].get("body_html")
            )
            if needs_individual_fetch:
                total = len(raw_posts)
                print(f"Archive doesn't include post content. "
                      f"Fetching {total} individual posts...", file=sys.stderr)

            for i, post in enumerate(raw_posts):
                if needs_individual_fetch:
                    print(f"  Fetching post content: {i+1}/{total}",
                          file=sys.stderr)
                posts_rows.append(extract_post_row(
                    post,
                    include_content=include_content,
                    session=session if needs_individual_fetch else None,
                    subdomain=subdomain,
                    delay=delay,
                ))
        except Exception as e:
            print(f"Error fetching posts for {subdomain}: {e}", file=sys.stderr)
            print(f"Writing {len(posts_rows)} posts collected before failure...",
                  file=sys.stderr)

        if posts_rows:
            fields = POST_CSV_FIELDS_NO_CONTENT if not include_content else POST_CSV_FIELDS
            write_csv(posts_rows, os.path.join(out_dir, "posts.csv"), fields)

    # --- Notes ---
    notes_rows = []
    if not posts_only:
        try:
            raw_notes = fetch_notes(session, subdomain, delay)
            for note in raw_notes:
                notes_rows.append(extract_note_row(
                    note, include_content=include_content))
        except Exception as e:
            print(f"Error fetching notes for {subdomain}: {e}", file=sys.stderr)
            print(f"Writing {len(notes_rows)} notes collected before failure...",
                  file=sys.stderr)

        if notes_rows:
            fields = NOTE_CSV_FIELDS_NO_CONTENT if not include_content else NOTE_CSV_FIELDS
            write_csv(notes_rows, os.path.join(out_dir, "notes.csv"), fields)

    # --- Summary for this user ---
    print(f"\nDone with {subdomain}! Output: {out_dir}", file=sys.stderr)
    if posts_rows:
        print(f"  Posts: {len(posts_rows)} entries -> posts.csv", file=sys.stderr)
    if notes_rows:
        print(f"  Notes: {len(notes_rows)} entries -> notes.csv", file=sys.stderr)
    if not posts_rows and not notes_rows:
        print("  No data extracted.", file=sys.stderr)

    return len(posts_rows), len(notes_rows)


def main():
    args = parse_args()

    # Resolve cookie
    cookie = args.cookie or os.environ.get("SUBSTACK_SID")
    if not cookie:
        print("Error: No connect.sid cookie provided.\n"
              "Use --cookie or set SUBSTACK_SID environment variable.\n\n"
              "To get your cookie:\n"
              "  1. Log into Substack in your browser\n"
              "  2. Open Developer Tools (F12) > Application > Cookies\n"
              "  3. Copy the 'connect.sid' value",
              file=sys.stderr)
        sys.exit(1)

    session = get_session(cookie)
    include_content = not args.no_content
    base_dir = args.output_dir or "output"

    results = {}
    for subdomain in args.subdomains:
        out_dir = os.path.join(base_dir, subdomain)
        posts_count, notes_count = extract_user(
            session, subdomain, out_dir, include_content,
            args.delay, args.posts_only, args.notes_only,
        )
        results[subdomain] = (posts_count, notes_count)

    # Final summary across all users
    if len(args.subdomains) > 1:
        print(f"\n{'='*60}", file=sys.stderr)
        print("Summary:", file=sys.stderr)
        for subdomain, (pc, nc) in results.items():
            print(f"  {subdomain}: {pc} posts, {nc} notes -> {base_dir}/{subdomain}/",
                  file=sys.stderr)


if __name__ == "__main__":
    main()
