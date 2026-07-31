import os
import sys
import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestImportPaths:
    """测试导入路径是否正确更新"""

    def test_main_py_has_correct_imports(self):
        """测试 main.py 中的导入是否正确"""
        try:
            with open("app/main.py", "r", encoding="utf-8") as f:
                content = f.read()
            
            # 检查新的导入路径
            assert "from app.agents.assistant import MedicalAssistant" in content, \
                "缺少新的 MedicalAssistant 导入"
            assert "from app.agents.orchestrators.qwen_agent import QwenAgent" in content, \
                "缺少新的 QwenAgent 导入"
            
            # 检查旧的导入路径已被移除
            assert "from app.agents.qwen.qwen_agent import qwenAgent" not in content, \
                "仍然存在旧的 qwenAgent 导入"
            assert "from app.agents.qwen.qwen_assistant import MedicalAssistant" not in content, \
                "仍然存在旧的 MedicalAssistant 导入"
            
            # 检查实例化代码
            assert "QwenAgent(" in content, \
                "缺少 QwenAgent 实例化"
            
            print("✅ main.py 导入路径已正确更新")
        except Exception as e:
            pytest.fail(f"❌ main.py 导入检查失败: {e}")

    def test_evaluation_runner_is_offline(self):
        """测试评估运行器不依赖新旧推理入口"""
        try:
            with open("app/evaluation/benchmark.py", "r", encoding="utf-8") as f:
                content = f.read()

            assert "def run_benchmark" in content
            assert "from app.agents" not in content

            print("✅ 离线评测器未耦合推理入口")
        except Exception as e:
            pytest.fail(f"❌ 离线评测器检查失败: {e}")

    def test_new_architecture_files_exist(self):
        """测试新架构文件是否存在"""
        required_files = [
            "app/agents/assistant.py",
            "app/agents/orchestrators/qwen_agent.py",
            "app/agents/orchestrators/clinical_graph.py",
            "app/agents/orchestrators/nodes/intent_node.py",
            "app/agents/orchestrators/nodes/analysis_node.py",
            "app/agents/orchestrators/nodes/retrieve_node.py",
            "app/agents/orchestrators/nodes/reason_node.py",
            "app/agents/orchestrators/nodes/report_node.py",
            "app/agents/services/query_service.py",
            "app/agents/services/retrieval_service.py",
            "app/agents/services/synthesis_service.py",
            "app/agents/pipelines/rag_pipeline.py",
            "app/agents/core/schema.py",
        ]
        
        missing_files = []
        for file_path in required_files:
            if not os.path.exists(file_path):
                missing_files.append(file_path)
        
        if missing_files:
            pytest.fail(f"❌ 缺少以下新架构文件:\n" + "\n".join(f"  - {f}" for f in missing_files))
        
        print(f"✅ 所有 {len(required_files)} 个新架构文件都存在")

    def test_old_architecture_files_status(self):
        """检查旧架构文件的状态"""
        old_files = {
            "app/agents/qwen/qwen_agent.py": "可以删除（功能已迁移）",
            "app/agents/qwen/qwen_assistant.py": "可以删除（功能已迁移）",
            "app/agents/qwen/medical_agent.py": "必须保留（新架构仍依赖）",
        }
        
        print("\n📋 旧架构文件状态:")
        for file_path, status in old_files.items():
            exists = os.path.exists(file_path)
            status_icon = "✅" if exists else "❌"
            print(f"  {status_icon} {file_path}: {status} ({'存在' if exists else '不存在'})")

    def test_file_syntax(self):
        """测试关键文件的语法是否正确"""
        files_to_check = [
            "app/main.py",
            "app/agents/assistant.py",
            "app/agents/orchestrators/qwen_agent.py",
        ]
        
        for file_path in files_to_check:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    code = f.read()
                compile(code, file_path, 'exec')
                print(f"✅ {file_path} 语法正确")
            except SyntaxError as e:
                pytest.fail(f"❌ {file_path} 语法错误: {e}")

    def test_no_remaining_old_imports(self):
        """检查是否还有其他文件使用了旧的导入"""
        files_to_check = [
            "app/main.py",
            "app/evaluation/benchmark.py",
        ]
        
        old_imports = [
            "from app.agents.qwen.qwen_agent import qwenAgent",
            "from app.agents.qwen.qwen_assistant import MedicalAssistant",
            "from app.agents.qwen.qwenAgent import qwenAgent",
        ]
        
        issues = []
        for file_path in files_to_check:
            if not os.path.exists(file_path):
                continue
                
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            for old_import in old_imports:
                if old_import in content:
                    issues.append(f"{file_path} 仍包含旧导入: {old_import}")
        
        if issues:
            pytest.fail("\n".join(f"❌ {issue}" for issue in issues))
        
        print("✅ 所有文件都已更新导入路径")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
