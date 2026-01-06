"""
Vintern OCR Service - Sử dụng VLM Vintern 1B để OCR ảnh CCCD
"""

import os
import base64
import requests
from typing import Dict, Any, Optional
from django.conf import settings


class VinternOCRService:
    """Service để OCR ảnh CCCD sử dụng Vintern 1B VLM"""

    def __init__(self):
        # URL của Vintern service (có thể host local hoặc remote)
        self.vintern_url = os.getenv("VINTERN_API_URL", "http://localhost:8001/ocr")
        self.timeout = 60  # seconds

    def extract_id_card_front(self, image_path: str) -> Dict[str, Any]:
        """
        OCR mặt trước CCCD

        Returns:
            {
                "id_number": "001234567890",
                "full_name": "NGUYỄN VĂN A",
                "date_of_birth": "01/01/1990",
                "gender": "Nam",
                "hometown": "Hà Nội",
                "address": "123 Đường ABC, Quận XYZ",
                "expiry_date": "01/01/2030"
            }
        """
        return self._call_vintern_api(image_path, "ID_CARD_FRONT")

    def extract_id_card_back(self, image_path: str) -> Dict[str, Any]:
        """
        OCR mặt sau CCCD

        Returns:
            {
                "issue_date": "01/01/2020",
                "issue_place": "CỤC TRƯỞNG CỤC CẢNH SÁT...",
                "characteristics": "Nốt ruồi...",
            }
        """
        return self._call_vintern_api(image_path, "ID_CARD_BACK")

    def _call_vintern_api(self, image_path: str, doc_type: str) -> Dict[str, Any]:
        """Gọi API Vintern để OCR"""
        try:
            # Đọc và encode ảnh
            with open(image_path, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode("utf-8")

            # Gọi API
            response = requests.post(
                self.vintern_url,
                json={"image": image_base64, "doc_type": doc_type},
                timeout=self.timeout,
            )

            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "error": f"API error: {response.status_code}"}

        except requests.exceptions.ConnectionError:
            # Fallback: sử dụng mock data nếu Vintern service không available
            return self._mock_ocr(doc_type)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _mock_ocr(self, doc_type: str) -> Dict[str, Any]:
        """Mock OCR data khi Vintern service không available"""
        if doc_type == "ID_CARD_FRONT":
            return {
                "success": True,
                "data": {
                    "id_number": "",
                    "full_name": "",
                    "date_of_birth": "",
                    "gender": "",
                    "hometown": "",
                    "address": "",
                },
                "is_mock": True,
            }
        else:
            return {
                "success": True,
                "data": {
                    "issue_date": "",
                    "issue_place": "",
                },
                "is_mock": True,
            }

    def verify_user_info(self, user_data: Dict, ocr_data: Dict) -> Dict[str, Any]:
        """
        So sánh thông tin user nhập với OCR data

        Args:
            user_data: Thông tin user tự nhập
            ocr_data: Thông tin OCR từ CCCD

        Returns:
            {
                "is_verified": True/False,
                "match_score": 85.5,
                "details": {
                    "full_name": {"match": True, "score": 100},
                    "id_number": {"match": True, "score": 100},
                    ...
                },
                "mismatches": ["field1", "field2"]
            }
        """
        from ai_agents.agents.base import BaseAgent
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import JsonOutputParser

        agent = BaseAgent.__subclasses__()[0]()  # Get any agent for LLM

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """Bạn là chuyên gia xác minh danh tính. So sánh thông tin người dùng nhập với dữ liệu OCR từ CCCD.
            
Lưu ý:
- Tên có thể khác chữ hoa/thường, dấu
- Địa chỉ có thể viết tắt hoặc đầy đủ
- Ngày sinh có thể format khác nhau

Trả về JSON:
{
    "is_verified": true/false,
    "match_score": <0-100>,
    "details": {
        "full_name": {"match": true/false, "score": <0-100>, "reason": "lý do"},
        "id_number": {"match": true/false, "score": <0-100>, "reason": "lý do"},
        "date_of_birth": {"match": true/false, "score": <0-100>, "reason": "lý do"},
        "gender": {"match": true/false, "score": <0-100>, "reason": "lý do"},
        "address": {"match": true/false, "score": <0-100>, "reason": "lý do"}
    },
    "mismatches": ["field1", "field2"],
    "recommendation": "khuyến nghị"
}""",
                ),
                (
                    "human",
                    """So sánh thông tin:

THÔNG TIN NGƯỜI DÙNG NHẬP:
{user_data}

THÔNG TIN OCR TỪ CCCD:
{ocr_data}""",
                ),
            ]
        )

        chain = prompt | agent._get_llm() | JsonOutputParser()

        try:
            result = chain.invoke(
                {"user_data": str(user_data), "ocr_data": str(ocr_data)}
            )
            return result
        except Exception as e:
            return {"is_verified": False, "match_score": 0, "error": str(e)}


# Singleton instance
vintern_ocr = VinternOCRService()
