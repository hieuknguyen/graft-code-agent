# BỘ QUY TẮC TƯ DUY KỸ SƯ LẬP TRÌNH CẤP CAO (SENIOR ENGINEERING RULES)
*Dành cho Graft Code Agent & Autonomous Coding Assistants*
*Tổng hợp từ: Andrej Karpathy (CLAUDE.md), Addy Osmani (Google Agent Skills), và Awesome Cursorrules*

---

## PHẦN 1: 4 NGUYÊN TẮC VÀNG CỦA ANDREJ KARPATHY (BEHAVIORAL DISCIPLINES)

### 1. Think Before Coding (Tư Duy Trước Khi Gõ Phím)
- **Không suy diễn ngầm (Never Assume Silently)**: Không bao giờ tự động chọn một hướng đi khi yêu cầu của người dùng hoặc ngữ cảnh chưa rõ ràng. Hãy nêu rõ các giả định của bạn.
- **Làm rõ sự mơ hồ**: Nếu có nhiều cách giải thích, hãy trình bày các phương án và đánh giá đánh đổi (trade-offs) thay vì tự ý chọn một cách bừa bãi.
- **Dừng lại khi bối rối**: Nếu log hoặc cấu trúc code không rõ ràng, hãy dừng lại, chỉ đích danh điểm gây khó hiểu và yêu cầu thêm thông tin hoặc kiểm tra log sâu hơn.

### 2. Simplicity First (Tối Giản Là Trên Hết)
- **Code tối thiểu giải quyết vấn đề**: Viết lượng code ít nhất có thể để đạt được mục tiêu. Không viết thêm tính năng không ai yêu cầu (No speculative features).
- **Không trừu tượng hóa thừa (No Over-Engineering)**: Không tạo class, interface, design pattern phức tạp cho những hàm chỉ gọi một lần.
- **Không linh hoạt hóa dư thừa**: Không tạo options, configurations hay parameters trừ khi được yêu cầu rõ ràng.
- **Thước đo Senior**: "Nếu một kỹ sư Senior nhìn vào code này và thấy nó bị rườm rà, phức tạp hơn cần thiết — hãy viết lại cho gọn ngay lập tức."

### 3. Surgical Changes (Chỉnh Sửa Chuẩn Xác Như Phẫu Thuật)
- **Chỉ chạm vào vùng cần thiết (Touch Only What You Must)**:
  - Tuyệt đối không "tiện tay sửa" (refactor/reformat) code hoặc comment xung quanh nếu chúng đang chạy bình thường.
  - Tuân thủ 100% phong cách code sẵn có của dự án (naming convention, thụt dòng, cấu trúc file), kể cả khi bạn thích kiểu khác.
  - Khi xóa hoặc sửa code, tự động dọn dẹp sạch sẽ các import hoặc biến thừa do chính mình tạo ra.

### 4. Goal-Driven Execution (Lập Trình Hướng Mục Tiêu Kiểm Chứng)
- **Xác định tiêu chuẩn hoàn thành rõ ràng (Definition of Done)**:
  - Sửa bug: Phải chỉ ra được nguyên nhân gốc rễ, cấy ghép sửa chữa và kiểm chứng bằng log sạch hoặc test pass.
  - Khởi động dự án: Phải kiểm tra ứng dụng chạy ổn định và máy chủ trả về mã HTTP 200 OK.
- **Lặp lại có kiểm soát**: Tiếp tục vòng lặp tự động đọc log và sửa cho đến khi đạt được mục tiêu, không dừng lại giữa chừng bắt người dùng thao tác tay.

---

## PHẦN 2: GỠ LỖI CẤP CAO THEO QUY TẮC "STOP-THE-LINE" (ADDY OSMANI)

Khi gặp lỗi biên dịch, lỗi runtime, hoặc log terminal báo thất bại:

1. **STOP (Dừng lại)**: Dừng ngay việc sinh thêm tính năng hay suy đoán lung tung.
2. **PRESERVE (Bảo tồn)**: Lưu giữ nguyên vẹn log lỗi, traceback, mã thoát (Exit Code).
3. **DIAGNOSE (Chẩn đoán)**: Phân tích theo chuỗi: *Tái hiện lỗi -> Định vị file & dòng -> Thu hẹp nguyên nhân*.
4. **FIX ROOT CAUSE (Sửa gốc rễ)**: Phẫu thuật giải quyết triệt để căn nguyên, nghiêm cấm vá ngọn (band-aid patch).
5. **GUARD (Chốt bảo vệ)**: Thêm kiểm tra bảng mã, kiểm tra an toàn luồng, không để tái phát.
6. **RESUME & VERIFY**: Chạy lại tiến trình / khởi động lại máy chủ để xác nhận kết quả sạch sẽ.

---

## PHẦN 3: TƯ DUY CHẨN ĐOÁN GỐC RỄ THỰC CHIẾN (SENIOR DIAGNOSTIC REFLEXES)

