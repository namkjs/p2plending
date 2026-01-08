import time
from typing import Dict, Any, List
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from .base import BaseAgent
from ai_agents.models import ChatSession, ChatMessage


class ChatbotAgent(BaseAgent):
    """
    Agent Chatbot Q&A
    - Sử dụng history từ database
    - Trả lời câu hỏi người dùng dựa trên prompt thiết kế
    """

    agent_type = "CHATBOT"

    system_prompt = """Bạn là trợ lý ảo AI của nền tảng P2P Lending.
Tên của bạn là "Lending Bot".

Mục tiêu:
Chỉ trả lời các câu hỏi liên quan đến:
1) Điều khoản & điều kiện sử dụng (Terms)
2) Chính sách vay/nợ và quy định trả nợ
3) Các khái niệm khi vay: lãi suất, phí, kỳ hạn, lịch trả nợ, gốc/lãi, dư nợ, tất toán, gia hạn, phạt chậm trả, phí phạt, lãi quá hạn, ngày đến hạn, ân hạn (nếu có), quy trình nhắc nợ, xử lý nợ quá hạn, tranh chấp liên quan đến hợp đồng vay.

Phạm vi KHÔNG hỗ trợ (phải từ chối):
- Hướng dẫn kỹ thuật (lỗi hệ thống, API, migrate, database, devops, code)
- Tư vấn pháp lý cá nhân, tư vấn tài chính cá nhân, cam kết lợi nhuận
- Các Agent AI/kiến trúc hệ thống (Profiler/Matcher/Monitor...) nếu không liên quan trực tiếp đến chính sách/điều khoản.

Quy tắc trả lời:
- Trả lời bằng tiếng Việt, thân thiện, chuyên nghiệp, ngắn gọn.
- Không bịa thông tin. Nếu thiếu dữ liệu/không chắc chắn, hãy nói rõ “mình chưa có thông tin chính xác”.
- Không đưa ra lời khuyên pháp lý/tài chính cá nhân. Chỉ giải thích khái niệm và chính sách ở mức thông tin chung.
- Khi câu hỏi ngoài phạm vi: lịch sự từ chối và hướng dẫn liên hệ support theo số điện thoại "0966666666".

Mẫu từ chối ngoài phạm vi:
“Câu hỏi này nằm ngoài phạm vi hỗ trợ của Lending Bot (mình chỉ hỗ trợ điều khoản/chính sách vay và các khái niệm khi vay). Bạn vui lòng liên hệ bộ phận hỗ trợ qua [kênh support] để được giúp nhé.”

Thông tin nền tảng (để tham chiếu chung):
- P2P Lending kết nối trực tiếp người vay và người cho vay.
- Hợp đồng được tạo tự động và ký số.
- Các chính sách cụ thể (lãi suất/biểu phí/phạt) phụ thuộc vào điều khoản hiện hành của nền tảng.
"""

    def process(self, message: str, user, session_id: int = None) -> Dict[str, Any]:
        """
        Xử lý tin nhắn chat
        """
        start_time = time.time()
        
        # Determine session
        if session_id:
            try:
                session = ChatSession.objects.get(id=session_id, user=user)
            except ChatSession.DoesNotExist:
                return {"success": False, "error": "Session not found"}
        else:
            # Get latest active session or create new
            session = ChatSession.objects.filter(user=user, is_active=True).first()
            if not session:
                session = ChatSession.objects.create(user=user, title=message[:50])

        input_data = {
            "message": message,
            "user_id": user.id,
            "session_id": session.id
        }
        
        log = self._log_start(user, input_data)

        try:
            # 1. Save user message
            ChatMessage.objects.create(
                session=session,
                role="user",
                content=message
            )

            # 2. Retrieve history (last 10 messages, effectively 5 pairs)
            # Use negative slicing on ordered queryset might be inefficient in some DBs without reverse ordering first
            # We want the LAST 10 inserted messages, then ordered chronologically.
            history_msgs = ChatMessage.objects.filter(session=session).order_by("-created_at")[:10]
            history_msgs = reversed(history_msgs)  # Reverse back to chronological order

            
            chat_history = []
            for msg in history_msgs:
                if msg.role == "user":
                    chat_history.append(HumanMessage(content=msg.content))
                elif msg.role == "assistant":
                    chat_history.append(AIMessage(content=msg.content))
            
            # 3. generate response
            llm = self._get_llm()
            
            prompt = ChatPromptTemplate.from_messages([
                ("system", self.system_prompt),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{input}"),
            ])
            
            chain = prompt | llm
            
            response = chain.invoke({
                "chat_history": chat_history,
                "input": message
            })
            
            bot_reply = response.content

            # 4. Save bot message
            ChatMessage.objects.create(
                session=session,
                role="assistant",
                content=bot_reply
            )
            
            # Update session timestamp
            session.save()

            result = {
                "response": bot_reply,
                "session_id": session.id
            }

            self._log_success(log, result, start_time)
            return {"success": True, "data": result}

        except Exception as e:
            self._log_failure(log, str(e), start_time)
            return {"success": False, "error": str(e)}

    def get_history(self, user, session_id: int = None) -> List[Dict]:
        """Lấy lịch sử chat"""
        if session_id:
            qs = ChatMessage.objects.filter(session__id=session_id, session__user=user)
        else:
            # Latest session
            session = ChatSession.objects.filter(user=user).order_by("-updated_at").first()
            if not session:
                return []
            qs = ChatMessage.objects.filter(session=session)
            
        return [
            {
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at.isoformat()
            }
            for msg in qs.order_by("created_at")
        ]
