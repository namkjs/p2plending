"""
OCR Tools sử dụng Mistral Vision API để OCR CCCD
"""

import os
import base64
import json
import re
from pathlib import Path
from typing import Dict, Any, Optional
from langchain.tools import tool
from django.conf import settings


def encode_image_to_base64(image_path: str) -> str:
    """Encode image file to base64 string"""
    with open(image_path, "rb") as image_file:
        return base64.standard_b64encode(image_file.read()).decode("utf-8")


def get_image_mime_type(image_path: str) -> str:
    """Get MIME type from image path"""
    ext = Path(image_path).suffix.lower()
    mime_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    return mime_types.get(ext, "image/jpeg")


def call_mistral_ocr(image_path: str, prompt: str) -> Dict[str, Any]:
    """
    Gọi Mistral Vision API để OCR ảnh
    """
    from mistralai import Mistral

    api_key = os.getenv("MISTRAL_API_KEY", "")
    if not api_key:
        return {"success": False, "error": "MISTRAL_API_KEY not configured"}

    client = Mistral(api_key=api_key)

    # Encode image
    base64_image = encode_image_to_base64(image_path)
    mime_type = get_image_mime_type(image_path)

    try:
        response = client.chat.complete(
            model="pixtral-12b-2409",  # Mistral vision model
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": f"data:{mime_type};base64,{base64_image}",
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )

        return {"success": True, "content": response.choices[0].message.content}

    except Exception as e:
        return {"success": False, "error": str(e)}


@tool("ocr_id_card_front")
def ocr_id_card_front(image_path: str) -> str:
    """
    OCR mặt trước CCCD/CMND Việt Nam sử dụng Mistral Vision.
    Trích xuất: số CCCD, họ tên, ngày sinh, giới tính, quê quán, địa chỉ.

    Args:
        image_path: Đường dẫn đến file ảnh CCCD mặt trước
    Returns:
        JSON string chứa thông tin OCR
    """
    prompt = """Đây là ảnh mặt trước CCCD/CMND Việt Nam. Hãy trích xuất CHÍNH XÁC các thông tin sau và trả về dạng JSON:

{
    "id_number": "Số CCCD/CMND (12 số)",
    "full_name": "Họ và tên đầy đủ",
    "date_of_birth": "Ngày sinh (DD/MM/YYYY)",
    "gender": "Giới tính (Nam/Nữ)",
    "nationality": "Quốc tịch",
    "hometown": "Quê quán",
    "address": "Nơi thường trú",
    "expiry_date": "Có giá trị đến (DD/MM/YYYY)"
}

CHỈ TRẢ VỀ JSON, KHÔNG GIẢI THÍCH. Nếu không đọc được trường nào, để giá trị là null."""

    result = call_mistral_ocr(image_path, prompt)

    if not result["success"]:
        return json.dumps(
            {"success": False, "error": result.get("error", "OCR failed")},
            ensure_ascii=False,
        )

    # Parse JSON từ response
    content = result["content"]
    try:
        # Tìm JSON trong response
        json_match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return json.dumps({"success": True, "data": data}, ensure_ascii=False)
        else:
            return json.dumps(
                {"success": True, "raw_text": content}, ensure_ascii=False
            )
    except json.JSONDecodeError:
        return json.dumps({"success": True, "raw_text": content}, ensure_ascii=False)


@tool("ocr_id_card_back")
def ocr_id_card_back(image_path: str) -> str:
    """
    OCR mặt sau CCCD/CMND Việt Nam sử dụng Mistral Vision.
    Trích xuất: ngày cấp, nơi cấp, đặc điểm nhận dạng.

    Args:
        image_path: Đường dẫn đến file ảnh CCCD mặt sau
    Returns:
        JSON string chứa thông tin OCR
    """
    prompt = """Đây là ảnh mặt sau CCCD/CMND Việt Nam. Hãy trích xuất CHÍNH XÁC các thông tin sau và trả về dạng JSON:

{
    "issue_date": "Ngày cấp (DD/MM/YYYY)",
    "issue_place": "Nơi cấp (CỤC TRƯỞNG CỤC CẢNH SÁT...)",
    "characteristics": "Đặc điểm nhận dạng",
    "mrz_line1": "Dòng MRZ thứ 1 (nếu có)",
    "mrz_line2": "Dòng MRZ thứ 2 (nếu có)",
    "mrz_line3": "Dòng MRZ thứ 3 (nếu có)"
}

CHỈ TRẢ VỀ JSON, KHÔNG GIẢI THÍCH. Nếu không đọc được trường nào, để giá trị là null."""

    result = call_mistral_ocr(image_path, prompt)

    if not result["success"]:
        return json.dumps(
            {"success": False, "error": result.get("error", "OCR failed")},
            ensure_ascii=False,
        )

    content = result["content"]
    try:
        json_match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return json.dumps({"success": True, "data": data}, ensure_ascii=False)
        else:
            return json.dumps(
                {"success": True, "raw_text": content}, ensure_ascii=False
            )
    except json.JSONDecodeError:
        return json.dumps({"success": True, "raw_text": content}, ensure_ascii=False)


