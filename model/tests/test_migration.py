import os
import sys
import pytest
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from typing import AsyncGenerator

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestArchitectureMigration:
    """测试架构迁移是否成功"""

    def test_medical_assistant_import(self):
        """测试新的 MedicalAssistant 导入路径"""
        try:
            from app.agents.assistant import MedicalAssistant
            assert MedicalAssistant is not None
            print("✅ MedicalAssistant 导入成功")
        except ImportError as e:
            pytest.fail(f"❌ MedicalAssistant 导入失败: {e}")

    def test_qwen_agent_import(self):
        """测试新的 QwenAgent 导入路径"""
        try:
            from app.agents.orchestrators.qwen_agent import QwenAgent
            assert QwenAgent is not None
            print("✅ QwenAgent 导入成功")
        except ImportError as e:
            pytest.fail(f"❌ QwenAgent 导入失败: {e}")

    def test_old_qwen_agent_import_fails(self):
        """测试旧的 qwenAgent 导入应该失败或被弃用"""
        try:
            from app.agents.qwen.qwen_agent import qwenAgent
            print("⚠️ 旧的 qwenAgent 仍然可以导入，建议删除旧文件")
        except ImportError:
            print("✅ 旧的 qwenAgent 已无法导入，迁移成功")

    def test_old_qwen_assistant_import_fails(self):
        """测试旧的 MedicalAssistant 导入应该失败或被弃用"""
        try:
            from app.agents.qwen.qwen_assistant import MedicalAssistant as OldMedicalAssistant
            print("⚠️ 旧的 MedicalAssistant 仍然可以导入，建议删除旧文件")
        except ImportError:
            print("✅ 旧的 MedicalAssistant 已无法导入，迁移成功")

    def test_main_py_imports(self):
        """测试 main.py 中的导入是否正确"""
        try:
            with open("app/main.py", "r", encoding="utf-8") as f:
                content = f.read()
            
            assert "from app.agents.assistant import MedicalAssistant" in content
            assert "from app.agents.orchestrators.qwen_agent import QwenAgent" in content
            assert "from app.agents.qwen.qwen_agent import qwenAgent" not in content
            assert "from app.agents.qwen.qwen_assistant import MedicalAssistant" not in content
            
            print("✅ main.py 导入路径已正确更新")
        except Exception as e:
            pytest.fail(f"❌ main.py 导入检查失败: {e}")

    def test_evaluation_runner_is_offline(self):
        """测试离线评测器不依赖推理智能体"""
        try:
            with open("app/evaluation/benchmark.py", "r", encoding="utf-8") as f:
                content = f.read()

            assert "def run_benchmark" in content
            assert "from app.agents" not in content

            print("✅ 离线评测器与推理智能体保持隔离")
        except Exception as e:
            pytest.fail(f"❌ 离线评测器检查失败: {e}")

    def test_new_architecture_structure(self):
        """测试新架构的目录结构"""
        required_dirs = [
            "app/agents/orchestrators",
            "app/agents/orchestrators/nodes",
            "app/agents/services",
            "app/agents/pipelines",
            "app/agents/core"
        ]
        
        for dir_path in required_dirs:
            if not os.path.exists(dir_path):
                pytest.fail(f"❌ 缺少必需的目录: {dir_path}")
        
        print("✅ 新架构目录结构完整")

    def test_old_architecture_files_exist(self):
        """检查旧架构文件是否仍然存在"""
        old_files = [
            "app/agents/qwen/qwen_agent.py",
            "app/agents/qwen/qwen_assistant.py"
        ]
        
        existing_old_files = []
        for file_path in old_files:
            if os.path.exists(file_path):
                existing_old_files.append(file_path)
        
        if existing_old_files:
            print(f"⚠️ 以下旧架构文件仍然存在，建议在确认迁移完成后删除:")
            for f in existing_old_files:
                print(f"  - {f}")
        else:
            print("✅ 旧架构文件已清理")


class TestMedicalAssistantInterface:
    """测试 MedicalAssistant 接口兼容性"""

    def test_medical_assistant_methods_exist(self):
        """测试 MedicalAssistant 是否有必需的方法"""
        try:
            from app.agents.assistant import MedicalAssistant
            
            required_methods = [
                'afast_parallel_retrieve',
                'stream_fast_response',
                'stream_final_report'
            ]
            
            for method in required_methods:
                assert hasattr(MedicalAssistant, method), f"缺少方法: {method}"
            
            print("✅ MedicalAssistant 接口完整")
        except Exception as e:
            pytest.fail(f"❌ MedicalAssistant 接口检查失败: {e}")


class TestQwenAgentInterface:
    """测试 QwenAgent 接口兼容性"""

    def test_qwen_agent_methods_exist(self):
        """测试 QwenAgent 是否有必需的方法"""
        try:
            from app.agents.orchestrators.qwen_agent import QwenAgent
            
            required_methods = [
                'run_clinical_reasoning',
                'analyze_patient_risk_fast'
            ]
            
            for method in required_methods:
                assert hasattr(QwenAgent, method), f"缺少方法: {method}"
            
            print("✅ QwenAgent 接口完整")
        except Exception as e:
            pytest.fail(f"❌ QwenAgent 接口检查失败: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
