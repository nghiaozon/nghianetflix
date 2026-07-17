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

Không cần `GITHUB_TOKEN` cục bộ. Quy trình dùng thông tin đăng nhập Git hiện có để push tag;
GitHub Actions tạo Release bằng token nội bộ của repository.

Sau mỗi lần sửa code, chạy duy nhất:

```powershell
.\release.bat
```

Lệnh trên tự tăng phiên bản `patch`, build và smoke-test EXE, tính SHA-256, cập nhật
`app_version.py`/`update.json`, chạy test, commit, push code và push tag. GitHub Actions nhận tag,
build lại gói chính thức rồi tự tạo GitHub Release cùng EXE và manifest. Nếu lỗi xảy ra trước khi
commit, script tự khôi phục version và manifest ban đầu.

Trước khi đổi version, script tự `fetch` và `rebase --autostash` lên `origin/<branch>` để lấy
commit manifest do GitHub Actions tạo mà vẫn giữ các thay đổi source chưa commit. Script kiểm tra
remote lần nữa sau build/test và trước push, vì vậy lần phát hành kế tiếp không bị lỗi
`fetch first`/`non-fast-forward`. Không dùng `git push --force` để xử lý lỗi phát hành.

Các tùy chọn thường dùng:

```powershell
.\release.bat -Bump minor
.\release.bat -Version 2.0.0 -Notes "Giao diện mới và sửa lỗi đồng bộ"
.\release.bat -Package zip
.\release.bat -NoPush                 # chỉ thử quy trình cục bộ, không upload
```

Ứng dụng gọi trực tiếp GitHub API tại
`https://api.github.com/repos/nghiaozon/nghianetflix/releases/latest`, đọc `tag_name`, rồi chọn
asset theo tên cố định. `update.json` vẫn được phát hành và workflow ghi lại bản có hash chính
thức lên nhánh `main` để các bản app cũ tiếp tục cập nhật được.

Tên asset được nhận, theo thứ tự ưu tiên:

- `NetflixManager.exe` — bản portable một file, cách phát hành mặc định.
- `NetflixManager-X.Y.Z.zip` hoặc `NetflixManager.zip` — ZIP phải chứa đúng một
  `NetflixManager.exe`; toàn bộ cây file chương trình trong cùng thư mục sẽ được cập nhật.
- `NetflixManager-Setup.exe` hoặc `NetflixManager-Installer.exe` — installer độc lập.

Không đổi tên tùy ý (ví dụ `app-final.exe`) vì updater sẽ chủ động từ chối asset không thuộc
danh sách trên. Mỗi asset phải có SHA-256 trong trường `digest` của GitHub API hoặc có asset
sidecar cùng tên cộng `.sha256`, ví dụ `NetflixManager.exe.sha256`.

## Quy trình thủ công (tham khảo/xử lý sự cố)

1. Tăng `APP_VERSION` trong `app_version.py` (ví dụ `1.0.0` thành `1.1.0`).
2. Kiểm tra `GITHUB_OWNER`, `GITHUB_REPOSITORY` và `GITHUB_RELEASE_API_URL` trong file đó.
3. Chạy `build.ps1`, rồi tạo GitHub Release có tag `vX.Y.Z` và upload
   `dist\NetflixManager.exe` với đúng tên này.
4. Tính SHA-256 bằng `Get-FileHash dist\NetflixManager.exe -Algorithm SHA256`.
5. Sao chép `update.json.example` thành `update.json`; sửa `version`, `download_url`,
   `package_type`, `package_name`, `executable_name`, `changelog` và **bắt buộc** điền `sha256`.
6. Upload `NetflixManager.exe.sha256`; chỉ công bố Release sau khi các asset đã upload xong.
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

Updater luôn xác định EXE và thư mục ứng dụng từ runtime, không lưu đường dẫn vào config. Với gói EXE, app thay đúng file EXE đang chạy, kể cả khi người dùng đã đổi tên file. Với gói ZIP, app thay toàn bộ file chương trình có trong gói. Các thư mục `data`, `config`, `excel`, `database`, `credentials` cùng file DB, Excel, JSON người dùng và `.env` không bị ghi đè. Mọi file được backup trước khi thay; nếu copy hoặc smoke-test thất bại, updater tự rollback và mở lại bản cũ. Nhật ký `update.log` nằm cạnh EXE (hoặc `%TEMP%\NetflixManager-update.log` nếu thư mục app không ghi được) và ghi current/latest version, API URL, asset, URL/path tải, lỗi, replace, rollback và restart.

Vì đây là PyInstaller one-file, mọi lần smoke-test, restart và rollback đều phải chạy với
`PYINSTALLER_RESET_ENVIRONMENT=1` và không kế thừa biến `_PYI_*`. Nếu thiếu bước này, tiến trình
mới có thể dùng lại thư mục `_MEI` của tiến trình cũ rồi lỗi thiếu `base_library.zip` khi thư mục
cũ bị dọn. Sau khi build, có thể chạy regression test thực tế trong thư mục Unicode/tên EXE tùy ý:

```powershell
$env:NETFLIX_MANAGER_RUN_FROZEN_INTEGRATION = "1"
.\.venv\Scripts\python.exe -m unittest tests.test_updater.UpdaterTests.test_built_onefile_restarts_with_fresh_mei_from_unicode_folder -v
```
