import sqlite3
from datetime import datetime
from runtime_paths import config_file, data_file

# Cấu hình Google Sheets
try:
    from dotenv import load_dotenv
    load_dotenv(config_file(".env"))
except ImportError:
    pass

DB_FILE = data_file("netflix_manager.db")

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
        nguon VARCHAR DEFAULT 'Khách hàng'
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
        da_xoa INTEGER DEFAULT 0,
        FOREIGN KEY (email_tai_khoan) REFERENCES tai_khoan(email)
    )
    """)

    # Migration for databases created before purchase dates were stored separately.
    cursor.execute("PRAGMA table_info(don_hang)")
    order_columns = {row[1] for row in cursor.fetchall()}
    if "ngay_mua" not in order_columns:
        cursor.execute("ALTER TABLE don_hang ADD COLUMN ngay_mua DATE")
    cursor.execute("""
        UPDATE don_hang
        SET ngay_mua = COALESCE(NULLIF(DATE(ngay_tao), ''), DATE('now'))
        WHERE ngay_mua IS NULL OR TRIM(ngay_mua) = ''
    """)
    
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
        INSERT INTO don_hang (email_tai_khoan, nen_tang, ten_khach_hang, so_tien, ngay_mua, ngay_het_han, ghi_chu, so_lan_thong_bao, ngay_tao, da_xoa)
        VALUES (?, ?, ?, ?, DATE(?), ?, ?, ?, ?, 0)
        """, (email, plat, cust, price, order_date, exp, note, notify_count, order_date))

# --- CÁC HÀM XỬ LÝ CHO BẢNG TÀI KHOẢN (tai_khoan) ---

