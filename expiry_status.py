"""Quy tắc duy nhất để xác định trạng thái theo ngày hết hạn.

Ngày hết hạn chỉ là một ngày lịch.  Vì vậy một bản ghi hết hạn vào ngày D
được xem là hết hạn ngay từ 00:00 theo giờ local của máy trong ngày D.
"""

import logging
from datetime import date, datetime
from typing import Optional, Union


LOGGER = logging.getLogger(__name__)

STATUS_ACTIVE = "Đang hoạt động"
STATUS_EXPIRED = "Đã hết hạn"
STATUS_UNKNOWN = "Không xác định"

DateValue = Union[date, datetime, str, None]


def local_today() -> date:
    """Trả về ngày local của máy người dùng, không dùng UTC."""
    return datetime.now().date()


def parse_expiry_date(value: DateValue) -> Optional[date]:
    """Parse ngày hết hạn an toàn từ dữ liệu DB/Sheets/UI.

    Dữ liệu mới của ứng dụng lưu ISO ``YYYY-MM-DD``; ``dd/MM/yyyy`` cũng
    được chấp nhận khi nhập hoặc đồng bộ từ Google Sheets.  Dữ liệu lỗi trả về
    ``None`` và được log cảnh báo thay vì làm hỏng màn hình.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        LOGGER.warning("Ngày hết hạn bị trống hoặc không hợp lệ: %r", value)
        return None

    raw_value = value.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw_value, fmt).date()
        except ValueError:
            pass

    LOGGER.warning("Không thể parse ngày hết hạn %r", value)
    return None


def is_expired(expiry_date_value: DateValue, *, today: Optional[date] = None) -> Optional[bool]:
    """Trả về ``today >= expiry_date`` hoặc ``None`` nếu ngày không hợp lệ."""
    expiry_date = parse_expiry_date(expiry_date_value)
    if expiry_date is None:
        return None
    current_day = today or local_today()
    if isinstance(current_day, datetime):
        current_day = current_day.date()
    return current_day >= expiry_date


def get_status_from_expiry(
    expiry_date_value: DateValue, *, today: Optional[date] = None
) -> str:
    """Tính trạng thái hiển thị từ ngày hết hạn bằng quy tắc chung."""
    expired = is_expired(expiry_date_value, today=today)
    if expired is None:
        return STATUS_UNKNOWN
    return STATUS_EXPIRED if expired else STATUS_ACTIVE


def expiry_sort_key(expiry_date_value: DateValue):
    """Sắp xếp ngày hợp lệ trước, dữ liệu trống/sai luôn ở cuối."""
    parsed = parse_expiry_date(expiry_date_value)
    return (parsed is None, parsed or date.max)
