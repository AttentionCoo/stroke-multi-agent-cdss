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
            )

    def run_naming(self, question):
        logger.info(f"开始执行 run_naming() 方法，待处理内容: {question}")
        try:
            response = self.llm.invoke([
                SystemMessage(
                    content="你是一位专业医学取标题人员，请将输入文本准确生成简短标题，标题长度控制在5-10个汉字内。只输出标题本身，不要加引号或其他符号。"),
                HumanMessage(content=f"请将以下内容生成简洁的医学标题：\n{question}")
            ])
            result = response.content.strip().strip('"').strip("'").strip("《》")
            if not result:
                result = self._fallback_title(question)
            logger.info(f"生成标题结果: {result}")
            return result
        except Exception as e:
            logger.error(f"生成标题时发生错误: {str(e)}")
            return self._fallback_title(question)

    @staticmethod
    def _fallback_title(question):
        if not question:
            return "新对话"
        stripped = question.strip()
        if len(stripped) <= 10:
            return stripped
        return stripped[:10] + "..."


if __name__ == '__main__':
    nm = NamingModel()
    question = "我头疼，想知道是否有什么办法可以解决。"
    result = nm.run_naming(question)
    print(result)