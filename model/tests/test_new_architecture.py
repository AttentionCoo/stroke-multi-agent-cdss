import os
import sys
import pytest
from unittest.mock import Mock, AsyncMock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.assistant import MedicalAssistant
from app.agents.orchestrators.qwen_agent import QwenAgent
from app.agents.core.schema import ClinicalState
from app.config.config_loader import PromptManager, ReportTemplateManager


@pytest.fixture
def mock_llm():
    """创建模拟的 LLM"""
    llm = Mock()
    async def empty_stream(_messages):
        if False:
            yield None

    llm.astream = empty_stream
    llm.ainvoke = AsyncMock()
    llm.invoke = Mock()
    return llm


@pytest.fixture
def mock_retriever():
    """创建模拟的检索器"""
    retriever = Mock()
    retriever.search = Mock(return_value=[])
    return retriever


@pytest.fixture
def mock_prompt_manager():
    """创建模拟的提示管理器"""
    manager = Mock(spec=PromptManager)
    manager.get = Mock(return_value=None)
    return manager


@pytest.fixture
def mock_report_manager():
    """创建模拟的报告管理器"""
    manager = Mock(spec=ReportTemplateManager)
    manager.system_role = "你是三甲医院神经内科主任医师。"
    manager.get_template = Mock(return_value="模板内容")
    manager.get_template_name = Mock(return_value="急诊模式")
    return manager


class TestMedicalAssistant:
    """测试 MedicalAssistant 类"""

    def test_init(self, mock_llm, mock_retriever, mock_prompt_manager, mock_report_manager):
        """测试初始化"""
        assistant = MedicalAssistant(
            llm_main=mock_llm,
            llm_fast=mock_llm,
            retriever=mock_retriever,
            prompt_manager=mock_prompt_manager,
            report_manager=mock_report_manager
        )
        assert assistant.llm == mock_llm
        assert assistant.llm_fast == mock_llm
        assert assistant.retriever == mock_retriever
        assert assistant.prompts == mock_prompt_manager
        assert assistant.reports == mock_report_manager

    @pytest.mark.asyncio
    async def test_fast_parallel_retrieve_empty_questions(self, mock_llm, mock_retriever, mock_prompt_manager, mock_report_manager):
        """测试空问题列表的并行检索"""
        assistant = MedicalAssistant(
            llm_main=mock_llm,
            llm_fast=mock_llm,
            retriever=mock_retriever,
            prompt_manager=mock_prompt_manager,
            report_manager=mock_report_manager
        )
        result = await assistant.afast_parallel_retrieve([])
        assert result == ""

    @pytest.mark.asyncio
    async def test_stream_fast_response(self, mock_llm, mock_retriever, mock_prompt_manager, mock_report_manager):
        """测试流式快速响应"""
        assistant = MedicalAssistant(
            llm_main=mock_llm,
            llm_fast=mock_llm,
            retriever=mock_retriever,
            prompt_manager=mock_prompt_manager,
            report_manager=mock_report_manager
        )
        
        mock_chunk = Mock()
        mock_chunk.content = "测试响应"
        async def response_stream(_messages):
            yield mock_chunk

        mock_llm.astream = response_stream
        
        result = []
        async for chunk in assistant.stream_fast_response("测试病例"):
            result.append(chunk)
        
        assert len(result) > 0
        assert "测试响应" in result


class TestQwenAgent:
    """测试 QwenAgent 类"""

    def test_init(self, mock_llm, mock_retriever, mock_prompt_manager, mock_report_manager):
        """测试初始化"""
        medical_assistant = MedicalAssistant(
            llm_main=mock_llm,
            llm_fast=mock_llm,
            retriever=mock_retriever,
            prompt_manager=mock_prompt_manager,
            report_manager=mock_report_manager
        )
        
        agent = QwenAgent(
            llm_proposer=mock_llm,
            llm_critic=mock_llm,
            medical_assistant=medical_assistant,
            prompt_manager=mock_prompt_manager,
            report_manager=mock_report_manager
        )
        
        assert agent.llm_proposer == mock_llm
        assert agent.llm_critic == mock_llm
        assert agent.medical_assistant == medical_assistant
        assert agent.prompts == mock_prompt_manager
        assert agent.reports == mock_report_manager

    @pytest.mark.asyncio
    async def test_run_clinical_reasoning(self, mock_llm, mock_retriever, mock_prompt_manager, mock_report_manager):
        """测试临床推理流程"""
        medical_assistant = MedicalAssistant(
            llm_main=mock_llm,
            llm_fast=mock_llm,
            retriever=mock_retriever,
            prompt_manager=mock_prompt_manager,
            report_manager=mock_report_manager
        )
        
        agent = QwenAgent(
            llm_proposer=mock_llm,
            llm_critic=mock_llm,
            medical_assistant=medical_assistant,
            prompt_manager=mock_prompt_manager,
            report_manager=mock_report_manager
        )
        
        events = []
        async for event in agent.run_clinical_reasoning(
            case_text="测试病例",
            all_info="",
            report_mode="emergency",
            show_thinking=True
        ):
            events.append(event)
        
        assert len(events) > 0

    @pytest.mark.asyncio
    async def test_analyze_patient_risk_fast(self, mock_llm, mock_retriever, mock_prompt_manager, mock_report_manager):
        """测试快速患者风险分析"""
        medical_assistant = MedicalAssistant(
            llm_main=mock_llm,
            llm_fast=mock_llm,
            retriever=mock_retriever,
            prompt_manager=mock_prompt_manager,
            report_manager=mock_report_manager
        )
        
        agent = QwenAgent(
            llm_proposer=mock_llm,
            llm_critic=mock_llm,
            medical_assistant=medical_assistant,
            prompt_manager=mock_prompt_manager,
            report_manager=mock_report_manager
        )
        
        mock_response = Mock()
        mock_response.content = '{"riskLevel": "高风险", "suggestion": "建议立即就医", "analysisDetails": "症状严重"}'
        mock_llm.ainvoke.return_value = mock_response
        
        result = await agent.analyze_patient_risk_fast("患者男，65岁，高血压")
        
        assert "riskLevel" in result
        assert "suggestion" in result
        assert "analysisDetails" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
