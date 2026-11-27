import re


_YOUTUBE_PATTERNS = (
    r'(?:youtube\.com/watch\?v=|youtube\.com/embed/|youtube\.com/shorts/|youtu\.be/)([\w-]{11})',
)


def youtube_embed_url(url):
    """Return a privacy-enhanced embed URL, or an empty string for anything else."""
    if not url:
        return ''
    match = re.search(_YOUTUBE_PATTERNS[0], url)
    if not match:
        return ''
    video_id = match.group(1)
    return f'https://www.youtube-nocookie.com/embed/{video_id}'
