# -*- coding: utf-8 -*-
"""
Hướng dẫn cấu hình Google Sheets Sync

Bước 1: Tạo Google Cloud Project
1. Truy cập https://console.cloud.google.com/
2. Tạo dự án mới: "Netflix Account Manager"
3. Kích hoạt Google Sheets API:
   - Vào "APIs & Services" > "Library"
   - Tìm "Google Sheets API"
   - Bấm "Enable"

Bước 2: Tạo Service Account
1. Trong "APIs & Services", chọn "Credentials"
2. Bấm "Create Credentials" > "Service Account"
3. Điền thông tin:
   - Service account name: "netflix-manager-sync"
   - Description: "Sync data to Google Sheets"
4. Bấm "Create and Continue"
5. Bỏ qua bước Optional (bấm "Continue")
6. Hoàn tất bấm "Done"

Bước 3: Tạo Private Key
1. Chọn Service Account vừa tạo
2. Vào tab "Keys"
3. Bấm "Add Key" > "Create new key"
4. Chọn "JSON" và bấm "Create"
5. File credentials.json sẽ tải xuống
6. Di chuyển file này vào thư mục gốc của ứng dụng

Bước 4: Tạo Google Sheets
1. Truy cập https://sheets.google.com
2. Tạo spreadsheet mới
3. Sao chép ID từ URL:
   https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit
   
Bước 5: Chia sẻ Google Sheets với Service Account
1. Mở file credentials.json đã tải
2. Tìm trường "client_email", ví dụ: netflix-manager@project-id.iam.gserviceaccount.com
3. Trong Google Sheets, bấm "Share"
4. Dán email vào và bấm "Share"
5. Chọn "Editor" role

Bước 6: Cấu hình Environment
1. Tạo file .env trong thư mục ứng dụng
2. Thêm:
   GOOGLE_CREDENTIALS_PATH=credentials.json
   GOOGLE_SPREADSHEET_ID=<ID từ bước 4>

Sau đó ứng dụng sẽ tự động kết nối và đồng bộ dữ liệu!

Các library cần cài đặt:
pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client gspread python-dotenv
"""
