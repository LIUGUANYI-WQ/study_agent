import json
import datetime
import schedule
import time
import os
import sys
from dotenv import load_dotenv
from openai import OpenAI

# 加载环境变量
load_dotenv()
API_KEY = os.getenv("ZHIPU_API_KEY")
MEMORY_FILE = "study_memory.json"

# ========== 1. 记忆模块：长期记忆持久化 ==========
def init_memory():
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        init_data = {"tasks": [], "daily_record": {}}
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(init_data, f, ensure_ascii=False, indent=2)
        return init_data

def save_memory(data):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

memory_data = init_memory()

# ========== 短期记忆：滑动窗口 ==========
MAX_HISTORY_ROUNDS = 5
chat_history = []

def clean_surrogates(text):
    """清除字符串中的 UTF-8 代理字符（surrogate），防止编码错误"""
    return text.encode("utf-8", errors="replace").decode("utf-8")

def trim_history():
    """滑动窗口：超出最大轮数时丢弃最早的对话"""
    max_messages = MAX_HISTORY_ROUNDS * 2
    if len(chat_history) > max_messages:
        excess = len(chat_history) - max_messages
        del chat_history[:excess]

# ========== 2. 工具模块：时间、任务操作 ==========
def get_now_date():
    return datetime.datetime.now().strftime("%Y-%m-%d")

def get_yesterday_date():
    yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
    return yesterday.strftime("%Y-%m-%d")

def add_task(task_name, deadline):
    new_task = {
        "task": task_name,
        "deadline": deadline,
        "status": "未完成",
        "review_count": 0,
        "create_time": get_now_date()
    }
    memory_data["tasks"].append(new_task)
    save_memory(memory_data)
    return f"任务添加成功：{task_name}，截止日期：{deadline}"

def record_daily_content(content):
    today = get_now_date()
    memory_data["daily_record"][today] = content
    save_memory(memory_data)
    return f"已记录今日学习内容：{content}"

def get_tasks():
    """获取所有任务列表"""
    return json.dumps(memory_data["tasks"], ensure_ascii=False)

def get_daily_record(date_str=None):
    """获取指定日期的学习记录，默认今天"""
    if date_str is None:
        date_str = get_now_date()
    content = memory_data["daily_record"].get(date_str, f"{date_str} 无学习记录")
    return content

# ========== 3. Function Calling 工具定义 ==========
tools = [
    {
        "type": "function",
        "function": {
            "name": "add_task",
            "description": "添加一个新的学习任务",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_name": {
                        "type": "string",
                        "description": "任务名称"
                    },
                    "deadline": {
                        "type": "string",
                        "description": "截止日期，格式 YYYY-MM-DD"
                    }
                },
                "required": ["task_name", "deadline"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "record_daily_content",
            "description": "记录今日学习内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "学习内容描述"
                    }
                },
                "required": ["content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_tasks",
            "description": "获取当前所有学习任务列表",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_daily_record",
            "description": "获取指定日期的学习记录",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_str": {
                        "type": "string",
                        "description": "日期，格式 YYYY-MM-DD，不填则默认今天"
                    }
                }
            }
        }
    }
]

# 工具名 → 函数映射
tool_map = {
    "add_task": add_task,
    "record_daily_content": record_daily_content,
    "get_tasks": get_tasks,
    "get_daily_record": get_daily_record,
}

# ========== 4. LLM + 规划模块 ==========
client = OpenAI(
    api_key=API_KEY,
    base_url="https://open.bigmodel.cn/api/paas/v4"
)

def execute_tool_call(tool_call):
    """执行单个工具调用"""
    func_name = tool_call.function.name
    func_args = json.loads(tool_call.function.arguments)

    if func_name not in tool_map:
        return f"错误：未知工具 {func_name}"

    func = tool_map[func_name]
    try:
        result = func(**func_args)
        return result
    except Exception as e:
        return f"工具执行错误：{e}"

