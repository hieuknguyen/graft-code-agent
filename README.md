# Graft Code Agent

Graft Code Agent là coding agent chạy cục bộ cho dự án của bạn. Chế độ chính dùng **Gemini API trực tiếp**; gateway `antigravity-fastapi` cũ vẫn có thể dùng khi cần tương thích. Agent lấy ngữ cảnh từ thư mục dự án đã chọn, có thể đọc mã nguồn và đề xuất thay đổi hoặc lệnh chạy, nhưng các hành động có tác động luôn phải được bạn xác nhận rõ ràng.

## Gemini trực tiếp (mặc định cho cấu hình mới)

Chế độ này không cần API gateway trung gian. Khóa Gemini chỉ được đọc từ biến môi trường, không lưu vào `config.yaml`, giao diện hay lịch sử dự án.

### Cài đặt

Cần Python 3.10 trở lên để dùng đầy đủ các bộ kiểm tra cú pháp. Cài các thư viện của dự án (bao gồm SDK `google-genai>=2.24.0,<3.0.0`):

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

## Giao diện desktop theo mẫu Antigravity

Ứng dụng desktop PySide6 dùng bố cục hội thoại theo ảnh mẫu Antigravity: danh sách dự án và hội thoại ở thanh bên trái, ô nhập lớn ở giữa màn hình và bộ chọn dự án ngay phía trên. Khi có tin nhắn, ô nhập chuyển xuống dưới cuộc trò chuyện. Model, đính kèm ảnh và tùy chọn nằm trong khung nhập; các nút áp dụng/hoàn tác xuất hiện khi có thay đổi để xử lý.

Nhấn **Mở mã nguồn** hoặc `Ctrl+P` để mở Explorer và khung code/diff, dùng `Ctrl+J` để mở terminal. Hội thoại được nhóm theo dự án; chọn một hội thoại sẽ mở đúng thư mục và lịch sử tương ứng. Agent tiếp tục đề xuất thay đổi để bạn xem và xác nhận trước khi áp dụng.

```powershell
python desktop_app.py --dir "C:\duong-dan\toi\du-an"
```

Phím tắt hữu ích:

| Phím | Chức năng |
| --- | --- |
| `Ctrl+L` | Focus prompt của agent |
| `Ctrl+Enter` | Gửi yêu cầu hiện tại |
| `Ctrl+P` | Focus tìm file/symbol |
| `Ctrl+J` | Ẩn/hiện terminal |
| `Ctrl+Alt+A` | Quay lại hội thoại, đóng khung mã nguồn |
| `Ctrl+B` | Ẩn/hiện thanh bên |
| `Ctrl+N` | Bắt đầu cuộc trò chuyện mới |

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

## Công cụ code tích hợp cho AI

AI có thể gọi trực tiếp các công cụ dưới đây qua Gateway, cả khi lập kế hoạch và khi phân tích
log lỗi. Bộ khai báo Gemini cũng dùng chung các công cụ mới. Cài đầy đủ `requirements.txt`
để bật bộ kiểm tra cú pháp cho nhiều ngôn ngữ.

| Công cụ | Công dụng |
| --- | --- |
| `edit_file` | Sửa một đoạn bằng `path`, `old_text`, `new_text`; ứng dụng tự nhớ phiên bản file đã đọc. |
| `edit_file_ranges` | Thay/chèn/xóa tối đa 200 khoảng dòng trong file tới 8 MB; không cần gửi lại toàn bộ đoạn cũ. |
| `find_files` | Tìm đường dẫn theo mẫu như `**/*.py`, có phân trang. |
| `list_symbols` | Liệt kê hàm, class, method và khoảng dòng trong Python (`.py`, `.pyi`). |
| `read_symbol` | Đọc một hàm/class Python, gồm decorator; phân biệt các method trùng tên bằng `parent`. |
| `check_syntax` | Kiểm tra riêng một file trên đĩa theo ngôn ngữ tự nhận diện. Thao tác đọc/sửa đã tự trả thông tin cú pháp. |
| `propose_edit_file` | Đề xuất thay những đoạn văn bản xác định trong file UTF-8, giữ phần còn lại. |