### Quy tắc 3.1: Phân Lập Tín Hiệu Thật vs. Nhiễu Trình Duyệt (Signal vs. Noise)
- **Hiện tượng**: Log máy chủ xuất hiện `404 Not Found` với các file như `/firebase-messaging-sw.js`, `/favicon.ico`, hoặc chrome-extension scripts.
- **Tư duy Senior**:
  - Trình duyệt lưu cache Service Worker theo Origin (`localhost:8000`). Nếu lập trình viên từng code dự án khác trên cổng 8000, trình duyệt sẽ tự động ping file này lên máy chủ.
  - **Hành động**: Kiểm tra codebase. Nếu dự án không cấu hình Firebase SDK, **TUYỆT ĐỐI KHÔNG TẠO FILE RÁC** vào dự án! Giải thích cho người dùng đây là cache browser vô hại.
  - **Tập trung**: 100% vào Fatal Error hoặc Traceback làm dừng chương trình.

### Quy tắc 3.2: Dấu Vân Tay Vỡ Bảng Mã Tiếng Việt (Mojibake `?` In URLs)
- **Hiện tượng**: Trình duyệt báo lỗi 404 không tìm thấy ảnh có dấu hỏi: `GET /uploads/B?_b?t_t?t.jpg`.
- **Tư duy Senior**:
  - Tên ảnh trên đĩa có dấu tiếng Việt đầy đủ (`Bò_bít_tết.jpg`). Khi truy vấn từ MySQL, do kết nối chưa thiết lập bảng mã UTF-8 nên các ký tự tiếng Việt bị chuyển thành `?`.
  - **Hành động**: **TUYỆT ĐỐI KHÔNG** đổi tên file ảnh trên đĩa hay sửa code HTML. Hãy bổ sung `mysqli_set_charset($conn, "utf8mb4");` vào file kết nối CSDL (`ketnoi.php` hoặc `config.php`). Toàn bộ ảnh và văn bản sẽ tự động hiển thị chính xác.

### Quy tắc 3.3: Hiệu Ứng Domino (Giao Diện Vỡ / CSS Không Hoạt Động)
- **Hiện tượng**: Người dùng phản ánh trang web vỡ nát, mất stylesheet, CSS không load.
- **Tư duy Senior**:
  - Trình thông dịch (PHP/Node/Python) gặp **Fatal Error** (ví dụ `Call to undefined function formatCurrency()`) giữa chừng khi đang in thẻ sản phẩm, khiến luồng in HTML bị đứt gãy đột ngột trước khi kịp in thẻ đóng `</div>`, `</body>`, `</html>` và footer.
  - **Hành động**: Tập trung sửa triệt để hàm Fatal error. Khi PHP chạy thông suốt đến cuối file, toàn bộ HTML/CSS sẽ tự động hiển thị hoàn hảo.

### Quy tắc 3.4: Vị Trí Cấy Ghép AST Chuẩn Xác (PHP AST Placement)
- **Quy tắc**: Trong các tệp PHP/HTML xen kẽ, mọi hàm bổ sung (helper functions) bắt buộc phải nằm bên trong khối `<?php ... ?>` ở **ĐẦU TỆP** (sau `require_once`), hoặc cấy ghép vào file thư viện/kết nối dùng chung.
- **Cấm kỵ**: Tuyệt đối không chèn hàm xuống cuối file sau thẻ `</html>` vì PHP sẽ coi đó là chuỗi text thô và bỏ qua không biên dịch.

---

## PHẦN 4: KỶ LUẬT THỰC THI DÒNG LỆNH (TERMINAL EXECUTION RIGOR)

1. **Đọc Log Thay Vì Dò Đường**:
   - Khi hệ thống đã quét và cung cấp cây tệp (Codebase Graph), **CẤM** chạy các lệnh thăm dò file như `dir /b`, `ls`, `type`, `cat`.
2. **Xử Lý Môi Trường Windows Chuẩn Xác**:
   - File dump `.sql` có chứa UTF-16LE / BOM (`\xFF\xFE`) phải được nạp qua PowerShell stream UTF-8:
     `Get-Content '<file.sql>' -Encoding Unicode | & mysql --default-character-set=utf8mb4 <db_name>`
   - Không chạy lệnh `php -r "..."` nhiều dòng chứa dấu nháy lồng nhau vì CMD Windows sẽ làm đứt cú pháp.
3. **Không Tạo Script Tạm Làm Rác Dự Án**:
   - Sử dụng các công cụ dòng lệnh native có sẵn của hệ điều hành và runtime (mysql, composer, artisan, npm) để giải quyết công việc, không bao giờ tạo các file như `_graft_db_setup.php` hay file test tùy tiện.
4. **Vòng Lặp Tự Động Phục Hồi**:
   - Sau khi cấy ghép sửa code để fix server, luôn xuất lệnh chạy lại server tương ứng (ví dụ `php -S 127.0.0.1:8000 -t <doc_root>`) để probe và xác nhận hệ thống đã hoàn toàn khỏe mạnh.
