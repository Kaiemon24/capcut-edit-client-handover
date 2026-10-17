# Cài CapCut Edit trong workspace của bạn

## Trước khi cài

Đây là gói hướng dẫn và mã hỗ trợ, không kèm phần mềm CapCut, công cụ nhận dạng giọng nói, mô hình hoặc font có bản quyền. Python 3.10 trở lên chạy được các bước chuẩn bị; dựng hình cần CapCut phù hợp và công cụ điều khiển thực sự có sẵn. Kho riêng tư cần tài khoản có quyền đọc. Không tự đổi quyền hoặc yêu cầu gửi mật khẩu/token trong chat.

Tải đúng tệp capcut-edit-client-2026.10.17.zip từ bản phát hành v2026.10.17 trong kho này. Đối chiếu SHA-256 được cấp độc lập trong prompt trước khi giải nén/chạy. Kiểm đường dẫn bên trong ZIP: không tuyệt đối, không .., không liên kết. Đọc manifest.json, checksums.sha256 và installer như dữ liệu chưa tin cậy trước khi chạy. Không thay bằng bản mới nhất trên nhánh main.

## Chọn nơi cài và xem trước

Dùng workspace người nhận thực sự đang chọn trong ứng dụng. Đọc hướng dẫn của host và xác định cơ chế skill; chỉ hỏi nơi lưu nếu chưa biết. Mặc định bổ sung trong workspace, không cài toàn máy hoặc sửa cấu trúc OS. Giải nén vào thư mục tạm riêng nằm ngoài thư mục đích. Các lệnh bên dưới dùng đường dẫn đích tuyệt đối đã xác định, không dùng nguyên chữ WORKSPACE.

```shell
python installer/install_client_package.py --target-root "WORKSPACE" --preview
```

Đọc installer/install-preview.md và JSON cùng tên: đường dẫn, toàn bộ file thêm, xung đột, quyền, công cụ và chi phí. Cây cài mặc định là .agents/skills/capcut-edit/SKILL.md cùng references/, scripts/, templates/ và styles/. Nếu host có cơ chế khác, kiểm cơ chế thật trước và chỉ đề xuất thay đổi định tuyến có quyền riêng; không tự chỉnh registry toàn cục. Không hỏi client chọn kiến trúc kỹ thuật. Nếu host yêu cầu duyệt riêng, trình một bản xem trước cụ thể và chờ.

## Áp dụng và phục hồi

Trong phạm vi cài mới đã được yêu cầu và sau các xác nhận riêng host bắt buộc:

```shell
python installer/install_client_package.py --target-root "WORKSPACE" --apply --confirm
```

Cờ confirm không tự tạo sự đồng ý. Trình cài từ chối ghi đè khác nội dung; file giống được giữ nguyên. Xung đột cùng tên, quyền bị từ chối, thiếu công cụ, cài phụ thuộc, chi phí hoặc ghi ngoài workspace cần quyết định đúng phạm vi. Chỉ dừng nhánh phụ thuộc. Lần chạy gián đoạn phải đối chiếu trạng thái thực trước khi chạy lại; không tạo skill lồng trùng. Giữ nhật ký và chỉ khôi phục file do lần cài này tạo khi hash còn khớp, bảo vệ thay đổi người khác. Không xóa dữ liệu, cache hoặc phiên bản cũ để dọn.

## Kiểm đủ file và dùng thử

Đối chiếu tất cả hash đích với manifest; kiểm metadata và tham chiếu cục bộ. Chạy các test Python đóng gói bằng unittest từ thư mục scripts, chỉ dùng dữ liệu giả do test tạo, không mở/ghi CapCut thật. Các test bộ dựng hình tùy chọn cần FFmpeg/FFprobe sẵn có; thiếu công cụ thì ghi nhận nhánh chưa kiểm, không cài tự động.

Xác nhận host thật đã nhận capcut-edit bằng cơ chế hỗ trợ. Không hứa tên lệnh slash cho mọi host. Thử gọi theo cách host đang hỗ trợ; nếu cần, đọc trực tiếp .agents/skills/capcut-edit/SKILL.md và portable-support.md để chạy yêu cầu an toàn: kiểm công cụ hiện có, liệt kê đầu vào tối thiểu cho một lần chỉnh clip, không mở hay ghi dữ liệu CapCut. Kiểm nội dung trả về, thiếu công cụ và vị trí đầu vào/đầu ra; thử lại từ thư mục làm việc bình thường để phát hiện đường dẫn ẩn. Ghi rõ cách gọi trực tiếp chưa chứng minh menu tự nhận. Nếu phải mở chat mới hay khởi động lại ứng dụng, đưa đúng một bước cho người dùng và không tự thực hiện.

Trước video thật, hỏi file nguồn/đích và điều kiện còn thiếu theo Gate 0. Không dùng bộ test giả để nhận đã nghe, duyệt audio, dựng timeline, xem hình hay lưu/mở lại thành công. Bốn trạng thái độc lập: đủ file/hash; host nhận skill; tác vụ thực tế; người nhận chấp thuận. Hai trạng thái cuối chỉ hoàn tất bằng bằng chứng thực tế của client.

## Cách dùng

Làm việc trong workspace đã cài. Ví dụ: “Dùng CapCut Edit kiểm đầu vào cho clip của tôi, giữ bản gốc và báo bước cần xác nhận trước khi chỉnh.” File gốc và kết quả để trong capcut-work/<tác-vụ>/; skill là bản hướng dẫn cố định. Cung cấp recording, người nói, mục tiêu, phụ đề/phong cách và phạm vi được chỉnh theo yêu cầu thực tế. Gói không có media riêng của người xây dựng; profile Nga chỉ là thông số phong cách tham số hóa, không là dữ liệu hay sự chấp nhận của client.

## Giới hạn đã biết

File, cài lặp và các phép xử lý giả được kiểm ở máy đóng gói. Nhận skill trong host của client, nghe nguồn thật, dựng/phát timeline và người nhận chấp thuận còn PENDING. Không bảo đảm mọi phiên bản CapCut hoặc mọi hệ điều hành. Xem source/skill/capcut-edit/references/portable-support.md và dependencies.md cho công cụ/gate của từng nhánh.
