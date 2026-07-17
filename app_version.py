"""Application release information."""

APP_VERSION = "1.0.9"

GITHUB_OWNER = "nghiaozon"
GITHUB_REPOSITORY = "nghianetflix"
GITHUB_RELEASE_API_URL = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPOSITORY}/releases/latest"
)

# Chỉ các tên này được coi là gói chương trình hợp lệ. Thứ tự là thứ tự ưu tiên.
# Tên có {version} được thay bằng version đã chuẩn hóa, ví dụ 1.0.7.
UPDATE_ASSET_NAMES = (
    "NetflixManager.exe",
    "NetflixManager-{version}.zip",
    "NetflixManager.zip",
    "NetflixManager-Setup.exe",
    "NetflixManager-Installer.exe",
)
