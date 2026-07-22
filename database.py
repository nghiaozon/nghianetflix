import sqlite3
from datetime import date, datetime
from runtime_paths import config_file, data_file
from expiry_status import (
    STATUS_ACTIVE,
    STATUS_EXPIRED,
    expiry_sort_key,
    get_status_from_expiry,
    local_today,
)

# Cấu hình Google Sheets
try:
    from dotenv import load_dotenv
    load_dotenv(config_file(".env"))
except ImportError:
    pass

DB_FILE = data_file("netflix_manager.db")

# Valid deletion timestamps are newest first.  NULL, blank, or malformed
# legacy values are intentionally placed after timestamped records, with id
# descending as the stable tie-breaker.
TRASH_ORDER_BY = """
    CASE WHEN datetime(deleted_at) IS NULL THEN 1 ELSE 0 END ASC,
    datetime(deleted_at) DESC,
    id DESC
"""

# Creation timestamps are preferred, but legacy rows can legitimately have no
# timestamp. Keep those rows usable and fall back to their insertion id.
ACCOUNT_EMAIL_ORDER_BY = """
    CASE WHEN datetime(created_at) IS NULL THEN 1 ELSE 0 END ASC,
    datetime(created_at) DESC,
    id DESC
"""

# Global variable cho Google Sheets Service
gs_service = None

def init_google_sheets():
    """Khởi tạo Google Sheets Service."""
    global gs_service
    try:
        from google_sheets_service import GoogleSheetsService
        gs_service = GoogleSheetsService()
        return gs_service.is_connected
    except ImportError:
        return False
    except Exception:
        return False

def get_connection():
    """Tạo kết nối tới cơ sở dữ liệu SQLite."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_deleted_at_column(cursor, table_name):
    """Add the soft-delete timestamp column to legacy tables when needed."""
    columns = {
        row[1] for row in cursor.execute(f"PRAGMA table_info({table_name})")
    }
    if "deleted_at" not in columns:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN deleted_at TIMESTAMP")


def _ensure_account_created_at_column(cursor):
    """Add and backfill account creation time without changing existing data."""
    columns = {
        row[1] for row in cursor.execute("PRAGMA table_info(tai_khoan)")
    }
    if "created_at" not in columns:
        # SQLite cannot add a column with CURRENT_TIMESTAMP as its default on a
        # populated table. New rows receive their timestamp explicitly in
        # add_account(), while old rows retain a safe id-based fallback.
        cursor.execute("ALTER TABLE tai_khoan ADD COLUMN created_at TIMESTAMP")
        columns.add("created_at")

    # Some installations may already expose a legacy creation-time column.
    # Preserve it in the common created_at field so all email queries use one
    # ordering rule. Values that cannot be parsed remain harmless: the query
    # below places them with other legacy rows and uses id DESC.
    legacy_columns = [
        column for column in ("created_time", "inserted_at") if column in columns
    ]
    if legacy_columns:
        timestamp_values = ", ".join(
            "COALESCE(STRFTIME('%Y-%m-%d %H:%M:%S', {0}), "
            "NULLIF(TRIM({0}), ''))".format(column)
            for column in legacy_columns
        )
        source_expression = (
            f"COALESCE({timestamp_values})"
            if len(legacy_columns) > 1 else timestamp_values
        )
        cursor.execute(f"""
            UPDATE tai_khoan
            SET created_at = {source_expression}
            WHERE created_at IS NULL OR TRIM(created_at) = ''
        """)


def init_db():
    """Khởi tạo cấu trúc cơ sở dữ liệu nếu chưa tồn tại."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Bảng 1: tai_khoan (Quản lý kho tài khoản đầu vào)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tai_khoan (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ma_don_hang VARCHAR,
        email VARCHAR UNIQUE NOT NULL,
        mat_khau VARCHAR NOT NULL,
        lien_ket VARCHAR,
        ghi_chu TEXT,
        thong_bao VARCHAR DEFAULT '0/1',
        ngay_het_han DATE NOT NULL,
        trang_thai VARCHAR DEFAULT 'Đang hoạt động',
        nguon VARCHAR DEFAULT 'Khách hàng',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        deleted_at TIMESTAMP
    )
    """)
    
    # Bảng 2: don_hang (Quản lý đơn hàng bán ra)
    # Thêm một cột da_xoa (0 hoặc 1) để hỗ trợ chức năng Thùng rác cho Đơn hàng
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS don_hang (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email_tai_khoan VARCHAR,
        nen_tang VARCHAR NOT NULL,
        ten_khach_hang VARCHAR,
        so_tien FLOAT,
        so_lan_thong_bao INTEGER DEFAULT 0,
        ghi_chu TEXT,
        ngay_mua DATE NOT NULL DEFAULT CURRENT_DATE,
        ngay_het_han DATE,
        ngay_tao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        da_xoa INTEGER DEFAULT 0,
        deleted_at TIMESTAMP,
        FOREIGN KEY (email_tai_khoan) REFERENCES tai_khoan(email)
    )
    """)

    # Migration for databases created before purchase dates were stored separately.
    _ensure_deleted_at_column(cursor, "tai_khoan")
    _ensure_account_created_at_column(cursor)
    _ensure_deleted_at_column(cursor, "don_hang")
    cursor.execute("PRAGMA table_info(don_hang)")
    order_columns = {row[1] for row in cursor.fetchall()}
    if "ngay_mua" not in order_columns:
        cursor.execute("ALTER TABLE don_hang ADD COLUMN ngay_mua DATE")
    if "created_at" not in order_columns:
        # SQLite cannot add a column with CURRENT_TIMESTAMP as its default on
        # an existing table. Add it without a default, then preserve the best
        # available legacy creation timestamp below.
        cursor.execute("ALTER TABLE don_hang ADD COLUMN created_at TIMESTAMP")
    cursor.execute("""
        UPDATE don_hang
        SET ngay_mua = COALESCE(NULLIF(DATE(ngay_tao), ''), DATE('now'))
        WHERE ngay_mua IS NULL OR TRIM(ngay_mua) = ''
    """)
    if "ngay_tao" in order_columns:
        cursor.execute("""
            UPDATE don_hang
            SET created_at = COALESCE(
                STRFTIME('%Y-%m-%d %H:%M:%S', ngay_tao),
                NULLIF(TRIM(ngay_tao), '')
            )
            WHERE created_at IS NULL OR TRIM(created_at) = ''
        """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_don_hang_created_at ON don_hang(created_at)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_tai_khoan_created_at "
        "ON tai_khoan(created_at DESC, id DESC)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_tai_khoan_trash_deleted_at "
        "ON tai_khoan(deleted_at DESC, id DESC)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_don_hang_trash_deleted_at "
        "ON don_hang(deleted_at DESC, id DESC)"
    )
    
    conn.commit()
    
    # Tự động chèn dữ liệu mẫu nếu bảng tài khoản trống rỗng
    cursor.execute("SELECT COUNT(*) FROM tai_khoan")
    if cursor.fetchone()[0] == 0:
        seed_mock_data(cursor)
        conn.commit()
        
    conn.close()

