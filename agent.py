import json
import datetime
import schedule
import time
import os
import threading
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
                data = json.load(f)
            for task in data.get("tasks", []):
                task.setdefault("category", "其他")
                task.setdefault("mastery", "生疏")
                task.setdefault("last_review", None)
                task.setdefault("estimated_hours", 1.0)
                task.setdefault("priority", 0)
            self.data = data
            self._recalc_priorities()
            self._save()
            return data
        except FileNotFoundError:
            init_data = {"tasks": [], "daily_record": {}}
            self._save(init_data)
            return init_data

    def _save(self, data=None):
        if data is None:
            data = self.data
        raw = json.dumps(data, ensure_ascii=False, indent=2)
        raw = raw.encode("utf-8", errors="replace").decode("utf-8")
        with open(self.file_path, "w", encoding="utf-8") as f:
            f.write(raw)

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
        if task_index < 0 or task_index >= len(self.data["tasks"]):
            return f"错误：任务索引 {task_index} 不存在"
        task = self.data["tasks"][task_index]
        for key, value in kwargs.items():
            if key in task:
                task[key] = value
        if key in ("deadline", "mastery", "review_count", "last_review"):
            self._recalc_priorities()
        self._save()
        return f"任务更新成功：{task['task']}"

    def mark_reviewed(self, task_index):
        if task_index < 0 or task_index >= len(self.data["tasks"]):
            return f"错误：任务索引 {task_index} 不存在"
        task = self.data["tasks"][task_index]
        task["review_count"] += 1
        task["last_review"] = self.get_now_date()
        mastery_idx = self.MASTERY_LEVELS.index(task["mastery"])
        if mastery_idx < len(self.MASTERY_LEVELS) - 1:
            task["mastery"] = self.MASTERY_LEVELS[mastery_idx + 1]
        self._recalc_priorities()
        self._save()
        return f"已标记复习：{task['task']}，累计复习{task['review_count']}次，掌握程度：{task['mastery']}"

    def get_tasks(self):
        return json.dumps(self.data["tasks"], ensure_ascii=False)

    def get_task_ranking(self):
        sorted_tasks = sorted(
            self.data["tasks"],
            key=lambda t: t.get("priority", 0),
            reverse=True
        )
        return json.dumps(sorted_tasks, ensure_ascii=False)

    # ---- 优先级算法 ----
    def _recalc_priorities(self):
        today = datetime.datetime.now()
        for task in self.data["tasks"]:
            if task["status"] == "已完成":
                task["priority"] = 0
                continue
            try:
                deadline_date = datetime.datetime.strptime(task["deadline"], "%Y-%m-%d")
                days_left = (deadline_date - today).days
                if days_left <= 0:
                    urgency_score = 40
                elif days_left <= 3:
                    urgency_score = 30
                elif days_left <= 7:
                    urgency_score = 20
                else:
                    urgency_score = 10
            except ValueError:
                urgency_score = 10

            mastery_scores = {"生疏": 30, "一般": 20, "熟悉": 10, "精通": 0}
            mastery_score = mastery_scores.get(task["mastery"], 15)

            if task["last_review"] is None:
                interval_score = 30
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
                        interval_score = 0
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
        today = self.memory.get_now_date()

        cot_prompt = f"""你是一位专业的学习规划师，擅长根据艾宾浩斯遗忘曲线和学习优先级制定个性化复习计划。

## 输入数据
- 当前日期：{today}
- 昨日学习内容：{yesterday_content}
- 按优先级排序的任务列表：{ranked_tasks}

## 推理步骤
请按以下步骤逐步思考：

第一步：复盘昨日学习
- 提取昨日学习的核心知识点（不超过3个）
- 评估每个知识点的掌握情况
- 根据遗忘曲线，判断哪些知识点今天需要复习

第二步：分析任务优先级
- 找出优先级最高的3个任务
- 说明它们优先级高的原因（截止紧急/掌握程度低/复习间隔长）
- 计算今日可用学习时间（假设每天4小时）

第三步：制定今日计划
- 按优先级从高到低分配时间
- 生疏任务分配更多时间，熟悉任务快速回顾即可
- 确保总时长不超过4小时
- 每个任务给出具体的复习方式建议

## 输出格式
严格按照以下格式输出，不要添加额外内容：

【昨日学习复盘】
- 核心知识点1：xxx | 掌握情况：xxx | 是否需要今日复习：是/否
- 核心知识点2：xxx | 掌握情况：xxx | 是否需要今日复习：是/否

【优先任务分析】
1. 任务名 | 优先级：xx分 | 原因：xxx
2. 任务名 | 优先级：xx分 | 原因：xxx
3. 任务名 | 优先级：xx分 | 原因：xxx

【今日学习计划】
| 序号 | 任务 | 时长 | 复习方式 |
|------|------|------|---------|
| 1    | xxx  | 1.5h | xxx     |
| 2    | xxx  | 1.0h | xxx     |
总计：x.x小时
"""
        print("\n========== 每日学习提醒 ==========")
        result = self.chat(cot_prompt, stream=True, use_tools=False)
        print("=================================\n")
        return result

    def quiz_mode(self):
        """学习考察模式：基于遗忘曲线和掌握程度智能出题"""
        records = self.memory.data.get("daily_record", {})
        if not records:
            print("暂无学习记录，请先记录学习内容\n")
            return

        # ---- 智能选题：按遗忘曲线 + 掌握程度筛选 ----
        today = datetime.datetime.now()
        quiz_candidates = []

        for date_str, content in records.items():
            try:
                record_date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
                days_since = (today - record_date).days
            except ValueError:
                continue

            # 艾宾浩斯遗忘节点：1天、2天、4天、7天、15天
            # 在这些节点附近最需要复习
            forgetting_nodes = [1, 2, 4, 7, 15]
            need_review = False
            for node in forgetting_nodes:
                if abs(days_since - node) <= 1:  # 允许±1天误差
                    need_review = True
                    break
            # 超过15天没复习的也需要
            if days_since >= 15:
                need_review = True

            # 计算遗忘紧急度（越久没复习分越高）
            if days_since <= 1:
                urgency = 10
            elif days_since <= 3:
                urgency = 30
            elif days_since <= 7:
                urgency = 50
            elif days_since <= 15:
                urgency = 70
            else:
                urgency = 90

            quiz_candidates.append({
                "date": date_str,
                "content": content,
                "days_since": days_since,
                "urgency": urgency,
                "need_review": need_review
            })

        # 排序：需要复习的优先，遗忘紧急度高的优先
        quiz_candidates.sort(key=lambda x: (x["need_review"], x["urgency"]), reverse=True)

        # 只取最需要考察的3条记录（控制 token）
        quiz_records = quiz_candidates[:3]
        recent_content = "\n".join(
            f"{r['date']}(距今{r['days_since']}天，遗忘紧急度{r['urgency']}): {r['content']}"
            for r in quiz_records
        )

        # 获取任务掌握程度信息
        tasks_str = self.memory.get_task_ranking()

        quiz_system_prompt = f"""你是一位严格的老师，负责考察学生的学习成果。

当前日期：{self.memory.get_now_date()}
学生的学习记录（按遗忘紧急度排序，越紧急越需要重点考察）：
{recent_content}

学生的任务列表（按优先级排序）：
{tasks_str}

考察策略：
1. 优先考察遗忘紧急度高的内容（距今较久、快忘了的知识点）
2. 优先考察掌握程度"生疏"的任务相关内容，"精通"的可以跳过
3. 题型可以是：选择题、填空题、简答题，交替使用
4. 难度根据掌握程度调整：生疏→基础题，一般→中等题，熟悉→进阶题
5. 学生作答后，判断对错并给出详细解析
6. 如果答错，给出正确答案和相关知识点复习建议
7. 分析学生的理解是否正确，指出遗漏的关键点
8. 每次只出1道题，等学生回答后再出下一道

输出格式：
【题目】(题型：选择题/填空题/简答题 | 难度：基础/中等/进阶 | 考察知识点：xxx)
题目内容

【学生作答后输出】
✅ 回答正确 / ❌ 回答错误
【解析】详细解析
【理解分析】学生的理解是否正确，有哪些遗漏的关键点
【复习建议】如果答错或理解不完整，给出针对性复习建议
"""

        quiz_history = []

        def quiz_llm(prompt, stream=True):
            quiz_history.append({"role": "user", "content": ChatSession._clean_surrogates(prompt)})
            messages = [{"role": "system", "content": quiz_system_prompt}] + quiz_history

            if not stream:
                resp = self.client.chat.completions.create(
                    model="glm-4-flash", messages=messages, temperature=0.3
                )
                reply = ChatSession._clean_surrogates(resp.choices[0].message.content or "")
                quiz_history.append({"role": "assistant", "content": reply})
                return reply

            full_content = ""
            stream_resp = self.client.chat.completions.create(
                model="glm-4-flash", messages=messages, temperature=0.3, stream=True
            )
            for chunk in stream_resp:
                delta = chunk.choices[0].delta
                if delta.content:
                    safe_text = ChatSession._clean_surrogates(delta.content)
                    print(safe_text, end="", flush=True)
                    full_content += safe_text
            print()
            quiz_history.append({"role": "assistant", "content": full_content})
            return full_content

        # 显示考察范围
        print("\n========== 学习考察模式 ==========")
        print("基于艾宾浩斯遗忘曲线，优先考察快遗忘的知识点：")
        for r in quiz_records:
            print(f"  📅 {r['date']} | 距今{r['days_since']}天 | 遗忘紧急度：{r['urgency']}")
        print("输入 q 退出考察模式\n")

        print("老师：", end="")
        quiz_llm("请根据我的学习记录，优先考察遗忘紧急度高的知识点，出一道题。")

        while True:
            try:
                answer = input("\n你的回答：").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n退出考察模式\n")
                break

            if answer.lower() == "q":
                print("\n老师：", end="")
                quiz_llm("考察结束，请总结我的学习表现，指出理解上的偏差和遗漏的关键知识点，给出改进建议。")
                print("退出考察模式\n")
                break

            if not answer:
                print("请输入你的答案，或输入 q 退出\n")
                continue

            print("老师：", end="")
            quiz_llm(answer)

