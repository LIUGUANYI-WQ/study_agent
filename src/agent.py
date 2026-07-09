import os
import json
import time
import datetime
from openai import OpenAI
from .memory import MemoryStore
from .session import ChatSession


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

    def __init__(self, memory_file="study_memory.db", max_rounds=5, web_mode=False):
        self.memory = MemoryStore(memory_file)
        self.session = ChatSession(max_rounds)
        self.web_mode = web_mode
        self.client = OpenAI(
            api_key=os.getenv("ZHIPU_API_KEY"),
            base_url="https://open.bigmodel.cn/api/paas/v4"
        )

    def _log(self, msg):
        """打印日志，web 模式下也输出"""
        print(msg, flush=True)

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

    def analyze_learning_content(self, content):
        """
        使用LLM分析学习内容，提取知识点、评估质量、生成总结
        :return: 分析结果字典
        """
        analysis_prompt = f"""你是一位学习内容分析专家，请帮我分析以下学习记录：

学习内容：{content}

请按照以下要求进行分析：

1. **质量评估**（1-10分）：评估这条学习记录的质量，考虑因素包括：
   - 内容的完整性和深度
   - 是否包含具体知识点
   - 是否有实际价值

2. **知识点提取**：从内容中提取3-5个核心知识点，每个知识点包含：
   - name: 知识点名称
   - type: 类型（概念/原理/方法/工具/案例/其他）
   - description: 详细描述

3. **核心要点总结**：用简洁的语言总结学习内容的核心要点（不超过100字）

4. **改进建议**：如果内容质量较低，给出具体的改进建议

5. **标签建议**：建议3-5个标签

请以JSON格式输出，不要添加任何额外文字：
{{
    "quality_score": 分数,
    "quality_comment": "质量评价",
    "knowledge_points": [{{"name": "xxx", "type": "xxx", "description": "xxx"}}],
    "summary": "核心要点",
    "improvement_suggestions": ["建议1", "建议2"],
    "tags": ["标签1", "标签2"]
}}
"""
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                if not self.web_mode:
                    print(f"  正在分析（第 {attempt + 1}/{max_retries} 次尝试）...")
                resp = self.client.chat.completions.create(
                    model="glm-4-flash",
                    messages=[{"role": "user", "content": analysis_prompt}],
                    temperature=0.3,
                    timeout=60  # 增加超时到60秒
                )
                result = resp.choices[0].message.content
                
                # 清理可能的markdown格式
                if result:
                    result = result.strip()
                    # 移除 ```json 和 ``` 标记
                    if result.startswith("```"):
                        lines = result.split("\n")
                        # 移除第一行（可能是 ```json）
                        if lines[0].startswith("```"):
                            lines = lines[1:]
                        # 移除最后一行（可能是 ```）
                        if lines and lines[-1].strip() == "```":
                            lines = lines[:-1]
                        result = "\n".join(lines).strip()
                
                return json.loads(result)
                
            except json.JSONDecodeError as e:
                if not self.web_mode:
                    print(f"  JSON解析失败：{e}")
                    if attempt < max_retries - 1:
                        print(f"  将在2秒后重试...")
                if attempt < max_retries - 1:
                    time.sleep(2)
                else:
                    if not self.web_mode:
                        print(f"  JSON解析失败，已达最大重试次数")
                        print(f"  LLM返回内容：{result[:200] if result else '空内容'}...")
                    return None

            except Exception as e:
                error_msg = str(e)
                if "timeout" in error_msg.lower():
                    if not self.web_mode:
                        print(f"  请求超时")
                        if attempt < max_retries - 1:
                            print(f"  将在3秒后重试...")
                    if attempt < max_retries - 1:
                        time.sleep(3)
                    else:
                        if not self.web_mode:
                            print(f"  已达最大重试次数，请检查网络连接")
                        return None
                else:
                    if not self.web_mode:
                        print(f"  内容分析失败：{e}")
                    return None
        
        return None

    def optimize_learning_record(self, initial_content):
        """
        通过多轮对话优化学习记录，降低噪音
        :return: 优化后的结构化记录
        """
        if not self.web_mode:
            print("\n📝 正在分析您的学习内容...\n")

        analysis = self.analyze_learning_content(initial_content)
        if not analysis:
            if not self.web_mode:
                print("分析失败，将直接保存原始内容")
            return {
                "raw_content": initial_content,
                "knowledge_points": [],
                "mastery_level": "生疏",
                "tags": [],
                "summary": initial_content,
                "quality_score": 0
            }

        if not self.web_mode:
            print(f"🎯 质量评分：{analysis['quality_score']}/10")
            print(f"💡 质量评价：{analysis['quality_comment']}")

            if analysis.get("knowledge_points"):
                print("\n📚 提取的知识点：")
                for i, kp in enumerate(analysis["knowledge_points"], 1):
                    print(f"  {i}. [{kp['type']}] {kp['name']}")
                    if kp.get("description"):
                        print(f"     {kp['description'][:50]}...")

            print(f"\n📋 核心要点：{analysis['summary']}")

            if analysis["quality_score"] < 7:
                print("\n🔧 改进建议：")
                for i, suggestion in enumerate(analysis["improvement_suggestions"], 1):
                    print(f"  {i}. {suggestion}")

                while True:
                    try:
                        choice = input("\n是否需要根据建议优化内容？(y/n) ").strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        choice = 'n'

                    if choice == 'y':
                        print("\n请补充或修改学习内容（按回车确认，输入 'q' 跳过）：")
                        try:
                            improved_content = input("> ").strip()
                        except (EOFError, KeyboardInterrupt):
                            improved_content = ''

                        if improved_content.lower() == 'q':
                            break
                        if improved_content:
                            print("\n🔄 重新分析优化后的内容...")
                            analysis = self.analyze_learning_content(improved_content)
                            if analysis:
                                initial_content = improved_content
                                print(f"\n🎯 更新后质量评分：{analysis['quality_score']}/10")
                                print(f"📋 更新后核心要点：{analysis['summary']}")
                            else:
                                print("重新分析失败，使用原内容")
                            break
                        else:
                            print("未输入内容，保持原记录")
                            break
                    elif choice == 'n':
                        break
                    else:
                        print("请输入 y 或 n")

            while True:
                try:
                    mastery_input = input(f"\n请评估您对这些内容的掌握程度（{', '.join(MemoryStore.MASTERY_LEVELS)}，回车默认生疏）：").strip()
                except (EOFError, KeyboardInterrupt):
                    mastery_input = ''

                if not mastery_input:
                    mastery_level = "生疏"
                    break
                elif mastery_input in MemoryStore.MASTERY_LEVELS:
                    mastery_level = mastery_input
                    break
                else:
                    print(f"请输入：{'/'.join(MemoryStore.MASTERY_LEVELS)}")
        else:
            # Web模式：直接返回分析结果，不进行交互式输入
            mastery_level = "生疏"

        return {
            "raw_content": initial_content,
            "knowledge_points": analysis.get("knowledge_points", []),
            "mastery_level": mastery_level,
            "tags": analysis.get("tags", []),
            "summary": analysis.get("summary", initial_content),
            "quality_score": analysis.get("quality_score", 0) * 10,
            "quality_comment": analysis.get("quality_comment", ""),
            "improvement_suggestions": analysis.get("improvement_suggestions", []),
        }

    def chat(self, prompt, stream=False, use_tools=True):
        """与 LLM 对话，支持 Function Calling + 流式输出"""
        self.session.add_message("user", prompt)

        system_prompt = (
            f"你是一个专注的学习助手，只能帮助用户进行学习相关的对话。你的职责包括：帮助复盘学习内容、制定复习计划、添加学习任务、记录学习内容、解答学习问题等。\n"
            f"重要规则：\n"
            f"1. 严禁闲聊！如果用户的话题与学习无关（如闲聊天气、聊天打发时间、讲笑话、讨论娱乐等），你必须礼貌地拒绝，并引导用户回到学习话题。\n"
            f"2. 拒绝时的回复风格：温和但坚定，例如\"我是学习助手，只讨论学习相关的话题哦~有什么学习上的问题我可以帮你？\"\n"
            f"3. 允许的学习相关话题：学术知识问答、学习计划制定、知识点梳理、错题分析、考试备考、学习方法和技巧等。\n"
            f"当前日期：{self.memory.get_now_date()}"
        )
        messages = self.session.get_messages(system_prompt)

        kwargs = {
            "model": "glm-4-flash",
            "messages": messages,
            "temperature": 0.3,
            "timeout": 30,
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
                if not self.web_mode:
                    print(safe_text, end="", flush=True)
                full_content += safe_text
        if not self.web_mode:
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
        if not self.web_mode:
            print("\n========== 每日学习提醒 ==========")
        result = self.chat(cot_prompt, stream=True, use_tools=False)
        if not self.web_mode:
            print("=================================\n")
        return result

    def quiz_mode(self):
        """学习考察模式：基于遗忘曲线和掌握程度智能出题"""
        records = self.memory.data.get("daily_record", {})
        if not records:
            print("暂无学习记录，请先记录学习内容\n")
            return

        today = datetime.datetime.now()
        quiz_candidates = []

        for date_str, content in records.items():
            try:
                record_date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
                days_since = (today - record_date).days
            except ValueError:
                continue

            forgetting_nodes = [1, 2, 4, 7, 15]
            need_review = False
            for node in forgetting_nodes:
                if abs(days_since - node) <= 1:
                    need_review = True
                    break
            if days_since >= 15:
                need_review = True

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

        quiz_candidates.sort(key=lambda x: (x["need_review"], x["urgency"]), reverse=True)
        quiz_records = quiz_candidates[:3]
        recent_content = "\n".join(
            f"{r['date']}(距今{r['days_since']}天，遗忘紧急度{r['urgency']}): {r['content']}"
            for r in quiz_records
        )

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