Các công cụ `project_overview`, `list_files`, `search_project`, `read_file` hiện có cũng gọi được
qua Gateway. Dùng tìm kiếm văn bản và đọc theo dòng cho các ngôn ngữ ngoài Python. Kết quả đọc
có hash của file và thông báo nếu bị cắt bớt. File nhạy cảm, đường dẫn ngoài dự án và liên kết
symbolic/junction bị từ chối.

Ví dụ lời gọi do AI sinh:

```text
<<<TOOL_CALL
{"name": "read_symbol", "arguments": {"path": "src/service.py", "symbol": "fetch_data", "parent": "DataService"}}
<<<END_TOOL_CALL
```

Mỗi lượt lập kế hoạch/phân tích log có tối đa 4 vòng công cụ, mỗi vòng tối đa 8 lời gọi.
Lời gọi giống hệt bị lặp sẽ dừng; AI nhận kết quả trước khi đề xuất bước phụ thuộc.
`propose_edit_file` yêu cầu hash hiện tại cùng danh sách `old_text`/`new_text`: mỗi đoạn cũ phải
khớp duy nhất, các đoạn không được chồng lấn. Gom các sửa đổi của một file trong một đề xuất.
Đề xuất xuất hiện trong giao diện áp dụng hiện có, tuân theo chế độ áp dụng đang chọn; nếu file
đã thay đổi trước lúc lưu, ứng dụng từ chối ghi đè. Đề xuất chưa áp dụng không được tính là đã sửa.
`read_file` trả thêm `newline_style`; công cụ sửa giữ CRLF cho file dùng CRLF nhất quán trên Windows.

### Sửa file trực tiếp, không dùng terminal

AI đọc file bằng `read_file` hoặc `read_symbol`, rồi gọi `edit_file` với đoạn cũ và đoạn thay thế.
Không cần truyền hash hoặc viết script sửa file:

```text
<<<TOOL_CALL
{"name": "edit_file", "arguments": {"path": "src/service.py", "old_text": "timeout = 5", "new_text": "timeout = 30", "description": "Tăng thời gian chờ"}}
<<<END_TOOL_CALL
```

Thay đổi xuất hiện trong giao diện xem và áp dụng hiện có; chế độ tự động áp dụng vẫn hoạt động.
Đặt `new_text` rỗng để xóa đoạn cũ; để chèn, giữ đoạn làm mốc trong cả nội dung cũ và mới.
Nếu chưa đọc file hoặc file vừa thay đổi, AI phải đọc lại. Nếu đoạn cũ xuất hiện nhiều lần, AI phải
thêm ngữ cảnh để xác định đúng vị trí. Dùng `propose_edit_file` để gom nhiều sửa đổi cùng file.

### Sửa file lớn theo khoảng dòng

Sau khi đọc các vùng liên quan bằng `read_file`, AI có thể gửi một đề xuất gồm nhiều vùng:

```text
<<<TOOL_CALL
{"name": "edit_file_ranges", "arguments": {"path": "src/service.py", "edits": [{"start_line": 120, "end_line": 180, "new_text": "def fetch_data():\n    return []\n"}, {"start_line": 500, "end_line": 499, "new_text": "# Thêm ghi chú trước dòng 500\n"}], "description": "Cập nhật xử lý dữ liệu"}}
<<<END_TOOL_CALL
```

Số dòng bắt đầu từ 1, tính cả hai đầu và luôn dựa trên file gốc vừa đọc. `new_text` rỗng
xóa vùng; `end_line = start_line - 1` chèn trước dòng đó. Để thêm cuối file, dùng
`start_line = total_lines + 1`, `end_line = total_lines`. Có thể thay toàn bộ file bằng
vùng 1 đến `total_lines` nếu đã đọc đầy đủ nội dung. Các vùng không được chồng lấn.

Công cụ giữ phần không sửa, UTF-8 BOM và CRLF của file dùng CRLF nhất quán. Cả đề xuất
được kiểm tra trước khi tạo thẻ áp dụng; file thay đổi sau lần đọc sẽ bị từ chối để AI đọc lại.
Giới hạn đọc/sửa là 8 MB mỗi file. Mỗi lần đọc trả tối đa 400 dòng/48K ký tự; dùng
`next_start_line` để đọc tiếp. `partial_line` báo dòng quá dài chưa hiển thị hết.

### Tự phản hồi lỗi cú pháp cho AI