def seed_mock_data(cursor):
    """Gieo dữ liệu mẫu thực tế cho lần chạy đầu tiên."""
    from datetime import datetime, timedelta
    
    # Tạo các ngày hết hạn tương lai và quá khứ
    today = datetime.now()
    exp_active_1 = (today + timedelta(days=25)).strftime("%Y-%m-%d")
    exp_active_2 = (today + timedelta(days=15)).strftime("%Y-%m-%d")
    exp_active_3 = (today + timedelta(days=45)).strftime("%Y-%m-%d")
    exp_expired_1 = (today - timedelta(days=5)).strftime("%Y-%m-%d")
    
    accounts = [
        ("netflix.premium1@gmail.com", "Pass123!", exp_active_1, "https://netflix.com", "Gói 4K Ultra HD", "Đại lý A", "1/1", "Đang hoạt động", None),
        ("netflix.premium2@gmail.com", "S1234567", exp_active_2, "https://netflix.com", "Slot 1 - PIN 1111", "Đại lý A", "0/1", "Đã bán", "DH-0001"),
        ("disney.ultra@gmail.com", "DisneyPass9!", exp_active_3, "https://disneyplus.com", "Gói Gia đình 1 năm", "Tự làm", "1/1", "Đang hoạt động", None),
        ("disney.sold@gmail.com", "Dis123456", exp_active_1, "https://disneyplus.com", "Slot 2", "Tự làm", "0/1", "Đã bán", "DH-0002"),
        ("spotify.family@gmail.com", "SpotMusic99", exp_expired_1, "", "Gói 6 tháng", "Khách hàng", "0/1", "Hết hạn", None),
        ("youtube.premium@gmail.com", "YoutuPremium!", exp_active_2, "https://youtube.com", "Gói Cá nhân", "Đại lý B", "1/1", "Đã bán", "DH-0003"),
        ("appletv.trial@gmail.com", "ApplePass!", exp_expired_1, "", "Hết hạn sử dụng", "Khách hàng", "0/1", "Đang hoạt động", None),
    ]
    
    for email, pw, exp, link, note, src, notify, status, order_code in accounts:
        cursor.execute("""
        INSERT INTO tai_khoan (email, mat_khau, ngay_het_han, lien_ket, ghi_chu, nguon, thong_bao, trang_thai, ma_don_hang)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (email, pw, exp, link, note, src, notify, status, order_code))
        
    # Thêm các đơn hàng mẫu trải dài trong tháng hiện tại
    orders = [
        ("netflix.premium2@gmail.com", "Netflix", "Nguyễn Văn An", 130000, exp_active_2, "Bảo hành 1 đổi 1", 1, 3),
        ("disney.sold@gmail.com", "Disney+", "Trần Thị Bình", 95000, exp_active_1, "Khách quen", 0, 2),
        ("youtube.premium@gmail.com", "Youtube Premium", "Phạm Văn Cường", 55000, exp_active_2, "Tự gia hạn", 2, 0)
    ]
    
    for email, plat, cust, price, exp, note, notify_count, day_offset in orders:
        order_date = (today - timedelta(days=day_offset)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
        INSERT INTO don_hang (
            email_tai_khoan, nen_tang, ten_khach_hang, so_tien, ngay_mua,
            ngay_het_han, ghi_chu, so_lan_thong_bao, ngay_tao, created_at, da_xoa
        )
        VALUES (?, ?, ?, ?, DATE(?), ?, ?, ?, ?, ?, 0)
        """, (
            email, plat, cust, price, order_date, exp, note, notify_count,
            order_date, order_date,
        ))

