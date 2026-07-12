# -*- coding: utf-8 -*-
"""
Google Sheets Sync Service
Xử lý đồng bộ dữ liệu giữa SQLite Database và Google Sheets
"""

import os
from datetime import datetime
from typing import List, Dict, Tuple

from google.oauth2 import service_account
import gspread
from runtime_paths import config_file


class GoogleSheetsService:
    """Service xử lý kết nối và đồng bộ với Google Sheets."""
    
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
    
    # Tên sheets
    SHEET_ACCOUNTS = 'Accounts'
    SHEET_ORDERS = 'Orders'
    
    # Cột headers cho Accounts sheet
    ACCOUNTS_HEADERS = ['ID', 'Email', 'Mật khẩu', 'Ngày hết hạn', 'Ghi chú', 'Nguồn', 'Trạng thái', 'Cập nhật lần cuối']
    
    # Cột headers cho Orders sheet
    ORDERS_HEADERS = ['ID', 'Tài khoản Email', 'Nền tảng', 'Tên khách hàng', 'Số tiền', 'Ghi chú', 'Ngày mua', 'Ngày hết hạn', 'Trạng thái', 'Cập nhật lần cuối']
    
    def __init__(self, credentials_path: str = None, spreadsheet_id: str = None):
        """
        Khởi tạo Google Sheets Service.
        
        Args:
            credentials_path: Đường dẫn tới file credentials.json
            spreadsheet_id: ID của Google Sheets (lấy từ URL hoặc biến môi trường)
        """
        configured_path = credentials_path or os.getenv('GOOGLE_CREDENTIALS_PATH', 'credentials.json')
        if not os.path.isabs(configured_path):
            configured_path = config_file(configured_path)
        self.credentials_path = configured_path
        self.spreadsheet_id = spreadsheet_id or os.getenv('GOOGLE_SPREADSHEET_ID')
        self.client = None
        self.spreadsheet = None
        self.sync_status = "Chưa kết nối"
        self.last_sync = None
        self.is_connected = False
        
        # Thử kết nối
        self._initialize()
    
    def _initialize(self) -> bool:
        """Khởi tạo kết nối với Google Sheets."""
        try:
            if not os.path.exists(self.credentials_path):
                self.sync_status = f"Lỗi: Không tìm thấy file credentials ({self.credentials_path})"
                return False
            
            if not self.spreadsheet_id:
                self.sync_status = "Lỗi: Chưa cấu hình GOOGLE_SPREADSHEET_ID"
                return False
            
            # Tạo client từ service account credentials
            creds = service_account.Credentials.from_service_account_file(
                self.credentials_path, scopes=self.SCOPES
            )
            self.client = gspread.authorize(creds)
            
            # Mở spreadsheet
            self.spreadsheet = self.client.open_by_key(self.spreadsheet_id)
            
            self.is_connected = True
            self.sync_status = "Đã kết nối"
            self._ensure_sheets_exist()
            return True
            
        except FileNotFoundError:
            self.sync_status = f"Lỗi: Không tìm thấy file credentials"
            return False
        except Exception as e:
            self.sync_status = f"Lỗi kết nối: {str(e)}"
            return False
    
    def _ensure_sheets_exist(self) -> None:
        """Đảm bảo 2 sheets (Accounts, Orders) tồn tại."""
        try:
            existing_sheets = {ws.title for ws in self.spreadsheet.worksheets()}
            
            # Tạo Accounts sheet nếu chưa có
            if self.SHEET_ACCOUNTS not in existing_sheets:
                ws = self.spreadsheet.add_worksheet(self.SHEET_ACCOUNTS, rows=1000, cols=len(self.ACCOUNTS_HEADERS))
                ws.append_row(self.ACCOUNTS_HEADERS)
            
            # Tạo Orders sheet nếu chưa có
            if self.SHEET_ORDERS not in existing_sheets:
                ws = self.spreadsheet.add_worksheet(self.SHEET_ORDERS, rows=1000, cols=len(self.ORDERS_HEADERS))
                ws.append_row(self.ORDERS_HEADERS)
                
        except Exception as e:
            self.sync_status = f"Lỗi tạo sheets: {str(e)}"
    
    def sync_accounts(self, accounts: List[Dict]) -> Tuple[bool, str]:
        """
        Đồng bộ danh sách tài khoản lên Google Sheets.
        Xóa các dòng cũ và thêm lại toàn bộ dữ liệu mới.
        
        Args:
            accounts: Danh sách tài khoản từ database
            
        Returns:
            (success, message)
        """
        if not self.is_connected:
            return False, "Không kết nối Google Sheets"
        
        try:
            self.sync_status = "Đang đồng bộ tài khoản..."
            ws = self.spreadsheet.worksheet(self.SHEET_ACCOUNTS)
            
            # Xóa tất cả dòng trừ header
            if ws.row_count > 1:
                ws.delete_rows(2, ws.row_count)
            
            # Thêm dữ liệu mới
            rows_to_add = []
            for acc in accounts:
                row = [
                    acc.get('id', ''),
                    acc.get('email', ''),
                    acc.get('mat_khau', ''),
                    acc.get('ngay_het_han', ''),
                    acc.get('ghi_chu', ''),
                    acc.get('nguon', ''),
                    acc.get('trang_thai', 'Đang hoạt động'),
                    datetime.now().isoformat()
                ]
                rows_to_add.append(row)
            
            if rows_to_add:
                ws.append_rows(rows_to_add, value_input_option='USER_ENTERED')
            
            self.last_sync = datetime.now()
            self.sync_status = "Đã đồng bộ tài khoản"
            return True, "Tài khoản đã được đồng bộ thành công"
            
        except Exception as e:
            self.sync_status = f"Lỗi sync tài khoản: {str(e)}"
            return False, f"Lỗi: {str(e)}"
    
    def sync_orders(self, orders: List[Dict]) -> Tuple[bool, str]:
        """
        Đồng bộ danh sách đơn hàng lên Google Sheets.
        
        Args:
            orders: Danh sách đơn hàng từ database
            
        Returns:
            (success, message)
        """
        if not self.is_connected:
            return False, "Không kết nối Google Sheets"
        
        try:
            self.sync_status = "Đang đồng bộ đơn hàng..."
            ws = self.spreadsheet.worksheet(self.SHEET_ORDERS)

            # Keep existing spreadsheets compatible with the new purchase-date column.
            if ws.col_count < len(self.ORDERS_HEADERS):
                ws.add_cols(len(self.ORDERS_HEADERS) - ws.col_count)
            ws.update(range_name='A1:J1', values=[self.ORDERS_HEADERS])
            
            # Xóa tất cả dòng trừ header
            if ws.row_count > 1:
                ws.delete_rows(2, ws.row_count)
            
            # Thêm dữ liệu mới
            rows_to_add = []
            for order in orders:
                row = [
                    order.get('id', ''),
                    order.get('email_tai_khoan', ''),
                    order.get('nen_tang', ''),
                    order.get('ten_khach_hang', ''),
                    order.get('so_tien', ''),
                    order.get('ghi_chu', ''),
                    order.get('ngay_mua', ''),
                    order.get('ngay_het_han', ''),
                    self._calculate_order_status(order.get('ngay_het_han', '')),
                    datetime.now().isoformat()
                ]
                rows_to_add.append(row)
            
            if rows_to_add:
                ws.append_rows(rows_to_add, value_input_option='USER_ENTERED')
            
            self.last_sync = datetime.now()
            self.sync_status = "Đã đồng bộ đơn hàng"
            return True, "Đơn hàng đã được đồng bộ thành công"
            
        except Exception as e:
            self.sync_status = f"Lỗi sync đơn hàng: {str(e)}"
            return False, f"Lỗi: {str(e)}"
    
    def sync_all(self, accounts: List[Dict], orders: List[Dict]) -> Tuple[bool, str]:
        """
        Đồng bộ cả tài khoản và đơn hàng.
        
        Returns:
            (success, message)
        """
        acc_success, acc_msg = self.sync_accounts(accounts)
        order_success, order_msg = self.sync_orders(orders)
        
        if acc_success and order_success:
            self.sync_status = "Đã đồng bộ hoàn tất"
            return True, "Đã đồng bộ toàn bộ dữ liệu"
        else:
            msg = []
            if not acc_success:
                msg.append(acc_msg)
            if not order_success:
                msg.append(order_msg)
            return False, " | ".join(msg)
    
    def load_accounts_from_sheets(self) -> Tuple[bool, List[Dict]]:
        """
        Tải danh sách tài khoản từ Google Sheets về.
        
        Returns:
            (success, list_of_accounts)
        """
        if not self.is_connected:
            return False, []
        
        try:
            ws = self.spreadsheet.worksheet(self.SHEET_ACCOUNTS)
            records = ws.get_all_records()
            
            # Chuyển đổi format từ Google Sheets
            accounts = []
            for rec in records:
                accounts.append({
                    'id': int(rec.get('ID', 0)) if rec.get('ID', '').isdigit() else 0,
                    'email': rec.get('Email', ''),
                    'mat_khau': rec.get('Mật khẩu', ''),
                    'ngay_het_han': rec.get('Ngày hết hạn', ''),
                    'ghi_chu': rec.get('Ghi chú', ''),
                    'nguon': rec.get('Nguồn', ''),
                    'trang_thai': rec.get('Trạng thái', 'Đang hoạt động')
                })
            
            return True, accounts
            
        except Exception as e:
            self.sync_status = f"Lỗi tải tài khoản: {str(e)}"
            return False, []
    
    def load_orders_from_sheets(self) -> Tuple[bool, List[Dict]]:
        """
        Tải danh sách đơn hàng từ Google Sheets về.
        
        Returns:
            (success, list_of_orders)
        """
        if not self.is_connected:
            return False, []
        
        try:
            ws = self.spreadsheet.worksheet(self.SHEET_ORDERS)
            records = ws.get_all_records()
            
            # Chuyển đổi format từ Google Sheets
            orders = []
            for rec in records:
                orders.append({
                    'id': int(rec.get('ID', 0)) if rec.get('ID', '').isdigit() else 0,
                    'email_tai_khoan': rec.get('Tài khoản Email', ''),
                    'nen_tang': rec.get('Nền tảng', ''),
                    'ten_khach_hang': rec.get('Tên khách hàng', ''),
                    'so_tien': float(rec.get('Số tiền', 0)) if rec.get('Số tiền', '') else 0,
                    'ghi_chu': rec.get('Ghi chú', ''),
                    'ngay_mua': rec.get('Ngày mua', ''),
                    'ngay_het_han': rec.get('Ngày hết hạn', '')
                })
            
            return True, orders
            
        except Exception as e:
            self.sync_status = f"Lỗi tải đơn hàng: {str(e)}"
            return False, []
    
    def get_sync_status(self) -> Dict[str, str]:
        """Lấy trạng thái đồng bộ hiện tại."""
        return {
            'status': self.sync_status,
            'connected': self.is_connected,
            'last_sync': self.last_sync.isoformat() if self.last_sync else 'Chưa đồng bộ'
        }
    
    @staticmethod
    def _calculate_order_status(ngay_het_han: str) -> str:
        """Tính trạng thái đơn hàng từ ngày hết hạn."""
        try:
            from datetime import date
            expiry_date = date.fromisoformat(ngay_het_han)
            return "Đã hết hạn" if expiry_date < date.today() else "Đang hoạt động"
        except:
            return "—"
