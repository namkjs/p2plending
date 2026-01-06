"""
Base Agent class for all AI Agents in P2P Lending Platform
Tham khảo từ Fintech project - sử dụng langchain.agents.create_agent
"""

import os
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List
from django.utils import timezone

from langchain_groq import ChatGroq
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, AIMessage


def get_llm():
    """Get LLM instance - using Groq"""
    return ChatGroq(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        temperature=0.3,
        api_key=os.getenv("GROQ_API_KEY", ""),
    )


class BaseAgent(ABC):
    """Base class for all AI Agents"""

    agent_type: str = "BASE"
    system_prompt: str = "Bạn là AI Agent hỗ trợ nền tảng P2P Lending."
    tools: List = []

    def __init__(self):
        self._agent = None
        self._llm = None

    def _get_llm(self):
        """Get LLM instance"""
        if not self._llm:
            self._llm = get_llm()
        return self._llm

    def _create_agent(self):
        """Create agent using langchain.agents.create_agent"""
        if not self._agent:
            self._agent = create_agent(
                self._get_llm(),
                self.tools,
                system_prompt=self.system_prompt,
            )
        return self._agent

    def invoke(
        self, input_text: str, chat_history: List = None, user_id: int = None
    ) -> tuple:
        """
        Invoke the agent with input - tham khảo từ Fintech transaction.py

        Args:
            input_text: User input
            chat_history: Optional chat history (list of HumanMessage/AIMessage)
            user_id: Optional user ID to include in context

        Returns:
            Tuple of (response_content, updated_chat_history)
        """
        agent = self._create_agent()

        if chat_history is None:
            chat_history = []

        # Nếu là tin nhắn đầu tiên và có user_id, thêm context
        if not chat_history and user_id:
            user_text = f"[user_id={user_id}] {input_text}"
        else:
            user_text = input_text

        # Thêm câu hỏi mới vào history
        chat_history.append(HumanMessage(content=user_text))

        # Gọi Agent
        result = agent.invoke({"messages": chat_history})

        # Lấy phản hồi từ Agent (AIMessage)
        ai_response = result["messages"][-1]

        # Cập nhật history với phản hồi của AI
        chat_history.append(ai_response)

        return ai_response.content, chat_history

    def ask(self, question: str, user_id: int = None, chat_history: List = None) -> str:
        """
        Simple ask method - returns only response content

        Args:
            question: User question
            user_id: Optional user ID
            chat_history: Optional chat history

        Returns:
            Response string
        """
        response, _ = self.invoke(question, chat_history, user_id)
        return response

    @abstractmethod
    def process(self, *args, **kwargs) -> Dict[str, Any]:
        """
        Main processing method - to be implemented by subclasses
        """
        pass

    def _log_start(self, user, input_data: Dict) -> Any:
        """Log start of agent execution"""
        from ai_agents.models import AgentLog

        log = AgentLog.objects.create(
            agent_type=self.agent_type,
            user=user,
            input_data=input_data,
            status="PROCESSING",
        )
        return log

    def _log_success(self, log, output_data: Dict, start_time: float):
        """Log successful execution"""
        log.output_data = output_data
        log.status = "SUCCESS"
        log.execution_time = time.time() - start_time
        log.save()

    def _log_failure(self, log, error_message: str, start_time: float):
        """Log failed execution"""
        log.output_data = {"error": error_message}
        log.status = "FAILED"
        log.execution_time = time.time() - start_time
        log.save()

    def _create_notification(
        self,
        user,
        notification_type: str,
        title: str,
        message: str,
        related_loan_id: int = None,
    ):
        """Create notification for user"""
        from ai_agents.models import Notification

        Notification.objects.create(
            user=user,
            notification_type=notification_type,
            title=title,
            message=message,
            related_loan_id=related_loan_id,
        )
