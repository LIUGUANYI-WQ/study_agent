import json
import datetime
import schedule
import time
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


# ========== 长期记忆：数据持久化 ==========
class MemoryStore:
    """管理任务和学习日志的持久化存储"""

    MASTERY_LEVELS = ["生疏", "一般", "熟悉", "精通"]
    STATUS_OPTIONS = ["未完成", "进行中", "已完成"]
    CATEGORIES = ["编程", "算法", "数学", "英语", "其他"]

    def __init__(self, file_path="study_memory.json"):
        self.file_path = file_path
        self.data = self._load()

    def _load(self):
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            init_data = {"tasks": [], "daily_record": {}}
            self._save(init_data)
            return init_data

    def _save(self, data=None):
        if data is None:
            data = self.data
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ---- 任务操作 ----
    def add_task(self, task_name, deadline, category="其他",
                 mastery="生疏", estimated_hours=1.0):
        new_task = {
            "task": task_name,
            "deadline": deadline,
            "status": "未完成",
            "review_count": 0,
            "create_time": self.get_now_date(),
            "category": category,
            "mastery": mastery,
            "last_review": None,
            "estimated_hours": estimated_hours,
            "priority": 0,
        }
        self.data["tasks"].append(new_task)
        self._recalc_priorities()
        self._save()
        return f"任务添加成功：{task_name}，截止日期：{deadline}，分类：{category}，掌握程度：{mastery}"

    def update_task(self, task_index, **kwargs):
        """更新任务字段，支持部分更新"""
        if task_index < 0 or task_index >= len(self.data["tasks"]):
            return f"错误：任务索引 {task_index} 不存在"
        task = self.data["tasks"][task_index]
        for key, value in kwargs.items():
            if key in task:
                task[key] = value
        # 如果更新了影响优先级的字段，重新计算
        if key in ("deadline", "mastery", "review_count", "last_review"):
            self._recalc_priorities()
        self._save()
        return f"任务更新成功：{task['task']}"

    def mark_reviewed(self, task_index):
        """标记任务已复习，更新复习次数和上次复习时间"""
        if task_index < 0 or task_index >= len(self.data["tasks"]):
            return f"错误：任务索引 {task_index} 不存在"
        task = self.data["tasks"][task_index]
        task["review_count"] += 1
        task["last_review"] = self.get_now_date()
        # 复习次数增加，掌握程度提升
        mastery_idx = self.MASTERY_LEVELS.index(task["mastery"])
        if mastery_idx < len(self.MASTERY_LEVELS) - 1:
            task["mastery"] = self.MASTERY_LEVELS[mastery_idx + 1]
        self._recalc_priorities()
        self._save()
        return f"已标记复习：{task['task']}，累计复习{task['review_count']}次，掌握程度：{task['mastery']}"

    def get_tasks(self):
        return json.dumps(self.data["tasks"], ensure_ascii=False)

    def get_task_ranking(self):
        """返回按优先级排序的任务列表"""
        sorted_tasks = sorted(
            self.data["tasks"],
            key=lambda t: t.get("priority", 0),
            reverse=True
        )
        return json.dumps(sorted_tasks, ensure_ascii=False)

    # ---- 优先级算法 ----
    def _recalc_priorities(self):
        """多维度优先级打分：截止紧急度 + 生疏度 + 复习间隔"""
        today = datetime.datetime.now()
        for task in self.data["tasks"]:
            if task["status"] == "已完成":
                task["priority"] = 0
                continue

            # 维度1：截止紧急度（距截止日越近分越高，0-40分）
            try:
                deadline_date = datetime.datetime.strptime(task["deadline"], "%Y-%m-%d")
                days_left = (deadline_date - today).days
                if days_left <= 0:
                    urgency_score = 40  # 已过期，最高紧急
                elif days_left <= 3:
                    urgency_score = 30
                elif days_left <= 7:
                    urgency_score = 20
                else:
                    urgency_score = 10
            except ValueError:
                urgency_score = 10

            # 维度2：生疏度（越生疏分越高，0-30分）
            mastery_scores = {"生疏": 30, "一般": 20, "熟悉": 10, "精通": 0}
            mastery_score = mastery_scores.get(task["mastery"], 15)

            # 维度3：复习间隔（越久没复习分越高，0-30分）
            if task["last_review"] is None:
                interval_score = 30  # 从未复习
            else:
                try:
                    last = datetime.datetime.strptime(task["last_review"], "%Y-%m-%d")
                    days_since = (today - last).days
                    if days_since >= 7:
                        interval_score = 30
                    elif days_since >= 3:
                        interval_score = 20
                    elif days_since >= 1:
                        interval_score = 10
                    else:
                        interval_score = 0  # 今天刚复习过
                except ValueError:
                    interval_score = 15

            task["priority"] = urgency_score + mastery_score + interval_score

    # ---- 日志操作 ----
    def record_daily(self, content):
        today = self.get_now_date()
        self.data["daily_record"][today] = content
        self._save()
        return f"已记录今日学习内容：{content}"

    def get_daily_record(self, date_str=None):
        if date_str is None:
            date_str = self.get_now_date()
        return self.data["daily_record"].get(date_str, f"{date_str} 无学习记录")

    # ---- 工具方法 ----
    @staticmethod
    def get_now_date():
        return datetime.datetime.now().strftime("%Y-%m-%d")

    @staticmethod
    def get_yesterday_date():
        yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
        return yesterday.strftime("%Y-%m-%d")


