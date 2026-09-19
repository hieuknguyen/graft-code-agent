# Graft Code Agent

Graft Code Agent là coding agent chạy cục bộ cho dự án của bạn. Chế độ chính dùng **Gemini API trực tiếp**; gateway `antigravity-fastapi` cũ vẫn có thể dùng khi cần tương thích. Agent lấy ngữ cảnh từ thư mục dự án đã chọn, có thể đọc mã nguồn và đề xuất thay đổi hoặc lệnh chạy, nhưng các hành động có tác động luôn phải được bạn xác nhận rõ ràng.

## Gemini trực tiếp (mặc định cho cấu hình mới)

Chế độ này không cần API gateway trung gian. Khóa Gemini chỉ được đọc từ biến môi trường, không lưu vào `config.yaml`, giao diện hay lịch sử dự án.

### Cài đặt

Cần Python 3.9 trở lên. Cài các thư viện của dự án (bao gồm SDK `google-genai>=2.24.0,<3.0.0`):

```powershell
pip install -r requirements.txt
```

### Chạy trên Windows PowerShell

Đặt khóa cho phiên PowerShell hiện tại rồi mở agent tại thư mục mã nguồn cần làm việc:

```powershell
$env:GRAFT_PROVIDER = "gemini"
$env:GEMINI_API_KEY = "khóa_Gemini_của_bạn"
# Tùy chọn: chọn một model Gemini mà tài khoản của bạn được phép dùng.
$env:GEMINI_MODEL = "gemini-..."

python run.py --cli --dir "C:\duong-dan\toi\du-an"
```

`GEMINI_API_KEY` là bắt buộc. Nếu không đặt `GEMINI_MODEL`, agent dùng model mặc định của cấu hình. Không đưa khóa API vào Git, `config.yaml`, prompt hoặc ảnh chụp màn hình.

## Ngữ cảnh toàn dự án

`--dir` xác định **thư mục gốc (workspace)** của agent. Khi bắt đầu, agent quét cấu trúc và chỉ mục AST/symbol của dự án; trong lúc xử lý yêu cầu, nó đọc các tệp liên quan để có đủ ngữ cảnh thay vì yêu cầu bạn dán toàn bộ mã nguồn vào chat. Vì vậy bạn có thể hỏi về kiến trúc, tìm vị trí cần sửa, hoặc yêu cầu phân tích một lỗi trên toàn dự án.

Hãy chọn đúng thư mục gốc của dự án. Đường dẫn và tệp ngoài workspace không nên được coi là một phần ngữ cảnh hay phạm vi thao tác của agent.

## Quy tắc an toàn của coding agent

Đọc ngữ cảnh là thao tác chỉ đọc. Với mọi hành động có tác động, agent phải hiển thị nội dung cần làm và chờ xác nhận riêng của bạn:

| Hành động | Trước khi thực hiện |
| --- | --- |
| Tạo, sửa hoặc xóa tệp | Hiển thị đường dẫn và diff/nội dung dự kiến; chỉ ghi khi bạn đồng ý. |
| Chạy lệnh terminal | Hiển thị nguyên văn lệnh và thư mục chạy; chỉ chạy khi bạn đồng ý. |
| Chạy PowerShell | Hiển thị nguyên văn lệnh PowerShell và yêu cầu xác nhận riêng; PowerShell chạy ở chế độ không nạp profile, không tương tác. |

Từ chối xác nhận nghĩa là tệp không bị thay đổi và lệnh không được chạy. Giá trị mặc định an toàn là không tự áp dụng thay đổi; đừng dùng chế độ tự động nếu bạn muốn giữ bước kiểm tra này.

## Gateway cũ (tùy chọn)

Nếu đang có `antigravity-fastapi` Gateway, có thể chuyển sang nhà cung cấp cũ bằng biến môi trường sau:

```powershell
$env:GRAFT_PROVIDER = "gateway"
$env:GRAFT_GATEWAY_URL = "http://localhost:5678/webhook/antigravity-chat"
$env:GRAFT_API_KEY = "sk-antigravity-your-api-key"
$env:GRAFT_MODEL = "ten-model-cua-gateway"

python run.py --cli --dir "C:\duong-dan\toi\du-an"
```

Gateway là tùy chọn; cài đặt Gemini trực tiếp không phụ thuộc vào nó. Các biến `GRAFT_GATEWAY_URL`, `GRAFT_API_KEY` và `GRAFT_MODEL` chỉ dành cho chế độ `gateway`; `GEMINI_API_KEY` và `GEMINI_MODEL` chỉ dành cho chế độ `gemini`.

## Lệnh CLI hữu ích

```powershell
# Bắt đầu phiên tương tác tại thư mục hiện tại
python run.py --cli --dir .

# Quét/chỉ mục lại sau khi bạn tự thêm tệp
/scan

# Xem sơ đồ symbol đã lập chỉ mục
/tree

# Tìm một hàm hoặc class
/find ten_symbol
```

Ví dụ yêu cầu:

```text
Phân tích luồng đăng nhập của dự án và chỉ ra các tệp liên quan.
Sửa lỗi kiểm tra email trong utils.py; hãy cho tôi xem diff trước khi ghi.
Chạy bộ kiểm thử phù hợp, nhưng hỏi tôi trước khi thực thi lệnh.
```

## Khả năng Graft kế thừa

Dự án vẫn giữ các thành phần AST grafting: lập chỉ mục class/hàm, tạo diff và kiểm tra cú pháp trước khi áp dụng. Chúng hỗ trợ agent giới hạn thay đổi vào phần mã cần thiết thay vì viết lại cả tệp. Một số giao diện desktop/web cũ hướng tới workflow gateway; CLI là cách rõ ràng nhất để sử dụng chế độ Gemini trực tiếp và các bước xác nhận an toàn.
"# graft-code-agent" 
