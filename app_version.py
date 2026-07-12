"""Application release information."""

APP_VERSION = "1.0.3"

# The release script also uploads update.json as a release asset. New builds use
# this stable URL, while the repository copy remains available to older builds.
# It can also be overridden with NETFLIX_MANAGER_UPDATE_URL.
DEFAULT_UPDATE_MANIFEST_URL = (
    "https://github.com/nghiaozon/nghianetflix/releases/latest/download/update.json"
)