@tool("verify_id_card_info")
def verify_id_card_info(user_input: str, ocr_data: str) -> str:
    """
    So sánh thông tin người dùng nhập với dữ liệu OCR từ CCCD.

    Args:
        user_input: JSON string chứa thông tin người dùng nhập
        ocr_data: JSON string chứa thông tin OCR từ CCCD
    Returns:
        Kết quả xác minh với điểm phù hợp
    """
    from langchain_groq import ChatGroq

    llm = ChatGroq(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        temperature=0,
        api_key=os.getenv("GROQ_API_KEY", ""),
    )

    prompt = f"""So sánh thông tin người dùng nhập với dữ liệu OCR từ CCCD và đánh giá độ phù hợp.

THÔNG TIN NGƯỜI DÙNG NHẬP:
{user_input}

THÔNG TIN OCR TỪ CCCD:
{ocr_data}

Hãy so sánh và trả về JSON:
{{
    "is_verified": true/false,
    "match_score": 0-100,
    "details": {{
        "full_name": {{"match": true/false, "user": "...", "ocr": "...", "reason": "..."}},
        "id_number": {{"match": true/false, "user": "...", "ocr": "...", "reason": "..."}},
        "date_of_birth": {{"match": true/false, "user": "...", "ocr": "...", "reason": "..."}},
        "gender": {{"match": true/false, "user": "...", "ocr": "...", "reason": "..."}},
        "address": {{"match": true/false, "user": "...", "ocr": "...", "reason": "..."}}
    }},
    "mismatches": ["field1", "field2"],
    "recommendation": "Khuyến nghị cho người dùng"
}}

Lưu ý:
- Tên có thể khác chữ hoa/thường, dấu câu
- Ngày sinh có thể format khác nhau (DD/MM/YYYY vs YYYY-MM-DD)
- Địa chỉ có thể viết tắt hoặc đầy đủ
- Match score >= 70 thì is_verified = true

CHỈ TRẢ VỀ JSON."""

    response = llm.invoke(prompt)
    return response.content


@tool("save_kyc_verification_result")
def save_kyc_verification_result(user_id: int, verification_result: str) -> str:
    """
    Lưu kết quả xác minh KYC vào database.

    Args:
        user_id: ID của user
        verification_result: JSON string kết quả xác minh
    Returns:
        Kết quả lưu
    """
    from user.models import UserProfile
    from django.contrib.auth.models import User
    import json

    try:
        user = User.objects.get(id=user_id)
        profile = UserProfile.objects.get(user=user)

        # Parse result
        try:
            result = json.loads(verification_result)
        except:
            # Try to extract JSON from string
            json_match = re.search(r"\{.*\}", verification_result, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                return "Không thể parse kết quả xác minh"

        # Update profile
        profile.ocr_verified = result.get("is_verified", False)
        profile.ocr_match_score = result.get("match_score", 0)
        profile.ocr_data = result

        if profile.ocr_verified and profile.ocr_match_score >= 70:
            profile.kyc_status = "VERIFIED"
            message = (
                f"KYC đã được xác thực thành công! Độ khớp: {profile.ocr_match_score}%"
            )
        else:
            profile.kyc_status = "REJECTED"
            mismatches = result.get("mismatches", [])
            recommendation = result.get("recommendation", "")
            profile.kyc_note = f"Không khớp: {', '.join(mismatches)}. {recommendation}"
            message = f"KYC bị từ chối. Độ khớp: {profile.ocr_match_score}%. Lý do: {profile.kyc_note}"

        profile.save()
        return message

    except User.DoesNotExist:
        return f"Không tìm thấy user với ID: {user_id}"
    except UserProfile.DoesNotExist:
        return f"Không tìm thấy profile của user ID: {user_id}"
    except Exception as e:
        return f"Lỗi lưu KYC: {str(e)}"


# Export tools
OCR_TOOLS = [
    ocr_id_card_front,
    ocr_id_card_back,
    verify_id_card_info,
    save_kyc_verification_result,
]