`read_file` kiểm tra nội dung hiện tại; `edit_file`, `edit_file_ranges`, `propose_edit_file`
và `propose_write_file` kiểm tra toàn bộ nội dung dự kiến. Kết quả tự kèm trường `syntax`
gồm trạng thái, ngôn ngữ, dòng/cột, thông báo và đoạn code lỗi. Bản sửa không hợp lệ bị
từ chối trước khi tạo đề xuất: AI nhận ngay `SYNTAX_ERROR` và sửa lại dựa trên file gốc,
không cần gọi thêm công cụ hoặc chạy lệnh kiểm tra syntax. Khi áp dụng, app kiểm tra lại.
Các khối `CREATE_FILE`/`GRAFT_ACTION` kế thừa cũng nhận phản hồi tự động với tối đa hai
lượt sửa cú pháp; hết giới hạn thì dừng và hiển thị lỗi.

App chọn bộ kiểm tra theo phần mở rộng/tên file trong dự án, hỗ trợ Python, JS/JSX,
TS/TSX, PHP, Go, Rust, Java, C/C++, C#, CSS/HTML, SQL và nhiều ngôn ngữ khác; cấu hình
JSON, JSONC (gồm tsconfig/jsconfig và cấu hình `.vscode`), YAML, TOML cũng được xử lý.
Bộ [tree-sitter-language-pack 0.13.0](https://pypi.org/project/tree-sitter-language-pack/0.13.0/)
được khóa phiên bản để dùng các grammar đi kèm, không tải parser qua mạng lúc sửa file.
Không chạy code dự án để kiểm tra cú pháp.

Định dạng chưa hỗ trợ, template Blade, parser thiếu hoặc vượt giới hạn được trả là
`unavailable` và hiển thị cảnh báo, không bị coi là đã kiểm tra thành công. Đây là kiểm
tra cú pháp khi đọc/đề xuất/ghi file, không phải trình theo dõi nền toàn bộ dự án. Nó không
thay thế kiểm tra kiểu, import, build hay test; phần code nhúng trong HTML/Vue hoặc cú pháp
đặc thù framework có thể cần công cụ riêng của dự án.

## AI prompts

The maintained model instructions are written in English. User-facing replies follow the user's
language and default to Vietnamese. Project source, user requests, and diagnostic report data retain
their original language.

- `core/prompts.py` contains the shared engineering instructions, gateway action protocol, Gemini
  tool protocol, context follow-up, and terminal-feedback instructions.
- `core/context_builder.py` assembles the gateway's project context and loads the additional
  guidelines from `rules/SENIOR_ENGINEERING_RULES.md`. The root `SENIOR_ENGINEERING_RULES.md` is a
  compatibility fallback; keep the two copies aligned.
- `core/agent.py` adds source excerpts, web results, and diagnostic hypotheses to gateway requests.
- `core/gemini_agent.py` uses the shared engineering instructions with its function-tool protocol.

The prompts require source-based investigation, focused changes, root-cause diagnosis, and evidence
before completion claims. They distinguish proposals from applied and verified work. They do not
change runtime permissions or approval settings. Gateway planning allows one retrieval follow-up
and one correction when a clear action request receives only prose or code examples. The correction
must return explicit action blocks; ordinary Markdown is never converted into executable commands.
If no actions are returned, the desktop reports that nothing was executed. Questions and explicit
explanation-only requests do not trigger this correction. Gemini exposes only its declared tools.
Missing evidence must be reported honestly at those limits.

Terminal feedback keeps a per-task journal of actual file changes and recent command results,
and supports one batched `READ_FILE`/enabled `WEB_SEARCH` follow-up. File reads use the project
read policy and do not pass through the terminal's 4000-character log tail. On Windows, CMD
receives native arguments so quoted paths, Python inline scripts, and nested PowerShell survive
Qt's launch boundary.

`max_feedback_loops = 0` still allows unlimited useful steps. A separate guard stops the task
when the same command or equivalent full-file read occurs four times within twelve command
completions without an actual file-content change. It clears queued commands and pending automatic
callbacks. Failed writes and identical-content rewrites do not reset this guard; a new request does.

## Kiểm thử desktop

Các kiểm thử desktop chạy ở chế độ offscreen nên có thể dùng trong CI Linux:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q
python -m compileall -q desktop
```