def add_account(email, password, ngay_het_han, lien_ket="", ghi_chu="", nguon="Khách hàng", thong_bao="0/1"):
    """Thêm tài khoản mới."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO tai_khoan (email, mat_khau, ngay_het_han, lien_ket, ghi_chu, nguon, thong_bao, trang_thai)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'Đang hoạt động')
        """, (email, password, ngay_het_han, lien_ket, ghi_chu, nguon, thong_bao))
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
        """, (email, password, ngay_het_han, lien_ket, ghi_chu, nguon, thong_bao, trang_thai, acc_id))
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
    today_str = datetime.now().date().strftime("%Y-%m-%d")
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        UPDATE tai_khoan
        SET trang_thai = 'Đã hết hạn'
        WHERE trang_thai != 'Đã xóa'
          AND DATE(ngay_het_han) < DATE(?)
        """, (today_str,))
        cursor.execute("""
        UPDATE tai_khoan
        SET trang_thai = 'Đang hoạt động'
        WHERE trang_thai != 'Đã xóa'
          AND DATE(ngay_het_han) >= DATE(?)
        """, (today_str,))
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
        cursor.execute("""
        UPDATE tai_khoan
        SET trang_thai = 'Đã xóa'
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
        placeholders = ",".join("?" for _ in account_ids)
        cursor.execute(
            f"UPDATE tai_khoan SET trang_thai = 'Đã xóa' WHERE id IN ({placeholders})",
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
        # Kiểm tra xem tài khoản đã từng có mã đơn hàng hay chưa để khôi phục trạng thái phù hợp
        cursor.execute("SELECT ma_don_hang FROM tai_khoan WHERE id = ?", (acc_id,))
        row = cursor.fetchone()
        trang_thai = "Đang hoạt động"
        if row and row['ma_don_hang']:
            trang_thai = "Đã bán"
            
        cursor.execute("""
        UPDATE tai_khoan
        SET trang_thai = ?
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
        
    if filter_status and filter_status != "Tất cả" and filter_status != "Mặc định":
        query += " AND trang_thai = ?"
        params.append(filter_status)
        
    query += " ORDER BY CASE "
    query += "WHEN DATE(ngay_het_han, '+0 days') IS NULL "
    query += "OR DATE(ngay_het_han, '+0 days') != TRIM(ngay_het_han) THEN 1 ELSE 0 END, "
    query += "DATE(ngay_het_han, '+0 days') ASC, id ASC"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_deleted_accounts():
    """Lấy danh sách tài khoản trong Thùng rác (trạng thái 'Đã xóa')."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tai_khoan WHERE trang_thai = 'Đã xóa' ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_available_emails():
    """Lấy danh sách các email tài khoản chưa bán (Đang hoạt động)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM tai_khoan WHERE trang_thai = 'Đang hoạt động' ORDER BY email ASC")
    rows = cursor.fetchall()
    conn.close()
    return [row['email'] for row in rows]


def get_all_emails():
    """Lấy tất cả email tài khoản hiện có, trừ những tài khoản đã bị xóa mềm (trang_thai = 'Đã xóa')."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM tai_khoan WHERE trang_thai != 'Đã xóa' ORDER BY email ASC")
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


# --- CÁC HÀM XỬ LÝ CHO BẢNG ĐƠN HÀNG (don_hang) ---

def add_order(email_tai_khoan, nen_tang, ten_khach_hang, so_tien, ngay_mua, ngay_het_han, ghi_chu=""):
    """Thêm đơn hàng mới và tự động cập nhật mã đơn hàng cho tài khoản tương ứng."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # 1. Thêm đơn hàng mới
        cursor.execute("""
        INSERT INTO don_hang (email_tai_khoan, nen_tang, ten_khach_hang, so_tien, ngay_mua, ngay_het_han, ghi_chu, so_lan_thong_bao)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0)
        """, (email_tai_khoan, nen_tang, ten_khach_hang, so_tien, ngay_mua, ngay_het_han, ghi_chu))
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
        # Tìm email tài khoản liên kết
        cursor.execute("SELECT email_tai_khoan FROM don_hang WHERE id = ?", (order_id,))
        row = cursor.fetchone()
        
        # Đánh dấu xóa đơn hàng
        cursor.execute("UPDATE don_hang SET da_xoa = 1 WHERE id = ?", (order_id,))
        
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
        placeholders = ",".join("?" for _ in order_ids)
        cursor.execute(
            f"SELECT id, email_tai_khoan FROM don_hang "
            f"WHERE da_xoa = 0 AND id IN ({placeholders})",
            order_ids,
        )
        linked_accounts = cursor.fetchall()
        cursor.execute(
            f"UPDATE don_hang SET da_xoa = 1 WHERE id IN ({placeholders})",
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
        cursor.execute("SELECT email_tai_khoan FROM don_hang WHERE id = ?", (order_id,))
        row = cursor.fetchone()
        email = row['email_tai_khoan'] if row else None
        ma_don_hang = f"DH-{order_id:04d}"
        
        # Khôi phục đơn hàng
        cursor.execute("UPDATE don_hang SET da_xoa = 0 WHERE id = ?", (order_id,))
        
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
    """Lấy đơn hàng đã lọc, sắp xếp theo ngày hết hạn tăng dần.

    Mọi nhánh lọc dùng giá trị ngày ISO qua ``DATE()``; ngày trống/sai định
    dạng được đưa xuống cuối ở nhánh có thể chứa chúng.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM don_hang WHERE da_xoa = 0"
    params = []
    
    if search_query:
        query += " AND (email_tai_khoan LIKE ? OR ten_khach_hang LIKE ? OR id LIKE ?)"
        # Hỗ trợ tìm kiếm theo ID, Email hoặc Tên khách hàng
        clean_id = search_query.lower().replace("dh-", "")
        try:
            val_id = int(clean_id)
        except ValueError:
            val_id = -1
        params.extend([f"%{search_query}%", f"%{search_query}%", val_id])
        
    if status_filter == "Đơn hàng mới nhất":
        query += " AND DATE(ngay_het_han) >= DATE('now', 'localtime')"
    elif status_filter == "Đã hết hạn":
        query += " AND DATE(ngay_het_han) < DATE('now', 'localtime')"

    query += " ORDER BY CASE "
    query += "WHEN DATE(ngay_het_han, '+0 days') IS NULL "
    query += "OR DATE(ngay_het_han, '+0 days') != TRIM(ngay_het_han) THEN 1 ELSE 0 END, "
    query += "DATE(ngay_het_han, '+0 days') ASC, id ASC"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_deleted_orders():
    """Lấy danh sách đơn hàng đã xóa mềm (trong Thùng rác)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM don_hang WHERE da_xoa = 1 ORDER BY id DESC")
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

def get_dashboard_stats():
    """
    Tính toán các số liệu thống kê cho Dashboard:
    1. Tổng số đơn hàng (da_xoa = 0)
    2. Đơn hàng còn bảo hành (da_xoa = 0 và ngay_het_han >= hôm nay)
    3. Tổng doanh thu (tổng so_tien của các đơn da_xoa = 0)
    4. Doanh thu tháng hiện tại
    """
    conn = get_connection()
    cursor = conn.cursor()
    today_str = datetime.now().strftime("%Y-%m-%d")
    current_month_prefix = datetime.now().strftime("%Y-%m-") + "%"  # e.g. '2026-07-%'
    
    # 1. Tổng đơn hàng
    cursor.execute("SELECT COUNT(*) FROM don_hang WHERE da_xoa = 0")
    total_orders = cursor.fetchone()[0] or 0
    
    # 2. Đơn hàng còn bảo hành
    cursor.execute("SELECT COUNT(*) FROM don_hang WHERE da_xoa = 0 AND (ngay_het_han >= ? OR ngay_het_han IS NULL)", (today_str,))
    active_warranty = cursor.fetchone()[0] or 0
    
    # 3. Tổng doanh thu
    cursor.execute("SELECT SUM(so_tien) FROM don_hang WHERE da_xoa = 0")
    total_revenue = cursor.fetchone()[0] or 0.0
    
    # 4. Doanh thu tháng
    cursor.execute("SELECT SUM(so_tien) FROM don_hang WHERE da_xoa = 0 AND ngay_mua LIKE ?", (current_month_prefix,))
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
        WHERE da_xoa = 0 AND ngay_mua LIKE ?
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
