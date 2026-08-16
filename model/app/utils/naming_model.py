import os
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)


class NamingModel(object):
    def __init__(self, llm=None):
        if llm is not None:
            self.llm = llm
        else:
            api_key = os.environ.get("DASHSCOPE_API_KEY")
            if not api_key:
                raise ValueError("未找到环境变量 DASHSCOPE_API_KEY，请设置该环境变量")
            self.llm = ChatOpenAI(
                model="qwen-turbo",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                api_key=api_key,
                temperature=0.3,
                max_tokens=300,
                timeout=25,
                extra_body={"enable_thinking": False},
                stream_usage=True,
            )

    def run_naming(self, question, answer=None, max_title_len: int = 12):
        """
        基于用户问题(及可选 AI 回答)生成简短医学标题。

        Args:
            question: 用户提问文本
            answer: 可选，AI 回答摘要，用于提炼更准确的标题
            max_title_len: 标题最大长度(字符)

        Returns:
            生成的标题字符串
        """
        logger.info(f"开始执行 run_naming() 方法，待处理内容: {question}")
        try:
            # 结合回答内容能生成更准确的标题(如"急性脑梗死"而非问题原文截断)
            content = question
            if answer and answer.strip():
                content = f"问题：{question}\n回答摘要：{answer.strip()[:300]}"
            response = self.llm.invoke([
                SystemMessage(
                    content=(
                        f"你是一位专业医学取标题人员。请根据用户提问和 AI 回答内容，"
                        f"用简洁的医学术语概括对话主题，生成一个简短标题，"
                        f"长度控制在 4-{max_title_len} 个汉字内。"
                        f"只输出标题本身，不要加引号、标点或其他符号。"
                    ),
                ),
                HumanMessage(content=f"请为以下医学对话生成简洁标题：\n{content}")
            ])
            result = response.content.strip().strip('"').strip("'").strip("《》")
            if not result:
                result = self._fallback_title(question, max_title_len)
            logger.info(f"生成标题结果: {result}")
            return result
        except Exception as e:
            logger.error(f"生成标题时发生错误: {str(e)}")
            return self._fallback_title(question, max_title_len)

    @staticmethod
    def _fallback_title(question, max_title_len: int = 12):
        if not question:
            return "新对话"
        stripped = question.strip()
        if len(stripped) <= max_title_len:
            return stripped
        return stripped[:max_title_len] + "..."


if __name__ == '__main__':
    nm = NamingModel()
    question = "我头疼，想知道是否有什么办法可以解决。"
    result = nm.run_naming(question)
    print(result)