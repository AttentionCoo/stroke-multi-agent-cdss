import httpx; import openai; client = openai.OpenAI(api_key='sk-26c638a2564d4b44833e4866365a56c9', base_url='https://dashscope.aliyuncs.com/compatible-mode/v1', http_client=httpx.Client(event_hooks={'request': [lambda r: print(r.url, r.headers.get('authorization'))]}));
try:
  client.chat.completions.create(model='qwen-turbo', messages=[{'role': 'user', 'content': 'hi'}])
except Exception as e:
  print(e)