# --- CÁC HÀM XỬ LÝ CHO BẢNG TÀI KHOẢN (tai_khoan) ---

def add_account(email, password, ngay_het_han, lien_ket="", ghi_chu="", nguon="Khách hàng", thong_bao="0/1"):
    """Thêm tài khoản mới."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO tai_khoan (
            email, mat_khau, ngay_het_han, lien_ket, ghi_chu, nguon,
            thong_bao, trang_thai, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            email, password, ngay_het_han, lien_ket, ghi_chu, nguon,
            thong_bao, get_status_from_expiry(ngay_het_han),
        ))
        conn.commit()
        return True, "Thêm tài khoản thành công!"
    except sqlite3.IntegrityError:
        return False, f"Email '{email}' đã tồn tại trong hệ thống!"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def update_account(acc_id, email, password, ngay_het_han, lien_ket="", ghi_chu="", nguon="Khách hàng", thong_bao="0/1", trang_thai="Đang hoạt động"):
    """Cập nhật thông tin tài khoản."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        UPDATE tai_khoan
        SET email = ?, mat_khau = ?, ngay_het_han = ?, lien_ket = ?, ghi_chu = ?, nguon = ?, thong_bao = ?, trang_thai = ?
        WHERE id = ?
        """, (
            email, password, ngay_het_han, lien_ket, ghi_chu, nguon,
            thong_bao,
            # Expiry status is derived; callers cannot accidentally preserve
            # a stale "Đang hoạt động" value when editing on expiry day.
            get_status_from_expiry(ngay_het_han),
            acc_id,
        ))
        conn.commit()
        return True, "Cập nhật tài khoản thành công!"
    except sqlite3.IntegrityError:
        return False, f"Email '{email}' đã được sử dụng bởi tài khoản khác!"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def sync_account_status_by_expire_date():
    """Cập nhật trạng thái tài khoản tự động dựa trên ngày hết hạn."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Do not compare SQLite text values.  The shared parser also accepts
        # legacy dd/MM/yyyy data and sends invalid values to a safe state.
        today = local_today()
        rows = cursor.execute(
            "SELECT id, ngay_het_han FROM tai_khoan WHERE trang_thai != 'Đã xóa'"
        ).fetchall()
        cursor.executemany(
            "UPDATE tai_khoan SET trang_thai = ? WHERE id = ?",
            [
                (get_status_from_expiry(row["ngay_het_han"], today=today), row["id"])
                for row in rows
            ],
        )
        conn.commit()
    except Exception as e:
        print(f"Lỗi cập nhật trạng thái tài khoản tự động: {e}")
    finally:
        conn.close()


