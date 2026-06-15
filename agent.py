import json
import datetime
import schedule
import time
import os
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
        # 初始化结构：任务列表 + 每日学习记录
        init_data = {"tasks": [], "daily_record": {}}
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(init_data, f, ensure_ascii=False, indent=2)
        return init_data

def save_memory(data):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

memory_data = init_memory()

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
    return f"✅ 任务添加成功：{task_name}"

def record_daily_content(content):
    today = get_now_date()
    memory_data["daily_record"][today] = content
    save_memory(memory_data)

# ========== 3. LLM + 规划模块（CoT思维链） ==========
client = OpenAI(
    api_key=API_KEY,
    base_url="https://open.bigmodel.cn/api/paas/v4"
)

def llm_chat(prompt):
    resp = client.chat.completions.create(
        model="glm-4-flash",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )
    return resp.choices[0].message.content

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
    result = llm_chat(cot_prompt)
    print("\n========== 每日学习提醒 ==========")
    print(result)
    print("=================================\n")
    return result

# ========== 4. 定时任务 & 主交互入口 ==========
def auto_run():
    generate_review_plan()

# 每日 08:00、21:00 自动提醒，可自行修改时间
schedule.every().day.at("08:00").do(auto_run)
schedule.every().day.at("21:00").do(auto_run)

def main():
    print("📚 个人学习提醒Agent 已启动")
    print("1 - 添加新学习任务")
    print("2 - 手动生成今日复习计划")
    print("3 - 记录今日学习内容")
    print("4 - 退出程序\n")

    while True:
        cmd = input("请输入指令编号：")
        if cmd == "1":
            task = input("请输入学习任务：")
            ddl = input("请输入截止日期(例:2026-06-20)：")
            print(add_task(task, ddl))
        elif cmd == "2":
            generate_review_plan()
        elif cmd == "3":
            content = input("请输入今日学习内容：")
            record_daily_content(content)
            print("✅ 今日内容已保存")
        elif cmd == "4":
            print("👋 程序退出")
            break
        else:
            print("❌ 无效指令")
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()