# ========== 入口：菜单 + 定时调度 ==========
class App:
    """应用入口，管理菜单交互和定时任务"""

    def __init__(self):
        self.agent = StudyAgent()

    def _print_menu(self):
        print("\n" + "=" * 40)
        print("  个人学习提醒Agent")
        print("=" * 40)
        print("1 - 添加新学习任务")
        print("2 - 手动生成今日复习计划")
        print("3 - 记录今日学习内容")
        print("4 - 查看任务优先级排行")
        print("5 - 标记任务已复习")
        print("6 - 学习考察模式（老师出题）")
        print("7 - 自由对话")
        print("8 - 退出程序")
        print("-" * 40)
        print("提示：也可直接输入自然语言，如'帮我添加一个Python任务'")
        print("=" * 40 + "\n")

    # ---- 输入校验工具 ----
    @staticmethod
    def _validate_date(date_str):
        try:
            datetime.datetime.strptime(date_str, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    def _input_with_validation(self, prompt, validator=None, error_msg="输入无效，请重新输入"):
        while True:
            value = input(prompt).strip()
            if not value:
                print("已取消输入\n")
                return None
            if validator is None or validator(value):
                return value
            print(error_msg)

    @staticmethod
    def _try_float(value):
        try:
            float(value)
            return True
        except ValueError:
            return False

    # ---- 菜单操作 ----
    def _handle_add_task(self):
        task = self._input_with_validation(
            "请输入学习任务（回车取消）：",
            lambda x: len(x) > 0,
            "任务名称不能为空"
        )
        if task is None:
            return

        ddl = self._input_with_validation(
            "请输入截止日期(YYYY-MM-DD，回车取消)：",
            self._validate_date,
            "日期格式错误，请使用 YYYY-MM-DD 格式，如 2026-06-20"
        )
        if ddl is None:
            return

        category = self._input_with_validation(
            f"任务分类({'/'.join(MemoryStore.CATEGORIES)})，回车默认其他：",
            lambda x: x in MemoryStore.CATEGORIES,
            f"请输入：{'/'.join(MemoryStore.CATEGORIES)}"
        )
        if category is None:
            category = "其他"

        mastery = self._input_with_validation(
            f"掌握程度({'/'.join(MemoryStore.MASTERY_LEVELS)})，回车默认生疏：",
            lambda x: x in MemoryStore.MASTERY_LEVELS,
            f"请输入：{'/'.join(MemoryStore.MASTERY_LEVELS)}"
        )
        if mastery is None:
            mastery = "生疏"

        hours = self._input_with_validation(
            "预估学习时长(小时)，回车默认1.0：",
            lambda x: self._try_float(x) and float(x) > 0,
            "请输入正数，如 1.5"
        )
        if hours is None:
            hours = "1.0"

        result = self.agent.memory.add_task(task, ddl, category, mastery, float(hours))
        print(result)

    def _handle_review_plan(self):
        try:
            self.agent.generate_review_plan()
        except Exception as e:
            print(f"生成复习计划失败：{e}\n请检查网络连接和API密钥\n")

    def _handle_record(self):
        content = self._input_with_validation(
            "请输入今日学习内容（回车取消）：",
            lambda x: len(x) > 0,
            "学习内容不能为空"
        )
        if content is None:
            return
        try:
            print(self.agent.memory.record_daily(content))
        except Exception as e:
            print(f"记录失败：{e}\n")

    def _handle_ranking(self):
        try:
            ranked = json.loads(self.agent.memory.get_task_ranking())
        except Exception as e:
            print(f"获取排行失败：{e}\n")
            return

        if not ranked:
            print("暂无任务，请先添加任务\n")
            return

        print("\n===== 任务优先级排行 =====")
        for i, task in enumerate(ranked):
            priority = task.get("priority", 0)
            print(f"  {i}. [{priority}分] {task['task']} "
                  f"| 截止:{task['deadline']} | 掌握:{task.get('mastery', '未知')} "
                  f"| 复习:{task.get('review_count', 0)}次 | 分类:{task.get('category', '其他')}")
        print("=========================\n")

    def _handle_mark_reviewed(self):
        self._handle_ranking()
        try:
            tasks = self.agent.memory.data["tasks"]
        except Exception:
            print("获取任务列表失败\n")
            return

        if not tasks:
            return

        idx_str = self._input_with_validation(
            "请输入要标记的任务编号（回车取消）：",
            lambda x: x.isdigit() and 0 <= int(x) < len(tasks),
            f"请输入 0-{len(tasks)-1} 之间的数字"
        )
        if idx_str is None:
            return

        try:
            print(self.agent.memory.mark_reviewed(int(idx_str)))
        except Exception as e:
            print(f"标记失败：{e}\n")

    def _handle_quiz(self):
        try:
            self.agent.quiz_mode()
        except Exception as e:
            print(f"考察模式出错：{e}\n请稍后重试\n")

    def _handle_chat(self):
        print("进入自由对话模式（输入 q 退出）")
        print("提示：可以直接说'帮我添加任务'、'看看我的任务排行'等\n")
        while True:
            try:
                user_input = input("你：").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n退出对话模式\n")
                break
            if user_input.lower() == "q":
                print("退出对话模式\n")
                break
            if not user_input:
                continue
            try:
                print("助手：", end="")
                self.agent.chat(user_input, stream=True, use_tools=True)
            except Exception as e:
                print(f"\n对话出错：{e}\n请稍后重试\n")

    # ---- 自然语言识别 ----
    def _is_menu_command(self, text):
        return text.isdigit() and 1 <= int(text) <= 8

    def _handle_natural_language(self, text):
        try:
            print("助手：", end="")
            self.agent.chat(text, stream=True, use_tools=True)
        except Exception as e:
            print(f"\n处理失败：{e}\n请稍后重试\n")

    # ---- 定时调度 ----
    def _run_scheduler(self):
        while True:
            schedule.run_pending()
            time.sleep(1)

    def _scheduled_review(self):
        now = datetime.datetime.now().strftime("%H:%M")
        print(f"\n\n⏰ [{now}] 定时提醒触发！")
        try:
            self.agent.generate_review_plan()
        except Exception as e:
            print(f"定时任务执行失败：{e}\n")

    # ---- 主循环 ----
    def run(self):
        self._print_menu()

        schedule.every().day.at("08:00").do(self._scheduled_review)
        schedule.every().day.at("21:00").do(self._scheduled_review)

        scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        scheduler_thread.start()

        while True:
            try:
                cmd = input("请输入指令或自然语言：").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n程序退出")
                break

            if not cmd:
                continue

            if self._is_menu_command(cmd):
                cmd_num = int(cmd)
                if cmd_num == 1:
                    self._handle_add_task()
                elif cmd_num == 2:
                    self._handle_review_plan()
                elif cmd_num == 3:
                    self._handle_record()
                elif cmd_num == 4:
                    self._handle_ranking()
                elif cmd_num == 5:
                    self._handle_mark_reviewed()
                elif cmd_num == 6:
                    self._handle_quiz()
                elif cmd_num == 7:
                    self._handle_chat()
                elif cmd_num == 8:
                    print("程序退出")
                    break
            else:
                self._handle_natural_language(cmd)


if __name__ == "__main__":
    App().run()