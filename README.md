# Hệ thống cho vay ngang hàng (P2P Lending)

Dự án hệ thống cho vay ngang hàng được xây dựng trên Django Framework, sử dụng AI Agent để hỗ trợ quá trình đánh giá và kết nối giữa người cho vay và người đi vay.

## Tính năng chính

- Đăng ký và xác thực người dùng (KYC)
- Tạo và quản lý khoản vay
- Hệ thống AI đánh giá hồ sơ người đi vay
- Tự động ghép nối người cho vay và người đi vay
- Theo dõi thanh toán
- Giải quyết tranh chấp
- Xử lý OCR cho tài liệu

## Cài đặt

1. Clone dự án về máy
2. Tạo môi trường ảo:
   ```
   python -m venv fintech
   fintech\Scripts\activate
   ```
3. Cài đặt thư viện:
   ```
   pip install -r requirements.txt
   ```
4. Tạo database:
   ```
   python manage.py migrate
   ```
5. Chạy server:
   ```
   python manage.py runserver
   ```

## Cấu trúc dự án

- `ai_agents/` - Các AI agent hỗ trợ đánh giá và kết nối
- `lending/` - Quản lý khoản vay và tranh chấp  
- `user/` - Quản lý người dùng và KYC
- `templates/` - Giao diện web
- `static/` - File tĩnh (CSS, JS, hình ảnh)
- `media/` - File upload từ người dùng

## Công nghệ sử dụng

- Django 5.2.9
- SQLite Database
- LangChain cho AI
- Groq API
- OCR để xử lý tài liệu

## Liên hệ

Dự án được phát triển để hỗ trợ việc cho vay ngang hàng an toàn và hiệu quả.