def llm_chat(prompt, stream=False, use_tools=True):
    """调用LLM，支持流式输出 + 短期记忆 + Function Calling"""
    # 将用户输入加入短期记忆
    chat_history.append({"role": "user", "content": clean_surrogates(prompt)})
    trim_history()

    # 构建带上下文的 messages
    messages = [{
        "role": "system",
        "content": f"你是一个学习助手，帮助用户复盘学习内容并制定复习计划。当前日期：{get_now_date()}"
    }]
    messages.extend(chat_history)

    # 第一次调用：判断是否需要工具
    kwargs = {
        "model": "glm-4-flash",
        "messages": messages,
        "temperature": 0.3,
    }
    if use_tools:
        kwargs["tools"] = tools

    resp = client.chat.completions.create(**kwargs)
    message = resp.choices[0].message

    # 如果 LLM 请求调用工具
    if use_tools and message.tool_calls:
        # 把 LLM 的工具调用请求加入历史
        chat_history.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                } for tc in message.tool_calls
            ]
        })
        trim_history()

        # 逐个执行工具
        messages.append(message)
        for tool_call in message.tool_calls:
            func_name = tool_call.function.name
            func_args_str = tool_call.function.arguments
            print(f"  [调用工具: {func_name}({func_args_str})]")

            result = execute_tool_call(tool_call)

            # 工具结果加入 messages
            messages.append({
                "role": "tool",
                "content": clean_surrogates(str(result)),
                "tool_call_id": tool_call.id
            })

        # 第二次调用：LLM 根据工具结果生成最终回复
        if stream:
            full_content = ""
            stream_resp = client.chat.completions.create(
                model="glm-4-flash",
                messages=messages,
                tools=tools,
                temperature=0.3,
                stream=True
            )
            for chunk in stream_resp:
                delta = chunk.choices[0].delta
                if delta.content:
                    safe_text = clean_surrogates(delta.content)
                    print(safe_text, end="", flush=True)
                    full_content += safe_text
            print()
            chat_history.append({"role": "assistant", "content": full_content})
            trim_history()
            return full_content
        else:
            final_resp = client.chat.completions.create(
                model="glm-4-flash",
                messages=messages,
                tools=tools,
                temperature=0.3
            )
            reply = clean_surrogates(final_resp.choices[0].message.content)
            chat_history.append({"role": "assistant", "content": reply})
            trim_history()
            return reply

    # 不需要工具，直接回复
    reply = clean_surrogates(message.content or "")
    chat_history.append({"role": "assistant", "content": reply})
    trim_history()

    if stream:
        # 非工具场景的流式已在上面处理，这里处理非流式
        return reply

    return reply

def generate_review_plan():
    """复盘昨日学习 + 生成今日复习计划"""
    today = get_now_date()
    yesterday = get_yesterday_date()
    yesterday_content = memory_data["daily_record"].get(yesterday, "昨日无学习记录")
    all_tasks = memory_data["tasks"]

    cot_prompt = f"""
请作为我的学习助手，完成两项工作：
1. 复盘昨日学习内容：{yesterday_content}，总结重点并给出复习建议
2. 结合现有任务 {all_tasks}，根据截止时间、复习次数，制定简洁的今日学习复习计划

严格按照以下格式输出：
【昨日学习复盘与复习建议】
【今日学习计划】
"""
    print("\n========== 每日学习提醒 ==========")
    result = llm_chat(cot_prompt, stream=True, use_tools=False)
    print("=================================\n")
    return result

# ========== 5. 定时任务 & 主交互入口 ==========
def auto_run():
    generate_review_plan()

schedule.every().day.at("08:00").do(auto_run)
schedule.every().day.at("21:00").do(auto_run)

def main():
    print("=" * 40)
    print("  个人学习提醒Agent 已启动")
    print("=" * 40)
    print("1 - 添加新学习任务")
    print("2 - 手动生成今日复习计划")
    print("3 - 记录今日学习内容")
    print("4 - 自由对话（支持自然语言操作）")
    print("5 - 退出程序\n")

    while True:
        cmd = input("请输入指令编号：").strip()
        if cmd == "1":
            task = input("请输入学习任务：")
            ddl = input("请输入截止日期(例:2026-06-20)：")
            print(add_task(task, ddl))
        elif cmd == "2":
            generate_review_plan()
        elif cmd == "3":
            content = input("请输入今日学习内容：")
            print(record_daily_content(content))
        elif cmd == "4":
            print("进入自由对话模式（输入 q 退出）")
            print("提示：可以直接说'帮我添加任务'、'看看我的任务列表'等\n")
            while True:
                user_input = input("你：").strip()
                if user_input.lower() == "q":
                    print("退出对话模式\n")
                    break
                if not user_input:
                    continue
                print("助手：", end="")
                llm_chat(user_input, stream=True, use_tools=True)
        elif cmd == "5":
            print("程序退出")
            break
        else:
            # 非数字输入也尝试作为自然语言处理
            print("助手：", end="")
            llm_chat(cmd, stream=True, use_tools=True)
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()