# ========== 短期记忆：对话历史 + 滑动窗口 ==========
class ChatSession:
    """管理对话上下文，支持滑动窗口截断"""

    def __init__(self, max_rounds=5):
        self.max_rounds = max_rounds
        self.history = []

    @staticmethod
    def _clean_surrogates(text):
        return text.encode("utf-8", errors="replace").decode("utf-8")

    def add_message(self, role, content, **kwargs):
        msg = {"role": role, "content": self._clean_surrogates(content)}
        msg.update(kwargs)
        self.history.append(msg)
        self._trim()

    def add_tool_call_message(self, tool_calls):
        self.history.append({
            "role": "assistant",
            "content": None,
            "tool_calls": tool_calls
        })
        self._trim()

    def add_tool_result(self, tool_call_id, result):
        self.history.append({
            "role": "tool",
            "content": self._clean_surrogates(str(result)),
            "tool_call_id": tool_call_id
        })
        self._trim()

    def get_messages(self, system_prompt):
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self.history)
        return messages

    def _trim(self):
        max_messages = self.max_rounds * 2
        if len(self.history) > max_messages:
            excess = len(self.history) - max_messages
            del self.history[:excess]

    def clear(self):
        self.history = []


# ========== 核心逻辑：LLM + Function Calling ==========
class StudyAgent:
    """学习助手 Agent，组合 MemoryStore + ChatSession"""

    TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "add_task",
                "description": "添加一个新的学习任务",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_name": {"type": "string", "description": "任务名称"},
                        "deadline": {"type": "string", "description": "截止日期，格式 YYYY-MM-DD"},
                        "category": {
                            "type": "string",
                            "description": "任务分类：编程/算法/数学/英语/其他",
                            "enum": ["编程", "算法", "数学", "英语", "其他"]
                        },
                        "mastery": {
                            "type": "string",
                            "description": "掌握程度：生疏/一般/熟悉/精通",
                            "enum": ["生疏", "一般", "熟悉", "精通"]
                        },
                        "estimated_hours": {
                            "type": "number",
                            "description": "预估学习时长（小时）"
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
                        "content": {"type": "string", "description": "学习内容描述"}
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
                "parameters": {"type": "object", "properties": {}}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_task_ranking",
                "description": "获取按优先级排序的任务列表，优先级越高越需要优先复习",
                "parameters": {"type": "object", "properties": {}}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "mark_reviewed",
                "description": "标记某个任务已完成复习，会自动更新复习次数和掌握程度",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_index": {
                            "type": "integer",
                            "description": "任务在列表中的索引（从0开始）"
                        }
                    },
                    "required": ["task_index"]
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

    def __init__(self, memory_file="study_memory.json", max_rounds=5):
        self.memory = MemoryStore(memory_file)
        self.session = ChatSession(max_rounds)
        self.client = OpenAI(
            api_key=os.getenv("ZHIPU_API_KEY"),
            base_url="https://open.bigmodel.cn/api/paas/v4"
        )

    def _execute_tool(self, func_name, func_args):
        tool_map = {
            "add_task": self.memory.add_task,
            "record_daily_content": self.memory.record_daily,
            "get_tasks": self.memory.get_tasks,
            "get_task_ranking": self.memory.get_task_ranking,
            "mark_reviewed": self.memory.mark_reviewed,
            "get_daily_record": self.memory.get_daily_record,
        }
        if func_name not in tool_map:
            return f"错误：未知工具 {func_name}"
        try:
            return tool_map[func_name](**func_args)
        except Exception as e:
            return f"工具执行错误：{e}"

    def chat(self, prompt, stream=False, use_tools=True):
        """与 LLM 对话，支持 Function Calling + 流式输出"""
        self.session.add_message("user", prompt)

        system_prompt = (
            f"你是一个学习助手，帮助用户复盘学习内容并制定复习计划。"
            f"当前日期：{self.memory.get_now_date()}"
        )
        messages = self.session.get_messages(system_prompt)

        kwargs = {
            "model": "glm-4-flash",
            "messages": messages,
            "temperature": 0.3,
        }
        if use_tools:
            kwargs["tools"] = self.TOOLS

        resp = self.client.chat.completions.create(**kwargs)
        message = resp.choices[0].message

        if use_tools and message.tool_calls:
            tool_calls_serialized = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                } for tc in message.tool_calls
            ]
            self.session.add_tool_call_message(tool_calls_serialized)

            messages.append(message)
            for tc in message.tool_calls:
                func_name = tc.function.name
                func_args = json.loads(tc.function.arguments)
                print(f"  [调用工具: {func_name}({tc.function.arguments})]")

                result = self._execute_tool(func_name, func_args)
                messages.append({
                    "role": "tool",
                    "content": ChatSession._clean_surrogates(str(result)),
                    "tool_call_id": tc.id
                })
                self.session.add_tool_result(tc.id, result)

            return self._call_llm_stream(messages, use_tools=True) if stream \
                else self._call_llm(messages, use_tools=True)

        reply = ChatSession._clean_surrogates(message.content or "")
        self.session.add_message("assistant", reply)
        return reply

    def _call_llm(self, messages, use_tools=True):
        kwargs = {"model": "glm-4-flash", "messages": messages, "temperature": 0.3}
        if use_tools:
            kwargs["tools"] = self.TOOLS
        resp = self.client.chat.completions.create(**kwargs)
        reply = ChatSession._clean_surrogates(resp.choices[0].message.content or "")
        self.session.add_message("assistant", reply)
        return reply

    def _call_llm_stream(self, messages, use_tools=True):
        kwargs = {"model": "glm-4-flash", "messages": messages, "temperature": 0.3, "stream": True}
        if use_tools:
            kwargs["tools"] = self.TOOLS
        stream_resp = self.client.chat.completions.create(**kwargs)
        full_content = ""
        for chunk in stream_resp:
            delta = chunk.choices[0].delta
            if delta.content:
                safe_text = ChatSession._clean_surrogates(delta.content)
                print(safe_text, end="", flush=True)
                full_content += safe_text
        print()
        self.session.add_message("assistant", full_content)
        return full_content

    def generate_review_plan(self):
        """复盘昨日学习 + 生成今日复习计划"""
        yesterday = self.memory.get_yesterday_date()
        yesterday_content = self.memory.get_daily_record(yesterday)
        ranked_tasks = self.memory.get_task_ranking()

        cot_prompt = f"""
请作为我的学习助手，完成两项工作：
1. 复盘昨日学习内容：{yesterday_content}，总结重点并给出复习建议
2. 结合按优先级排序的任务列表 {ranked_tasks}，制定简洁的今日学习复习计划
   - 优先安排高优先级任务
   - 参考掌握程度决定复习强度（生疏多分配时间，熟悉少分配）
   - 参考预估时长合理安排每日学习量

严格按照以下格式输出：
【昨日学习复盘与复习建议】
【今日学习计划】
"""
        print("\n========== 每日学习提醒 ==========")
        result = self.chat(cot_prompt, stream=True, use_tools=False)
        print("=================================\n")
        return result


