import os
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

os.environ['OPENAI_API_KEY'] = 'sk-26c638a2564d4b44833e4866365a56c9'
llm = ChatOpenAI(model='qwen-turbo', base_url='https://dashscope.aliyuncs.com/compatible-mode/v1')
print(llm.invoke([HumanMessage(content='hello')]))
