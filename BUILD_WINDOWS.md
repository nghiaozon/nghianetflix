# Build ứng dụng Windows (.exe)

## Kết quả đóng gói

PyInstaller tạo một file giao diện `dist\NetflixManager.exe` chạy không có cửa sổ console. Python, PySide6, Matplotlib và các thư viện khác được đóng trong file này; máy người dùng không cần cài Python hoặc pip.

Dữ liệu có thể ghi không được nhét vào file `.exe`, vì nội dung đóng gói một-file là tạm thời. Cấu trúc phát hành là:

```text
dist\
  NetflixManager.exe
  data\
    netflix_manager.db
  .env                 (tùy chọn, cho Google Sheets)
  credentials.json     (tùy chọn, không chia sẻ công khai)
```

Hãy gửi nguyên thư mục `dist` (có thể nén ZIP), không chỉ riêng `.exe`, nếu muốn gửi kèm dữ liệu ban đầu.

## Yêu cầu trên máy build

- Windows 10/11 64-bit.
- Python 3.11–3.14 64-bit từ python.org, có Python Launcher (`py`). Khuyến nghị 3.13 cho môi trường build ổn định.
- Internet ở lần đầu để tải thư viện.

## Cách build tự động

Mở PowerShell tại thư mục dự án và chạy:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build.ps1
```

Script sẽ tạo `.venv`, cài `requirements.txt`, chạy PyInstaller, rồi chép database và cấu hình tùy chọn sang `dist`.

Để build sạch lại, chỉ cần chạy lại script. Thư mục trung gian là `build`; sản phẩm gửi cho người dùng nằm trong `dist`.

## Google Sheets (tùy chọn)

Sao chép `.env.example` thành `.env`, điền `GOOGLE_SPREADSHEET_ID`, và đặt `credentials.json` cạnh `.exe`. Nếu `GOOGLE_CREDENTIALS_PATH` là đường dẫn tương đối, app sẽ tính từ thư mục chứa `.exe`. Không có hai file này thì app vẫn chạy local với SQLite, chỉ chức năng đồng bộ không kết nối.

Không commit hoặc phát hành `credentials.json` cho người không được phép truy cập service account.

## Icon và tài nguyên bổ sung

Hiện dự án chưa có icon/ảnh/file `.ui` riêng. Khi có icon, đặt tại `assets\app.ico` rồi bỏ dấu `#` trước dòng `icon=` trong `NetflixManager.spec`.

Với ảnh hoặc file giao diện chỉ dùng để đọc, thêm chúng vào `datas` trong spec, ví dụ:

```python
datas += [("assets", "assets")]
```

File Excel/database cần chỉnh sửa nên đặt trong `dist\data`, không đóng vào bundle. Trong code, dùng `runtime_paths.data_file("ten_file.xlsx")` để lấy đúng đường dẫn.

## Kiểm thử trước khi gửi

1. Chạy `dist\NetflixManager.exe` và kiểm tra không xuất hiện console.
2. Thêm/sửa một bản ghi, đóng app, mở lại và xác nhận dữ liệu còn nguyên.
3. Thử trên máy Windows khác chưa cài Python.
4. Nếu Windows SmartScreen cảnh báo, chọn **More info > Run anyway** cho bản nội bộ. Để phân phối rộng rãi và giảm cảnh báo, nên ký số file `.exe` bằng chứng thư code-signing.

Lưu ý: phải build trên Windows để tạo `.exe` Windows; nên build cùng kiến trúc với máy đích (thông thường x64).

## Phát hành bản tự cập nhật bằng một lệnh

Thiết lập một lần GitHub token có quyền **Contents: Read and write**:

```powershell
$env:GITHUB_TOKEN = "github_pat_..."
```

Không ghi token vào file trong dự án. Có thể lưu biến môi trường trong Windows nếu không muốn nhập lại sau khi mở terminal mới.

Sau mỗi lần sửa code, chạy duy nhất:

```powershell
.\release.bat
```

Lệnh trên tự tăng phiên bản `patch`, build và smoke-test EXE, tính SHA-256, cập nhật
`app_version.py`/`update.json`, chạy test, commit và push thay đổi, tạo GitHub Release dạng draft,
upload EXE cùng manifest rồi mới công bố Release. Nếu bước nào lỗi, quy trình dừng với exit code 1 và
Release chưa hoàn chỉnh vẫn ở trạng thái draft.

Các tùy chọn thường dùng:

```powershell
.\release.bat -Bump minor
.\release.bat -Version 2.0.0 -Notes "Giao diện mới và sửa lỗi đồng bộ"
.\release.bat -Package zip
.\release.bat -NoPush                 # chỉ thử quy trình cục bộ, không upload
```

Ứng dụng mới đọc manifest ổn định tại `releases/latest/download/update.json`; bản cũ vẫn đọc
`update.json` trên nhánh `main`, nên script tiếp tục commit file này để tương thích.

## Quy trình thủ công (tham khảo/xử lý sự cố)

1. Tăng `APP_VERSION` trong `app_version.py` (ví dụ `1.0.0` thành `1.1.0`).
2. Đặt URL raw/public của manifest vào `DEFAULT_UPDATE_MANIFEST_URL` trong file đó.
3. Chạy `build.ps1`, rồi upload `dist\NetflixManager.exe` lên GitHub Releases hoặc server HTTPS.
4. Tính SHA-256 bằng `Get-FileHash dist\NetflixManager.exe -Algorithm SHA256`.
5. Sao chép `update.json.example` thành `update.json`; sửa `version`, `download_url`,
   `package_type`, `package_name`, `executable_name`, `changelog` và **bắt buộc** điền `sha256`.
6. Chỉ công bố manifest sau khi Release asset đã upload xong.
7. Chạy workflow **Verify update release** trong GitHub Actions. Workflow tải manifest và
   Release asset công khai, sau đó đối chiếu SHA-256; chỉ phát hành khi job này thành công.

Có thể kiểm tra tương tự từ máy build:

```powershell
.\.venv\Scripts\python.exe tools\verify_release.py "https://raw.githubusercontent.com/nghiaozon/nghianetflix/main/update.json"
```

Với gói ZIP, đặt `package_type` là `zip`, `package_name` là tên ZIP và
`executable_name` là tên EXE duy nhất cần lấy từ ZIP. SHA-256 luôn là hash của package
được tải xuống (ZIP hoặc EXE), không phải hash của file sau khi giải nén.

Nếu bản phát hành đã ký số, đặt `require_authenticode: true` và điền một phần tên nhà
phát hành trong `publisher`. Ứng dụng sẽ từ chối file không có chữ ký Windows hợp lệ
hoặc không đúng nhà phát hành. Nên bật tùy chọn này sau khi quy trình code-signing ổn định.

Khi khởi động, ứng dụng kiểm tra cập nhật ở nền và chỉ hiện hộp thoại nếu có bản mới.
Lỗi mạng của lần kiểm tra nền không làm gián đoạn người dùng; nút cập nhật thủ công vẫn
hiển thị lỗi đầy đủ. Trước khi tải/cài, ứng dụng thử quyền ghi trong thư mục chứa EXE và
hướng dẫn người dùng di chuyển ứng dụng hoặc dùng quyền phù hợp nếu thư mục bị khóa.

App chỉ thay thế `NetflixManager.exe`. Các thư mục `data` và `config` không bị xóa hay ghi đè. Cấu hình mới nằm trong `config`; app sẽ tự sao chép `.env`/`credentials.json` từ vị trí cũ cạnh EXE vào đây một lần để tương thích.