# ========== 入口：菜单 + 定时调度 ==========
class App:
    """应用入口，管理菜单交互和定时任务"""

    def __init__(self):
        self.agent = StudyAgent()

    def _print_menu(self):
        print("=" * 40)
        print("  个人学习提醒Agent 已启动")
        print("=" * 40)
        print("1 - 添加新学习任务")
        print("2 - 手动生成今日复习计划")
        print("3 - 记录今日学习内容")
        print("4 - 查看任务优先级排行")
        print("5 - 标记任务已复习")
        print("6 - 自由对话（支持自然语言操作）")
        print("7 - 退出程序\n")

    def _handle_add_task(self):
        task = input("请输入学习任务：")
        ddl = input("请输入截止日期(例:2026-06-20)：")
        category = input(f"任务分类({'/'.join(MemoryStore.CATEGORIES)})，回车默认其他：") or "其他"
        mastery = input(f"掌握程度({'/'.join(MemoryStore.MASTERY_LEVELS)})，回车默认生疏：") or "生疏"
        try:
            hours = float(input("预估学习时长(小时)，回车默认1.0：") or "1.0")
        except ValueError:
            hours = 1.0
        print(self.agent.memory.add_task(task, ddl, category, mastery, hours))

    def _handle_review_plan(self):
        self.agent.generate_review_plan()

    def _handle_record(self):
        content = input("请输入今日学习内容：")
        print(self.agent.memory.record_daily(content))

    def _handle_ranking(self):
        ranked = json.loads(self.agent.memory.get_task_ranking())
        print("\n===== 任务优先级排行 =====")
        for i, task in enumerate(ranked):
            print(f"  {i}. [{task['priority']}分] {task['task']} "
                  f"| 截止:{task['deadline']} | 掌握:{task['mastery']} "
                  f"| 复习:{task['review_count']}次 | 分类:{task['category']}")
        print("=========================\n")

    def _handle_mark_reviewed(self):
        self._handle_ranking()
        try:
            idx = int(input("请输入要标记的任务编号："))
            print(self.agent.memory.mark_reviewed(idx))
        except ValueError:
            print("错误：请输入有效数字")

    def _handle_chat(self):
        print("进入自由对话模式（输入 q 退出）")
        print("提示：可以直接说'帮我添加任务'、'看看我的任务排行'等\n")
        while True:
            user_input = input("你：").strip()
            if user_input.lower() == "q":
                print("退出对话模式\n")
                break
            if not user_input:
                continue
            print("助手：", end="")
            self.agent.chat(user_input, stream=True, use_tools=True)

    def run(self):
        self._print_menu()

        schedule.every().day.at("08:00").do(self.agent.generate_review_plan)
        schedule.every().day.at("21:00").do(self.agent.generate_review_plan)

        while True:
            cmd = input("请输入指令编号：").strip()
            if cmd == "1":
                self._handle_add_task()
            elif cmd == "2":
                self._handle_review_plan()
            elif cmd == "3":
                self._handle_record()
            elif cmd == "4":
                self._handle_ranking()
            elif cmd == "5":
                self._handle_mark_reviewed()
            elif cmd == "6":
                self._handle_chat()
            elif cmd == "7":
                print("程序退出")
                break
            else:
                print("助手：", end="")
                self.agent.chat(cmd, stream=True, use_tools=True)
            schedule.run_pending()
            time.sleep(1)


if __name__ == "__main__":
    App().run()