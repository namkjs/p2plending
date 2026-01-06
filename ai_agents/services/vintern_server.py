"""
Vintern 1B VLM Server - Host local để OCR ảnh CCCD
Chạy: python vintern_server.py
"""

import os
import base64
import io
import re
import json
from typing import Dict, Any

# Check for required packages
try:
    import torch
    from transformers import AutoModel, AutoTokenizer
    from PIL import Image
    from flask import Flask, request, jsonify
except ImportError as e:
    print(f"Missing package: {e}")
    print("Install with: pip install torch transformers pillow flask")
    exit(1)

app = Flask(__name__)

# Model config
MODEL_NAME = "5CD-AI/Vintern-1B-v2"
device = "cuda" if torch.cuda.is_available() else "cpu"

# Global model and tokenizer
model = None
tokenizer = None


def load_model():
    """Load Vintern 1B model"""
    global model, tokenizer

    print(f"Loading Vintern 1B model on {device}...")

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)

    model = AutoModel.from_pretrained(
        MODEL_NAME,
        trust_remote_code=True,
        torch_dtype=torch.float16 if device == "cuda" else torch.float32,
    ).to(device)

    model.eval()
    print("Model loaded successfully!")


def extract_id_card_info(image: Image.Image, doc_type: str) -> Dict[str, Any]:
    """Trích xuất thông tin từ ảnh CCCD"""

    if doc_type == "ID_CARD_FRONT":
        prompt = """Đây là ảnh mặt trước CCCD/CMND Việt Nam. Hãy trích xuất các thông tin sau và trả về dạng JSON:
- id_number: Số CCCD/CMND
- full_name: Họ và tên
- date_of_birth: Ngày sinh (DD/MM/YYYY)
- gender: Giới tính (Nam/Nữ)
- hometown: Quê quán
- address: Nơi thường trú

Chỉ trả về JSON, không giải thích."""
    else:
        prompt = """Đây là ảnh mặt sau CCCD/CMND Việt Nam. Hãy trích xuất các thông tin sau và trả về dạng JSON:
- issue_date: Ngày cấp (DD/MM/YYYY)
- issue_place: Nơi cấp

Chỉ trả về JSON, không giải thích."""

    try:
        # Generate response
        with torch.no_grad():
            response = model.chat(
                tokenizer, image, prompt, do_sample=False, max_new_tokens=512
            )

        # Parse JSON from response
        json_match = re.search(r"\{[^{}]*\}", response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        else:
            # Try to parse entire response
            return json.loads(response)

    except json.JSONDecodeError:
        # Extract info manually if JSON parsing fails
        return extract_manual(response, doc_type)
    except Exception as e:
        return {"error": str(e)}


def extract_manual(text: str, doc_type: str) -> Dict[str, Any]:
    """Trích xuất thông tin thủ công từ text"""
    result = {}

    if doc_type == "ID_CARD_FRONT":
        # Try to find patterns
        patterns = {
            "id_number": r"(?:số|id|cccd|cmnd)[:\s]*([0-9]{9,12})",
            "full_name": r"(?:họ.*tên|name)[:\s]*([A-ZÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴĐ\s]+)",
            "date_of_birth": r"(?:sinh|born|ngày sinh)[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{4})",
            "gender": r"(?:giới tính|sex)[:\s]*(nam|nữ|male|female)",
        }

        for field, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result[field] = match.group(1).strip()

    return result


@app.route("/ocr", methods=["POST"])
def ocr():
    """API endpoint để OCR ảnh CCCD"""
    try:
        data = request.json

        # Decode base64 image
        image_data = base64.b64decode(data["image"])
        image = Image.open(io.BytesIO(image_data)).convert("RGB")

        doc_type = data.get("doc_type", "ID_CARD_FRONT")

        # Extract info
        result = extract_id_card_info(image, doc_type)

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint"""
    return jsonify({"status": "ok", "model": MODEL_NAME, "device": device})


if __name__ == "__main__":
    # Load model on startup
    load_model()

    # Run server
    port = int(os.getenv("VINTERN_PORT", 8001))
    print(f"Starting Vintern OCR server on port {port}...")
    app.run(host="0.0.0.0", port=port, debug=False)