def delete_account_soft(acc_id):
    """Xóa mềm tài khoản (chuyển trạng thái sang 'Đã xóa' để đưa vào Thùng rác)."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        _ensure_deleted_at_column(cursor, "tai_khoan")
        cursor.execute("""
        UPDATE tai_khoan
        SET trang_thai = 'Đã xóa', deleted_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """, (acc_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Lỗi xóa tài khoản: {e}")
        return False
    finally:
        conn.close()


def delete_accounts_soft_bulk(account_ids):
    """Move multiple accounts to trash in one transaction."""
    account_ids = sorted(set(account_ids))
    if not account_ids:
        return True
    conn = get_connection()
    cursor = conn.cursor()
    try:
        _ensure_deleted_at_column(cursor, "tai_khoan")
        placeholders = ",".join("?" for _ in account_ids)
        cursor.execute(
            f"UPDATE tai_khoan SET trang_thai = 'Đã xóa', "
            f"deleted_at = CURRENT_TIMESTAMP WHERE id IN ({placeholders})",
            account_ids,
        )
        conn.commit()
        return True
    except Exception as exc:
        conn.rollback()
        print(f"Bulk account delete failed: {exc}")
        return False
    finally:
        conn.close()

def delete_account_permanently(acc_id):
    """Xóa vĩnh viễn tài khoản khỏi cơ sở dữ liệu."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM tai_khoan WHERE id = ?", (acc_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Lỗi xóa vĩnh viễn tài khoản: {e}")
        return False
    finally:
        conn.close()

def restore_account(acc_id):
    """Khôi phục tài khoản từ trạng thái 'Đã xóa' về 'Đang hoạt động' hoặc 'Đã bán' tùy thuộc vào mã đơn hàng."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        _ensure_deleted_at_column(cursor, "tai_khoan")
        # Kiểm tra xem tài khoản đã từng có mã đơn hàng hay chưa để khôi phục trạng thái phù hợp
        cursor.execute("SELECT ma_don_hang FROM tai_khoan WHERE id = ?", (acc_id,))
        row = cursor.fetchone()
        trang_thai = "Đang hoạt động"
        if row and row['ma_don_hang']:
            trang_thai = "Đã bán"
            
        cursor.execute("""
        UPDATE tai_khoan
        SET trang_thai = ?, deleted_at = NULL
        WHERE id = ?
        """, (trang_thai, acc_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"Lỗi khôi phục tài khoản: {e}")
        return False
    finally:
        conn.close()

def get_accounts(search_query="", filter_status="Tất cả"):
    """Lấy tài khoản đã lọc, sắp xếp theo ngày hết hạn tăng dần.

    Ngày được lưu ở dạng ISO ``YYYY-MM-DD`` nên ``DATE()`` của SQLite sắp
    xếp theo giá trị ngày, không theo chuỗi hiển thị ``dd/MM/yyyy``. Phép
    chuẩn hóa ``+0 days`` còn phát hiện ngày không có thật (ví dụ 30/02);
    mọi giá trị trống hoặc sai đều nằm cuối.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM tai_khoan WHERE trang_thai != 'Đã xóa'"
    params = []
    
    if search_query:
        query += " AND email LIKE ?"
        params.append(f"%{search_query}%")
        
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    today = local_today()
    accounts = [dict(row) for row in rows]
    for account in accounts:
        account['trang_thai'] = get_status_from_expiry(
            account.get('ngay_het_han'), today=today
        )
    if filter_status in (STATUS_ACTIVE, STATUS_EXPIRED):
        accounts = [a for a in accounts if a['trang_thai'] == filter_status]
    return sorted(accounts, key=lambda account: (expiry_sort_key(account.get('ngay_het_han')), account['id']))

def get_deleted_accounts():
    """Lấy danh sách tài khoản trong Thùng rác (trạng thái 'Đã xóa')."""
    conn = get_connection()
    cursor = conn.cursor()
    _ensure_deleted_at_column(cursor, "tai_khoan")
    conn.commit()
    cursor.execute(
        f"SELECT * FROM tai_khoan WHERE trang_thai = 'Đã xóa' "
        f"ORDER BY {TRASH_ORDER_BY}"
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_available_emails():
    """Lấy danh sách các email tài khoản chưa bán (Đang hoạt động)."""
    conn = get_connection()
    cursor = conn.cursor()
    _ensure_deleted_at_column(cursor, "tai_khoan")
    _ensure_account_created_at_column(cursor)
    conn.commit()
    cursor.execute(f"""
        SELECT email
        FROM tai_khoan
        WHERE trang_thai = 'Đang hoạt động'
          AND (deleted_at IS NULL OR TRIM(deleted_at) = '')
        ORDER BY {ACCOUNT_EMAIL_ORDER_BY}
    """)
    rows = cursor.fetchall()
    conn.close()
    return [row['email'] for row in rows]


def get_all_emails():
    """Return non-deleted accounts, newest-created first for order entry."""
    conn = get_connection()
    cursor = conn.cursor()
    _ensure_deleted_at_column(cursor, "tai_khoan")
    _ensure_account_created_at_column(cursor)
    conn.commit()
    cursor.execute(f"""
        SELECT email
        FROM tai_khoan
        WHERE trang_thai != 'Đã xóa'
          AND (deleted_at IS NULL OR TRIM(deleted_at) = '')
        ORDER BY {ACCOUNT_EMAIL_ORDER_BY}
    """)
    rows = cursor.fetchall()
    conn.close()
    return [row['email'] for row in rows]


def _unique_non_empty_values(query, value_key, formatter=str):
    """Return persisted autocomplete values, de-duplicated for display."""
    conn = get_connection()
    try:
        rows = conn.execute(query).fetchall()
    finally:
        conn.close()

    values = []
    seen = set()
    for row in rows:
        raw_value = row[value_key]
        if raw_value is None:
            continue
        value = formatter(raw_value).strip()
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            values.append(value)
    return sorted(values, key=str.casefold)


def get_account_source_suggestions():
    """Get sources from all non-deleted accounts for source autocomplete."""
    return _unique_non_empty_values(
        "SELECT nguon FROM tai_khoan "
        "WHERE trang_thai != 'Đã xóa' AND nguon IS NOT NULL",
        "nguon",
    )


def get_order_customer_suggestions():
    """Get customer names from all non-deleted orders for autocomplete."""
    return _unique_non_empty_values(
        "SELECT ten_khach_hang FROM don_hang "
        "WHERE da_xoa = 0 AND ten_khach_hang IS NOT NULL",
        "ten_khach_hang",
    )


def get_order_amount_suggestions():
    """Get amounts from all non-deleted orders using their input-friendly form."""
    def format_amount(value):
        number = float(value)
        return str(int(number)) if number.is_integer() else format(number, "g")

    return _unique_non_empty_values(
        "SELECT so_tien FROM don_hang WHERE da_xoa = 0 AND so_tien IS NOT NULL",
        "so_tien",
        format_amount,
    )


def get_active_order_count_for_email(email):
    """Trả về số lượng đơn hàng còn hiệu lực (không bị xóa) đang sử dụng email tài khoản này."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) AS cnt FROM don_hang WHERE da_xoa = 0 AND email_tai_khoan = ?", (email,))
    row = cursor.fetchone()
    conn.close()
    return row['cnt'] if row else 0


def get_active_order_counts_for_emails(emails):
    """Lấy số đơn còn hiệu lực theo email trong một truy vấn duy nhất."""
    unique_emails = sorted({email for email in emails if email})
    if not unique_emails:
        return {}

    placeholders = ", ".join("?" for _ in unique_emails)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT email_tai_khoan, COUNT(*) AS cnt
            FROM don_hang
            WHERE da_xoa = 0 AND email_tai_khoan IN ({placeholders})
            GROUP BY email_tai_khoan
            """,
            unique_emails,
        )
        return {row['email_tai_khoan']: row['cnt'] for row in cursor.fetchall()}
    finally:
        conn.close()


# --- CÁC HÀM XỬ LÝ CHO BẢNG ĐƠN HÀNG (don_hang) ---

def add_order(email_tai_khoan, nen_tang, ten_khach_hang, so_tien, ngay_mua, ngay_het_han, ghi_chu=""):
    """Thêm đơn hàng mới và tự động cập nhật mã đơn hàng cho tài khoản tương ứng."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # 1. Thêm đơn hàng mới
        cursor.execute("""
        INSERT INTO don_hang (
            email_tai_khoan, nen_tang, ten_khach_hang, so_tien, ngay_mua,
            ngay_het_han, ghi_chu, so_lan_thong_bao, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
        """, (
            email_tai_khoan, nen_tang, ten_khach_hang, so_tien, ngay_mua,
            ngay_het_han, ghi_chu, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ))
        order_id = cursor.lastrowid
        ma_don_hang = f"DH-{order_id:04d}"
        
        # 2. Cập nhật mã đơn hàng và trạng thái 'Đã bán' cho tài khoản tương ứng
        cursor.execute("""
        UPDATE tai_khoan
        SET ma_don_hang = ?, trang_thai = 'Đã bán'
        WHERE email = ?
        """, (ma_don_hang, email_tai_khoan))
        
        conn.commit()
        return True, "Thêm đơn hàng thành công!"
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()

def update_order(order_id, email_tai_khoan, nen_tang, ten_khach_hang, so_tien, ngay_mua, ngay_het_han, ghi_chu="", so_lan_thong_bao=0):
    """Cập nhật thông tin đơn hàng và đồng bộ liên kết tài khoản nếu có thay đổi."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Lấy thông tin tài khoản cũ liên kết với đơn hàng này
        cursor.execute("SELECT email_tai_khoan FROM don_hang WHERE id = ?", (order_id,))
        old_row = cursor.fetchone()
        old_email = old_row['email_tai_khoan'] if old_row else None
        
        # Cập nhật đơn hàng
        cursor.execute("""
        UPDATE don_hang
        SET email_tai_khoan = ?, nen_tang = ?, ten_khach_hang = ?, so_tien = ?, ngay_mua = ?, ngay_het_han = ?, ghi_chu = ?, so_lan_thong_bao = ?
        WHERE id = ?
        """, (email_tai_khoan, nen_tang, ten_khach_hang, so_tien, ngay_mua, ngay_het_han, ghi_chu, so_lan_thong_bao, order_id))
        
        ma_don_hang = f"DH-{order_id:04d}"
        
        # Nếu email tài khoản thay đổi
        if old_email != email_tai_khoan:
            # Giải phóng tài khoản cũ (nếu có)
            if old_email:
                cursor.execute("""
                UPDATE tai_khoan
                SET ma_don_hang = NULL, trang_thai = 'Đang hoạt động'
                WHERE email = ? AND ma_don_hang = ?
                """, (old_email, ma_don_hang))
            
            # Gán tài khoản mới
            if email_tai_khoan:
                cursor.execute("""
                UPDATE tai_khoan
                SET ma_don_hang = ?, trang_thai = 'Đã bán'
                WHERE email = ?
                """, (ma_don_hang, email_tai_khoan))
                
        conn.commit()
        return True, "Cập nhật đơn hàng thành công!"
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()

def delete_order_soft(order_id):
    """Xóa mềm đơn hàng (đưa vào Thùng rác) và giải phóng tài khoản liên kết."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        _ensure_deleted_at_column(cursor, "don_hang")
        # Tìm email tài khoản liên kết
        cursor.execute("SELECT email_tai_khoan FROM don_hang WHERE id = ?", (order_id,))
        row = cursor.fetchone()
        
        # Đánh dấu xóa đơn hàng
        cursor.execute(
            "UPDATE don_hang SET da_xoa = 1, deleted_at = CURRENT_TIMESTAMP "
            "WHERE id = ?",
            (order_id,),
        )
        
        # Giải phóng tài khoản tương ứng
        if row and row['email_tai_khoan']:
            ma_don_hang = f"DH-{order_id:04d}"
            cursor.execute("""
            UPDATE tai_khoan
            SET ma_don_hang = NULL, trang_thai = 'Đang hoạt động'
            WHERE email = ? AND ma_don_hang = ?
            """, (row['email_tai_khoan'], ma_don_hang))
            
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Lỗi xóa đơn hàng: {e}")
        return False
    finally:
        conn.close()


def delete_orders_soft_bulk(order_ids):
    """Move orders to trash and release linked accounts in one transaction."""
    order_ids = sorted(set(order_ids))
    if not order_ids:
        return True
    conn = get_connection()
    cursor = conn.cursor()
    try:
        _ensure_deleted_at_column(cursor, "don_hang")
        placeholders = ",".join("?" for _ in order_ids)
        cursor.execute(
            f"SELECT id, email_tai_khoan FROM don_hang "
            f"WHERE da_xoa = 0 AND id IN ({placeholders})",
            order_ids,
        )
        linked_accounts = cursor.fetchall()
        cursor.execute(
            f"UPDATE don_hang SET da_xoa = 1, "
            f"deleted_at = CURRENT_TIMESTAMP WHERE id IN ({placeholders})",
            order_ids,
        )
        for row in linked_accounts:
            email = row['email_tai_khoan']
            if email:
                order_code = f"DH-{row['id']:04d}"
                cursor.execute(
                    """
                    UPDATE tai_khoan
                    SET ma_don_hang = NULL, trang_thai = 'Đang hoạt động'
                    WHERE email = ? AND ma_don_hang = ?
                    """,
                    (email, order_code),
                )
        conn.commit()
        return True
    except Exception as exc:
        conn.rollback()
        print(f"Bulk order delete failed: {exc}")
        return False
    finally:
        conn.close()

def delete_order_permanently(order_id):
    """Xóa vĩnh viễn đơn hàng khỏi cơ sở dữ liệu."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM don_hang WHERE id = ?", (order_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Lỗi xóa vĩnh viễn đơn hàng: {e}")
        return False
    finally:
        conn.close()

def restore_order(order_id):
    """Khôi phục đơn hàng từ Thùng rác và liên kết lại tài khoản nếu tài khoản đó chưa bị bán cho đơn hàng khác."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        _ensure_deleted_at_column(cursor, "don_hang")
        cursor.execute("SELECT email_tai_khoan FROM don_hang WHERE id = ?", (order_id,))
        row = cursor.fetchone()
        email = row['email_tai_khoan'] if row else None
        ma_don_hang = f"DH-{order_id:04d}"
        
        # Khôi phục đơn hàng
        cursor.execute(
            "UPDATE don_hang SET da_xoa = 0, deleted_at = NULL WHERE id = ?",
            (order_id,),
        )
        
        # Nếu có tài khoản liên kết và tài khoản này đang rảnh (hoặc đã bị xóa mềm nhưng khôi phục được)
        if email:
            # Kiểm tra trạng thái tài khoản
            cursor.execute("SELECT trang_thai, ma_don_hang FROM tai_khoan WHERE email = ?", (email,))
            acc_row = cursor.fetchone()
            if acc_row:
                # Nếu tài khoản đang hoạt động hoặc không có liên kết mã đơn hàng nào khác
                if acc_row['trang_thai'] == 'Đang hoạt động' or not acc_row['ma_don_hang']:
                    cursor.execute("""
                    UPDATE tai_khoan
                    SET ma_don_hang = ?, trang_thai = 'Đã bán'
                    WHERE email = ?
                    """, (ma_don_hang, email))
                    
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Lỗi khôi phục đơn hàng: {e}")
        return False
    finally:
        conn.close()

def get_orders(search_query="", status_filter="Tất cả"):
    """Lấy đơn hàng sau khi tìm kiếm/lọc rồi sắp xếp.

    Các nhánh trạng thái giữ nguyên thứ tự ngày hết hạn. Nhánh ``Đơn hàng
    gần đây`` dùng timestamp tạo bản ghi, với ``id`` làm fallback cho dữ liệu
    cũ không có timestamp hợp lệ.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM don_hang WHERE da_xoa = 0"
    params = []
    
    if search_query:
        query += " AND (email_tai_khoan LIKE ? OR ten_khach_hang LIKE ? OR nen_tang LIKE ? OR id LIKE ?)"
        # Hỗ trợ tìm kiếm theo ID, email, nền tảng hoặc tên khách hàng.
        clean_id = search_query.lower().replace("dh-", "")
        try:
            val_id = int(clean_id)
        except ValueError:
            val_id = -1
        params.extend([
            f"%{search_query}%", f"%{search_query}%", f"%{search_query}%", val_id
        ])
        
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    today = local_today()
    orders = [dict(row) for row in rows]
    for order in orders:
        order['trang_thai'] = get_status_from_expiry(
            order.get('ngay_het_han'), today=today
        )
    if status_filter in (STATUS_ACTIVE, STATUS_EXPIRED):
        orders = [order for order in orders if order['trang_thai'] == status_filter]
    if status_filter == "Đơn hàng gần đây":
        def recent_sort_key(order):
            raw_created_at = order.get('created_at')
            try:
                return (0, -datetime.fromisoformat(raw_created_at).timestamp(), -order['id'])
            except (TypeError, ValueError):
                # Invalid/absent legacy timestamps follow valid values, using
                # id DESC as a stable fallback.
                return (1, 0, -order['id'])

        return sorted(
            orders,
            key=recent_sort_key,
        )
    return sorted(orders, key=lambda order: (expiry_sort_key(order.get('ngay_het_han')), order['id']))

def get_deleted_orders():
    """Lấy danh sách đơn hàng đã xóa mềm (trong Thùng rác)."""
    conn = get_connection()
    cursor = conn.cursor()
    _ensure_deleted_at_column(cursor, "don_hang")
    conn.commit()
    cursor.execute(
        f"SELECT * FROM don_hang WHERE da_xoa = 1 ORDER BY {TRASH_ORDER_BY}"
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_platforms():
    """Lấy danh sách nền tảng độc nhất để làm bộ lọc."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT nen_tang FROM don_hang WHERE da_xoa = 0 ORDER BY nen_tang ASC")
    rows = cursor.fetchall()
    conn.close()
    return [row['nen_tang'] for row in rows if row['nen_tang']]


# --- CÁC HÀM THỐNG KÊ (DASHBOARD ANALYTICS) ---

def build_month_options():
    """Return every calendar month for the dashboard month picker."""
    return list(range(1, 13))


def build_year_options(current_date=None, years_before=2, years_after=1):
    """Return practical dashboard years, newest first.

    The range around the local year keeps the picker useful for future and
    prior periods without being unbounded. Years that exist in order history
    are always retained, including soft-deleted orders.
    """
    current_date = current_date or date.today()
    if isinstance(current_date, datetime):
        current_date = current_date.date()

    years = set(
        range(current_date.year - years_before, current_date.year + years_after + 1)
    )
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT ngay_mua FROM don_hang")
        for row in cursor.fetchall():
            raw_date = row["ngay_mua"]
            if raw_date is None:
                continue
            try:
                years.add(date.fromisoformat(str(raw_date)[:10]).year)
            except ValueError:
                # Legacy invalid dates must not prevent the picker rendering.
                continue
    finally:
        conn.close()

    return sorted(years, reverse=True)


def build_available_months(current_date=None, months_before=12, months_after=12):
    """Return chart periods as ``(year, month)`` tuples, newest first.

    The picker includes a continuous 12-month range before and after the local
    month, so users can inspect past and future periods even without orders.
    Existing order months outside that range are included too.  This is
    deliberately not filtered by ``da_xoa`` because soft-deleted orders remain
    part of dashboard analytics until they are permanently deleted.

    ``current_date`` is injectable so the rollover behavior can be tested
    without changing the operating system clock.
    """
    current_date = current_date or date.today()
    if isinstance(current_date, datetime):
        current_date = current_date.date()

    current_month_index = current_date.year * 12 + current_date.month - 1
    available_months = set()
    for offset in range(-months_before, months_after + 1):
        year, zero_based_month = divmod(current_month_index + offset, 12)
        available_months.add((year, zero_based_month + 1))
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT ngay_mua FROM don_hang")
        for row in cursor.fetchall():
            raw_date = row["ngay_mua"]
            if raw_date is None:
                continue
            try:
                purchase_date = date.fromisoformat(str(raw_date)[:10])
            except ValueError:
                # Keep legacy malformed dates from breaking the Dashboard.
                continue
            available_months.add((purchase_date.year, purchase_date.month))
    finally:
        conn.close()

    return sorted(available_months, reverse=True)

def get_dashboard_stats(year=None, month=None):
    """
    Dashboard là lịch sử nghiệp vụ: đơn xóa mềm trong Thùng rác vẫn được
    tính; chỉ DELETE vĩnh viễn mới làm bản ghi biến mất khỏi thống kê.

    Tính toán các số liệu thống kê cho Dashboard:
    1. Tổng số đơn hàng, bao gồm đơn trong Thùng rác
    2. Đơn hàng còn bảo hành, bao gồm đơn trong Thùng rác
    3. Tổng doanh thu của tất cả bản ghi đơn hàng còn tồn tại
    4. Doanh thu tháng hiện tại
    """
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now()
    has_selected_period = year is not None and month is not None
    selected_year = int(year or now.year)
    selected_month = int(month or now.month)
    month_prefix = f"{selected_year:04d}-{selected_month:02d}-%"
    period_clause = " WHERE ngay_mua LIKE ?" if has_selected_period else ""
    period_params = (month_prefix,) if has_selected_period else ()
    
    # 1. Tổng đơn hàng
    # Dashboard is historical: records in the trash remain included. Only a
    # permanent DELETE removes an order from these aggregates.
    cursor.execute("SELECT COUNT(*) FROM don_hang" + period_clause, period_params)
    total_orders = cursor.fetchone()[0] or 0
    
    # 2. Đơn hàng còn bảo hành
    cursor.execute("SELECT ngay_het_han FROM don_hang" + period_clause, period_params)
    today = local_today()
    active_warranty = sum(
        get_status_from_expiry(row['ngay_het_han'], today=today) == STATUS_ACTIVE
        for row in cursor.fetchall()
    )
    
    # 3. Tổng doanh thu
    cursor.execute("SELECT SUM(so_tien) FROM don_hang" + period_clause, period_params)
    total_revenue = cursor.fetchone()[0] or 0.0
    
    # 4. Doanh thu tháng
    cursor.execute("SELECT SUM(so_tien) FROM don_hang WHERE ngay_mua LIKE ?", (month_prefix,))
    month_revenue = cursor.fetchone()[0] or 0.0
    
    conn.close()
    return {
        "total_orders": total_orders,
        "active_warranty": active_warranty,
        "total_revenue": total_revenue,
        "month_revenue": month_revenue
    }

def get_chart_data(year=None, month=None):
    """
    Lấy dữ liệu vẽ biểu đồ trong tháng hiện tại:
    Doanh thu (VND) và Số đơn hàng theo từng ngày từ 1 tới cuối tháng.
    Trả về: danh sách các ngày (X), danh sách doanh thu tương ứng (Y1), danh sách số đơn tương ứng (Y2)
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    import calendar
    now = datetime.now()
    year = int(year or now.year)
    month = int(month or now.month)
    
    # Số ngày trong tháng này
    _, num_days = calendar.monthrange(year, month)
    
    days = list(range(1, num_days + 1))
    revenue_by_day = {d: 0.0 for d in days}
    orders_by_day = {d: 0 for d in days}
    
    # Query dữ liệu đơn hàng trong tháng này
    month_prefix = f"{year:04d}-{month:02d}-%"
    cursor.execute("""
        SELECT strftime('%d', ngay_mua) as day, SUM(so_tien) as total_rev, COUNT(*) as num_ord
        FROM don_hang
        -- Soft-deleted orders remain part of the business history.
        WHERE ngay_mua LIKE ?
        GROUP BY day
    """, (month_prefix,))
    
    rows = cursor.fetchall()
    for row in rows:
        try:
            day_num = int(row['day'])
            if day_num in revenue_by_day:
                revenue_by_day[day_num] = float(row['total_rev'] or 0.0)
                orders_by_day[day_num] = int(row['num_ord'] or 0)
        except (ValueError, TypeError):
            continue
            
    conn.close()
    
    return {
        "days": days,
        "revenue": [revenue_by_day[d] for d in days],
        "orders": [orders_by_day[d] for d in days],
        "month_name": f"{month:02d}/{year}"
    }


def get_chart_data_current_month():
    """Tương thích với các phần cũ: trả dữ liệu của tháng hiện tại."""
    return get_chart_data()


# ==========================================
# GOOGLE SHEETS SYNC FUNCTIONS
# ==========================================

def sync_accounts_to_sheets() -> tuple:
    """Đồng bộ toàn bộ danh sách tài khoản lên Google Sheets."""
    if not gs_service:
        return False, "Google Sheets chưa được khởi tạo"
    
    try:
        # Lấy toàn bộ tài khoản từ DB
        accounts = get_accounts("", "Tất cả")
        # Sync lên Google Sheets
        success, msg = gs_service.sync_accounts(accounts)
        return success, msg
    except Exception as e:
        return False, f"Lỗi sync tài khoản: {str(e)}"


def sync_orders_to_sheets() -> tuple:
    """Đồng bộ toàn bộ danh sách đơn hàng lên Google Sheets."""
    if not gs_service:
        return False, "Google Sheets chưa được khởi tạo"
    
    try:
        # Lấy toàn bộ đơn hàng từ DB
        orders = get_orders("", "Tất cả")
        
        # Sync lên Google Sheets
        success, msg = gs_service.sync_orders(orders)
        return success, msg
    except Exception as e:
        return False, f"Lỗi sync đơn hàng: {str(e)}"


def sync_all_to_sheets() -> tuple:
    """Đồng bộ toàn bộ dữ liệu (tài khoản + đơn hàng) lên Google Sheets."""
    if not gs_service:
        return False, "Google Sheets chưa được khởi tạo"
    
    try:
        accounts = get_accounts("", "Tất cả")
        orders = get_orders("", "Tất cả")
        
        success, msg = gs_service.sync_all(accounts, orders)
        return success, msg
    except Exception as e:
        return False, f"Lỗi sync dữ liệu: {str(e)}"


def get_sync_status() -> dict:
    """Lấy trạng thái đồng bộ Google Sheets hiện tại."""
    if not gs_service:
        return {
            'status': 'Chưa kết nối Google Sheets',
            'connected': False,
            'last_sync': 'Không'
        }
    
    return gs_service.get_sync_status()


# Gọi khởi tạo DB và Google Sheets khi import
init_db()
init_google_sheets()
