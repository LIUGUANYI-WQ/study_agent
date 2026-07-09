"""Flask Web 后端，为学习助手提供 API 和页面"""
import os
import re
import json
import datetime
from flask import Flask, render_template, request, jsonify, Response
from dotenv import load_dotenv
from src.agent import StudyAgent
from src.memory import MemoryStore
from src.session import ChatSession

load_dotenv()

# 停用词：这些通用词汇不参与关键词匹配，避免跨领域误匹配
STOP_WORDS = {
    "学习", "基础", "入门", "了解", "掌握", "熟悉", "理解", "复习",
    "知识", "知识点", "内容", "介绍", "概述", "总结", "笔记",
    "什么是", "怎么", "如何", "为什么", "的", "和", "与", "及",
    "一个", "一种", "一些", "这个", "那个", "这些", "那些",
    "使用", "用法", "方法", "方式", "技巧", "心得", "体会",
    "第一天", "第二天", "第三天", "第一", "第二", "第三",
    "第1天", "第2天", "第3天", "第7天",
}

app = Flask(__name__, static_folder='static')
agent = StudyAgent(web_mode=True)

import time
@app.before_request
def log_request():
    request._start_time = time.time()

@app.after_request
def log_response(response):
    if hasattr(request, '_start_time'):
        elapsed = (time.time() - request._start_time) * 1000
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {request.method} {request.path} -> {response.status_code} ({elapsed:.0f}ms)", flush=True)
    return response

# 自动迁移：如果存在旧的 study_memory.json 且数据库为空，则导入
if os.path.exists("study_memory.json"):
    tasks = agent.memory.data.get("tasks", [])
    if not tasks:
        try:
            agent.memory.migrate_from_json("study_memory.json")
            print("已自动从 study_memory.json 迁移数据到 SQLite")
        except Exception as e:
            print(f"数据迁移失败: {e}")


# ---- 页面 ----
@app.route("/")
def index():
    return render_template("index.html")


# ---- API ----
@app.route("/api/tasks", methods=["GET"])
def get_tasks():
    tasks = agent.memory.data.get("tasks", [])
    ranked = sorted(tasks, key=lambda t: t.get("priority", 0), reverse=True)
    return jsonify(ranked)


@app.route("/api/tasks", methods=["POST"])
def add_task():
    data = request.json
    result = agent.memory.add_task(
        task_name=data["task_name"],
        deadline=data["deadline"],
        category=data.get("category", "其他"),
        mastery=data.get("mastery", "生疏"),
        estimated_hours=float(data.get("estimated_hours", 1.0)),
    )
    return jsonify({"message": result["message"]})


@app.route("/api/tasks/<int:idx>/review", methods=["POST"])
def mark_reviewed(idx):
    result = agent.memory.mark_reviewed(idx)
    print(f"[任务] 标记复习: {result}", flush=True)
    return jsonify({"message": result})


@app.route("/api/tasks/<int:idx>", methods=["DELETE"])
def delete_task(idx):
    result = agent.memory.delete_task(idx)
    print(f"[任务] 删除: {result}", flush=True)
    return jsonify({"message": result})


@app.route("/api/daily-record", methods=["GET"])
def get_daily_record():
    date_str = request.args.get("date")
    record = agent.memory.get_daily_record(date_str)
    if isinstance(record, dict):
        return jsonify(record)
    return jsonify({"raw_content": record, "summary": record})


@app.route("/api/daily-record", methods=["POST"])
def record_daily():
    """分析学习记录，流式输出过程，最后返回结构化数据"""
    data = request.json
    content = data["content"]
    try:
        def generate():
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

3. **正误判断**：分析学习内容中用户的理解是否正确，指出：
   - correct_points: 正确的观点/理解（2-4条）
   - mistakes: 错误或有问题的地方（如果有的话，指出错误并给出正确解释；如果没有，返回空数组）
   - 注意：要基于客观事实判断，对于主观内容不要轻易判断对错

4. **核心要点总结**：用简洁的语言总结学习内容的核心要点（不超过100字）

5. **改进建议**：如果内容质量较低，给出具体的改进建议

6. **标签建议**：建议3-5个标签

请以JSON格式输出，不要添加任何额外文字：
{{
    "quality_score": 分数,
    "quality_comment": "质量评价",
    "knowledge_points": [{{"name": "xxx", "type": "xxx", "description": "xxx"}}],
    "correct_points": ["正确点1", "正确点2"],
    "mistakes": [{{"content": "错误内容", "explanation": "正确解释"}}],
    "summary": "核心要点",
    "improvement_suggestions": ["建议1", "建议2"],
    "tags": ["标签1", "标签2"]
}}
"""
            stream_resp = agent.client.chat.completions.create(
                model="glm-4-flash",
                messages=[{"role": "user", "content": analysis_prompt}],
                temperature=0.3,
                timeout=60,
                stream=True
            )
            full_content = ""
            for chunk in stream_resp:
                delta = chunk.choices[0].delta
                if delta.content:
                    safe_text = ChatSession._clean_surrogates(delta.content)
                    full_content += safe_text
                    yield f"data: {json.dumps({'type': 'text', 'content': safe_text}, ensure_ascii=False)}\n\n"

            result = full_content.strip()
            if result.startswith("```"):
                lines = result.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                result = "\n".join(lines).strip()

            try:
                analysis = json.loads(result)
                structured = {
                    "raw_content": content,
                    "knowledge_points": analysis.get("knowledge_points", []),
                    "mastery_level": "生疏",
                    "tags": analysis.get("tags", []),
                    "summary": analysis.get("summary", content),
                    "quality_score": analysis.get("quality_score", 0) * 10,
                    "quality_comment": analysis.get("quality_comment", ""),
                    "improvement_suggestions": analysis.get("improvement_suggestions", []),
                    "correct_points": analysis.get("correct_points", []),
                    "mistakes": analysis.get("mistakes", []),
                }
                yield f"data: {json.dumps({'type': 'done', 'data': structured}, ensure_ascii=False)}\n\n"
            except json.JSONDecodeError:
                structured = {
                    "raw_content": content,
                    "knowledge_points": [],
                    "mastery_level": "生疏",
                    "tags": [],
                    "summary": content,
                    "quality_score": 0,
                    "quality_comment": "解析失败",
                    "improvement_suggestions": [],
                    "correct_points": [],
                    "mistakes": [],
                }
                yield f"data: {json.dumps({'type': 'done', 'data': structured}, ensure_ascii=False)}\n\n"

        return Response(generate(), mimetype="text/event-stream")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/record-chat", methods=["POST"])
def record_chat():
    """学习记录对话：支持多轮对话优化学习记录，流式输出"""
    data = request.json
    message = data.get("message", "")
    history = data.get("history", [])
    current_record = data.get("current_record", None)

    if not message:
        return jsonify({"error": "请输入对话内容"}), 400

    def generate():
        system_prompt = """你是一位学习记录分析助手，帮助用户完善和优化学习记录。

你的职责：
1. 分析用户描述的学习内容，提取核心知识点
2. 评估学习质量，给出质量评分（0-100分）
3. 正误判断：分析用户的理解是否正确，指出正确点和错误点
4. 用简洁语言总结核心要点
5. 给出改进建议
6. 建议相关标签
7. 评估掌握程度（生疏/一般/熟悉/精通）

【重要规则】
- 每一轮对话都要基于当前已有的记录，整合用户新说的内容
- raw_content 字段必须包含完整的学习内容（所有轮次的内容都要整合进去）
- 知识点要去重，相同或相似的知识点合并
- 如果用户补充了新内容，要把新内容追加到 raw_content 中，并更新知识点和总结
- 不要只保留最后一轮的内容，要保留所有学习过的内容
- 正误判断要基于客观事实，对于主观内容不要轻易判断对错
- 如果没有明显错误，mistakes 数组返回空

对话规则：
- 第一次对话时，根据用户描述直接生成完整的结构化分析结果
- 后续对话中，根据用户的要求修改、补充、优化学习记录
- 用户可以要求：增加知识点、修改评分、补充内容、调整掌握程度等
- 每一轮回复最后都要输出最新的完整JSON结构

【输出格式要求】
用自然、友好的语气回复用户，说明你做了什么修改，或者对学习内容的分析。
回复的最后部分，用```json和```包裹最新的完整结构化数据。

JSON格式如下（必须是严格的JSON）：
```json
{
    "raw_content": "完整的学习内容描述，包含所有轮次对话中提到的学习内容",
    "knowledge_points": [
        {"name": "知识点名称", "type": "概念/原理/方法/工具/案例/其他", "description": "详细描述"}
    ],
    "correct_points": ["正确的理解1", "正确的理解2"],
    "mistakes": [
        {"content": "错误的内容", "explanation": "正确的解释"}
    ],
    "mastery_level": "生疏/一般/熟悉/精通",
    "tags": ["标签1", "标签2"],
    "summary": "核心要点总结（涵盖所有内容）",
    "quality_score": 0-100的整数,
    "quality_comment": "质量评价说明",
    "improvement_suggestions": ["改进建议1", "改进建议2"]
}
```

回复风格：简洁明了，不用太正式，像朋友一样交流。
"""
        messages = [{"role": "system", "content": system_prompt}]

        if current_record:
            messages.append({
                "role": "user",
                "content": f"这是我当前的学习记录，请基于它继续完善：\n```json\n{json.dumps(current_record, ensure_ascii=False, indent=2)}\n```\n\n重要：所有新学习的内容都要整合到这份记录里。raw_content要包含所有学习内容（之前的+新补充的），知识点要去重合并，不要只保留新内容。"
            })
            messages.append({
                "role": "assistant",
                "content": "好的，我会在这份记录的基础上继续完善，把新内容整合进去，确保记录完整。"
            })

        messages.append({"role": "user", "content": message})

        stream_resp = agent.client.chat.completions.create(
            model="glm-4-flash",
            messages=messages,
            temperature=0.3,
            timeout=120,
            stream=True
        )

        full_content = ""
        for chunk in stream_resp:
            delta = chunk.choices[0].delta
            if delta.content:
                safe_text = ChatSession._clean_surrogates(delta.content)
                full_content += safe_text
                yield f"data: {json.dumps({'type': 'text', 'content': safe_text}, ensure_ascii=False)}\n\n"

        # 解析JSON
        parsed_record = _extract_json_from_text(full_content)
        if parsed_record:
            if not parsed_record.get("raw_content"):
                parsed_record["raw_content"] = message
            yield f"data: {json.dumps({'type': 'done', 'record': parsed_record, 'full_text': full_content}, ensure_ascii=False)}\n\n"
        else:
            yield f"data: {json.dumps({'type': 'done', 'record': None, 'full_text': full_content, 'error': '无法解析JSON结构'}, ensure_ascii=False)}\n\n"

    return Response(generate(), mimetype="text/event-stream")


def _extract_json_from_text(text):
    """从AI回复文本中提取JSON结构"""
    import re
    json_str = None
    # 尝试匹配 ```json ... ``` 格式
    match = re.search(r'```json\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        json_str = match.group(1).strip()
    else:
        # 尝试找第一个 { 和最后一个 }
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            json_str = text[start:end+1]

    if json_str:
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return None
    return None


@app.route("/api/daily-record/confirm", methods=["POST"])
def confirm_daily_record():
    data = request.json
    result = agent.memory.record_daily_structured(
        content=data["raw_content"],
        knowledge_points=data.get("knowledge_points", []),
        mastery_level=data.get("mastery_level", "生疏"),
        tags=data.get("tags", []),
        summary=data.get("summary", ""),
    )
    # 自动生成复习任务（用带id的知识点列表）
    auto_tasks = _generate_review_tasks_from_record(
        result.get("knowledge_points", []),
        data.get("mastery_level", "生疏"),
        data.get("summary", "")
    )
    # 自动关联现有任务：把知识点和名称匹配的任务建立强关联
    linked_count = _auto_link_knowledge_to_tasks(result.get("knowledge_points", []))
    print(f"[学习记录] 保存成功，自动生成 {len(auto_tasks)} 个复习任务，自动关联 {linked_count} 个现有任务", flush=True)
    return jsonify({"message": result["message"], "auto_tasks": auto_tasks})


def _auto_link_knowledge_to_tasks(knowledge_points):
    """把知识点自动关联到名称匹配的现有任务（强关联）"""
    if not knowledge_points:
        return 0

    conn = agent.memory._get_conn()
    c = conn.cursor()
    c.execute("SELECT id, task FROM tasks ORDER BY priority DESC")
    tasks = c.fetchall()
    if not tasks:
        conn.close()
        return 0

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linked_count = 0

    for kp in knowledge_points:
        kp_name = kp.get("name", "")
        kp_id = kp.get("id")
        if not kp_name or not kp_id:
            continue

        # 清理知识点名称，用于匹配
        clean_kp = kp_name.strip()

        for task in tasks:
            task_id = task["id"]
            task_name = task["task"]
            clean_task = task_name.replace("复习：", "").replace("（第1天）", "").replace("（第7天）", "").strip()

            # 匹配规则：任务名包含知识点名，或知识点名包含任务名
            is_match = False
            if clean_kp and clean_task:
                if clean_kp == clean_task:
                    is_match = True
                elif len(clean_kp) >= 3 and clean_kp in clean_task:
                    is_match = True
                elif len(clean_task) >= 3 and clean_task in clean_kp:
                    is_match = True

            if is_match:
                c.execute(
                    "INSERT OR IGNORE INTO task_knowledge_points (task_id, knowledge_id, create_time) VALUES (?, ?, ?)",
                    (task_id, kp_id, now_str)
                )
                if c.rowcount > 0:
                    linked_count += 1

    conn.commit()
    conn.close()
    return linked_count


def _generate_review_tasks_from_record(knowledge_points, mastery_level, summary):
    """根据学习记录的知识点自动生成复习任务（已存在则跳过）"""
    if not knowledge_points:
        return []

    today = datetime.datetime.now()
    forgetting_nodes = [1, 2, 4, 7, 15]  # 艾宾浩斯遗忘曲线节点
    created_tasks = []

    # 先获取现有复习任务，用于去重
    existing_tasks = set()
    try:
        conn = agent.memory._get_conn()
        c = conn.cursor()
        c.execute("SELECT task, deadline FROM tasks WHERE category='复习'")
        for row in c.fetchall():
            existing_tasks.add((row["task"], row["deadline"]))
        conn.close()
    except Exception:
        pass

    # 选取前5个最重要的知识点生成任务
    important_kps = knowledge_points[:5]
    category = "复习"

    for idx, kp in enumerate(important_kps):
        kp_name = kp.get("name", f"知识点{idx+1}")
        kp_type = kp.get("type", "概念")
        kp_desc = kp.get("description", "")

        # 根据知识点类型调整基础优先级
        base_priority = 80
        if kp_type == "原理":
            base_priority = 90
        elif kp_type == "概念":
            base_priority = 75
        elif kp_type == "应用":
            base_priority = 85

        # 根据掌握程度调整
        if mastery_level == "生疏":
            base_priority += 10
        elif mastery_level == "熟悉":
            base_priority -= 10
        elif mastery_level == "精通":
            base_priority -= 20

        # 只在第1天和第7天生成任务（避免任务太多）
        review_days = [1, 7]
        for day_offset in review_days:
            deadline = (today + datetime.timedelta(days=day_offset)).strftime("%Y-%m-%d")
            task_name = f"复习：{kp_name}（第{day_offset}天）"
            priority = max(30, base_priority - day_offset * 5)

            # 去重检查：已存在则跳过
            if (task_name, deadline) in existing_tasks:
                continue

            try:
                task_result = agent.memory.add_task(
                    task_name=task_name,
                    deadline=deadline,
                    category=category,
                    mastery="生疏",
                    estimated_hours=0.5
                )
                task_id = task_result.get("task_id")
                # 关联知识点和任务
                if task_id and kp.get("id"):
                    agent.memory.link_task_knowledge(task_id, kp["id"])
                created_tasks.append({
                    "task": task_name,
                    "deadline": deadline,
                    "priority": priority,
                    "knowledge_point": kp_name,
                    "review_day": day_offset
                })
                existing_tasks.add((task_name, deadline))
            except Exception as e:
                print(f"[自动任务] 生成任务失败: {e}", flush=True)

    return created_tasks


@app.route("/api/review-plan", methods=["POST"])
def review_plan():
    """生成结构化复习计划 + 艾宾浩斯曲线数据"""
    try:
        conn = agent.memory._get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM tasks ORDER BY priority DESC")
        db_tasks = [dict(row) for row in c.fetchall()]
        conn.close()

        records = agent.memory.data.get("daily_record", {})
        today = datetime.datetime.now()

        today_str = today.strftime("%Y-%m-%d")
        today_tasks = []
        week_tasks = []
        later_tasks = []

        for idx, task in enumerate(db_tasks):
            if task.get("status") == "已完成":
                continue
            deadline_str = task.get("deadline", "")
            try:
                deadline = datetime.datetime.strptime(deadline_str, "%Y-%m-%d")
                days_left = (deadline - today).days
            except (ValueError, TypeError):
                days_left = 999

            task_info = {
                "task_index": idx,
                "name": task.get("task", ""),
                "deadline": deadline_str,
                "priority": task.get("priority", 0),
                "mastery": task.get("mastery", "生疏"),
                "category": task.get("category", "其他"),
                "review_count": task.get("review_count", 0),
                "days_left": days_left,
                "estimated_hours": task.get("estimated_hours", 1.0)
            }

            if days_left <= 0:
                today_tasks.append(task_info)
            elif days_left <= 7:
                week_tasks.append(task_info)
            else:
                later_tasks.append(task_info)

        today_tasks.sort(key=lambda x: (-x["priority"], x["days_left"]))
        week_tasks.sort(key=lambda x: (x["days_left"], -x["priority"]))
        later_tasks.sort(key=lambda x: (x["days_left"], -x["priority"]))

        # 计算今日总时长
        today_hours = sum(t.get("estimated_hours", 1.0) for t in today_tasks)

        # 艾宾浩斯遗忘曲线数据（记忆保留率 %）
        # 横轴：天数，纵轴：保留率
        forgetting_curve = {
            "labels": ["0天", "20分钟", "1小时", "9小时", "1天", "2天", "6天", "31天"],
            "retention": [100, 58.2, 44.2, 35.8, 33.7, 27.8, 25.4, 21.1],
            "review_nodes": [
                {"day": 0, "label": "学习当天", "tip": "首次学习，记忆最清晰"},
                {"day": 1, "label": "第1次复习", "tip": "24小时内复习，保留率从33%回升至90%"},
                {"day": 2, "label": "第2次复习", "tip": "第2天复习，巩固短期记忆"},
                {"day": 4, "label": "第3次复习", "tip": "第4天复习，过渡到中期记忆"},
                {"day": 7, "label": "第4次复习", "tip": "第7天复习，形成长期记忆"},
                {"day": 15, "label": "第5次复习", "tip": "第15天复习，记忆基本稳定"}
            ]
        }

        # 按复习节点整理记录
        record_review_status = []
        for date_str, content in records.items():
            try:
                record_date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
                days_since = (today - record_date).days
            except (ValueError, TypeError):
                continue

            # 判断当前处于哪个复习节点
            next_node = None
            nodes = [1, 2, 4, 7, 15]
            for n in nodes:
                if days_since <= n:
                    next_node = n
                    break

            kps = []
            if isinstance(content, dict):
                kps = [kp.get("name", "") for kp in content.get("knowledge_points", [])[:3]]

            record_review_status.append({
                "date": date_str,
                "days_since": days_since,
                "next_review_day": next_node,
                "knowledge_points": kps,
                "is_due_today": next_node is not None and days_since >= next_node - 1 and days_since <= next_node
            })

        record_review_status.sort(key=lambda x: x["days_since"])

        print(f"[复习计划] 生成成功：今日{len(today_tasks)}个，本周{len(week_tasks)}个", flush=True)

        return jsonify({
            "today_tasks": today_tasks,
            "week_tasks": week_tasks,
            "later_tasks": later_tasks,
            "today_hours": round(today_hours, 1),
            "forgetting_curve": forgetting_curve,
            "record_review_status": record_review_status,
            "total_records": len(records),
            "total_tasks": len(db_tasks)
        })
    except Exception as e:
        print(f"[复习计划] 生成失败: {e}", flush=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json
    prompt = data.get("prompt", "")
    stream = data.get("stream", True)

    if not stream:
        try:
            reply = agent.chat(prompt, stream=False, use_tools=True)
            return jsonify({"reply": reply})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # 流式输出
    def generate():
        agent.session.add_message("user", prompt)
        system_prompt = (
            f"你是一个专注的学习助手，只能帮助用户进行学习相关的对话。你的职责包括：帮助复盘学习内容、制定复习计划、添加学习任务、记录学习内容、解答学习问题等。\n"
            f"重要规则：\n"
            f"1. 严禁闲聊！如果用户的话题与学习无关（如闲聊天气、聊天打发时间、讲笑话、讨论娱乐等），你必须礼貌地拒绝，并引导用户回到学习话题。\n"
            f"2. 拒绝时的回复风格：温和但坚定，例如\"我是学习助手，只讨论学习相关的话题哦~有什么学习上的问题我可以帮你？\"\n"
            f"3. 允许的学习相关话题：学术知识问答、学习计划制定、知识点梳理、错题分析、考试备考、学习方法和技巧等。\n"
            f"当前日期：{agent.memory.get_now_date()}"
        )
        messages = agent.session.get_messages(system_prompt)
        kwargs = {
            "model": "glm-4-flash",
            "messages": messages,
            "temperature": 0.3,
            "timeout": 60,
            "tools": agent.TOOLS,
            "stream": True,
        }
        stream_resp = agent.client.chat.completions.create(**kwargs)

        full_content = ""
        tool_calls_buffer = {}
        current_tool_calls = False

        for chunk in stream_resp:
            delta = chunk.choices[0].delta

            # 处理文本内容
            if delta.content:
                safe_text = ChatSession._clean_surrogates(delta.content)
                full_content += safe_text
                yield f"data: {json.dumps({'type': 'text', 'content': safe_text}, ensure_ascii=False)}\n\n"

            # 处理 tool calls
            if hasattr(delta, 'tool_calls') and delta.tool_calls:
                current_tool_calls = True
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_buffer:
                        tool_calls_buffer[idx] = {
                            "id": "",
                            "name": "",
                            "arguments": ""
                        }
                    if tc.id:
                        tool_calls_buffer[idx]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            tool_calls_buffer[idx]["name"] = tc.function.name
                        if tc.function.arguments:
                            tool_calls_buffer[idx]["arguments"] += tc.function.arguments

        # 如果有 tool calls，执行工具并继续
        if current_tool_calls and tool_calls_buffer:
            tool_calls_serialized = []
            for idx in sorted(tool_calls_buffer.keys()):
                tc_data = tool_calls_buffer[idx]
                tool_calls_serialized.append({
                    "id": tc_data["id"],
                    "type": "function",
                    "function": {
                        "name": tc_data["name"],
                        "arguments": tc_data["arguments"]
                    }
                })

            agent.session.add_tool_call_message(tool_calls_serialized)
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": tool_calls_serialized
            })

            for tc_data in sorted(tool_calls_buffer.values(), key=lambda x: x["id"]):
                func_name = tc_data["name"]
                func_args = json.loads(tc_data["arguments"])
                yield f"data: {json.dumps({'type': 'tool_call', 'name': func_name, 'args': tc_data['arguments']}, ensure_ascii=False)}\n\n"

                result = agent._execute_tool(func_name, func_args)
                messages.append({
                    "role": "tool",
                    "content": ChatSession._clean_surrogates(str(result)),
                    "tool_call_id": tc_data["id"]
                })
                agent.session.add_tool_result(tc_data["id"], result)
                yield f"data: {json.dumps({'type': 'tool_result', 'name': func_name, 'result': str(result)[:200]}, ensure_ascii=False)}\n\n"

            # 继续调用 LLM
            kwargs2 = {
                "model": "glm-4-flash",
                "messages": messages,
                "temperature": 0.3,
                "timeout": 60,
                "tools": agent.TOOLS,
                "stream": True,
            }
            stream_resp2 = agent.client.chat.completions.create(**kwargs2)
            for chunk in stream_resp2:
                delta = chunk.choices[0].delta
                if delta.content:
                    safe_text = ChatSession._clean_surrogates(delta.content)
                    full_content += safe_text
                    yield f"data: {json.dumps({'type': 'text', 'content': safe_text}, ensure_ascii=False)}\n\n"

        if full_content:
            agent.session.add_message("assistant", full_content)

        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return Response(generate(), mimetype="text/event-stream")


@app.route("/api/task/<int:idx>/knowledge-points", methods=["GET"])
def task_knowledge_points(idx):
    """获取任务相关的知识点（优先强关联，旧数据fallback到关键词匹配）"""
    try:
        # 先从中间表查（强关联）
        kps = agent.memory.get_task_knowledge_points(idx)
        if kps:
            task = agent.memory.get_task_by_index(idx)
            task_name = task["task"] if task else f"任务{idx+1}"
            return jsonify({"task": task_name, "knowledge_points": kps, "source": "linked"})

        # 没有强关联数据，fallback到关键词匹配
        conn = agent.memory._get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM tasks ORDER BY priority DESC")
        tasks = c.fetchall()
        if idx < 0 or idx >= len(tasks):
            conn.close()
            return jsonify({"error": "任务不存在"}), 400
        task = tasks[idx]
        task_name = task["task"]
        task_category = task["category"]

        # 从所有知识点中匹配和任务相关的
        c.execute("SELECT * FROM knowledge_points ORDER BY id DESC LIMIT 100")
        all_kps = c.fetchall()
        conn.close()

        # 清理任务名称，去除复习前缀和天数后缀
        clean_name = task_name.replace("复习：", "").replace("（第1天）", "").replace("（第7天）", "").strip()
        task_cat = (task_category or "").strip()

        # 提取关键词（2字以上），并过滤停用词
        raw_words = re.findall(r'[\u4e00-\u9fa5A-Za-z0-9+#]{2,}', clean_name)
        keywords = set(w for w in raw_words if w not in STOP_WORDS)

        # 如果关键词太少，再用滑动窗口提取技术短语（仅连续汉字/字母组合）
        if len(keywords) < 2:
            for i in range(len(clean_name) - 1):
                for length in range(2, min(5, len(clean_name) - i + 1)):
                    word = clean_name[i:i+length]
                    # 只保留纯中文或纯英文/数字的组合，排除混合无意义片段
                    if re.match(r'^[\u4e00-\u9fa5]{2,}$', word) or re.match(r'^[A-Za-z0-9+#]{2,}$', word):
                        if word not in STOP_WORDS:
                            keywords.add(word)

        matched = []
        for kp in all_kps:
            kp_name = kp["name"]
            kp_desc = kp["description"] or ""
            kp_type = (kp["type"] or "").strip()
            score = 0
            name_hit_count = 0  # 命中名称的关键词数量

            # 完全匹配知识点名称（最高优先级）
            if kp_name == clean_name:
                score += 100

            # 分类相同加分（同领域优先）
            if task_cat and kp_type and task_cat == kp_type:
                score += 15

            # 关键词匹配
            for kw in keywords:
                if len(kw) < 2:
                    continue
                if kw in kp_name:
                    # 关键词越长，分数越高；名称命中权重高
                    score += len(kw) * 5
                    name_hit_count += 1
                elif kw in kp_desc:
                    # 描述命中权重低
                    score += len(kw) * 1

            # 反向匹配：知识点名称中的重要词在任务名称里
            kp_words = re.findall(r'[\u4e00-\u9fa5A-Za-z0-9+#]{2,}', kp_name)
            kp_keywords = set(w for w in kp_words if w not in STOP_WORDS)
            reverse_hits = 0
            for kw in kp_keywords:
                if kw in clean_name and len(kw) >= 2:
                    score += len(kw) * 3
                    reverse_hits += 1

            # 严格过滤：必须至少有一个关键词命中名称（避免仅描述命中导致的无关）
            has_name_hit = (name_hit_count > 0) or (reverse_hits > 0) or (kp_name == clean_name)
            if not has_name_hit:
                continue

            # 分数阈值：至少15分才算匹配
            if score >= 15:
                matched.append({
                    "id": kp["id"],
                    "name": kp["name"],
                    "type": kp["type"],
                    "description": kp["description"],
                    "score": score
                })

        matched.sort(key=lambda x: x["score"], reverse=True)
        matched = matched[:5]  # 最多返回5个

        # 如果没匹配到，就用任务名称本身作为一个知识点
        if not matched:
            matched = [{
                "id": 0,
                "name": clean_name,
                "type": task_category,
                "description": task_name,
                "score": 1
            }]

        return jsonify({"task": task_name, "knowledge_points": matched, "source": "matched"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/knowledge/list", methods=["GET"])
def knowledge_list():
    """获取所有知识点列表（供选择关联）"""
    try:
        conn = agent.memory._get_conn()
        c = conn.cursor()
        c.execute("SELECT id, name, type, description FROM knowledge_points ORDER BY id DESC LIMIT 200")
        kps = [dict(row) for row in c.fetchall()]
        conn.close()
        return jsonify({"knowledge_points": kps})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/task/<int:idx>/knowledge-link", methods=["POST"])
def link_knowledge_to_task(idx):
    """给任务关联知识点（强关联）"""
    try:
        data = request.json or {}
        kp_ids = data.get("knowledge_ids", [])
        if not kp_ids:
            return jsonify({"error": "请选择要关联的知识点"}), 400

        conn = agent.memory._get_conn()
        c = conn.cursor()
        c.execute("SELECT id FROM tasks ORDER BY priority DESC")
        tasks = c.fetchall()
        if idx < 0 or idx >= len(tasks):
            conn.close()
            return jsonify({"error": "任务不存在"}), 400
        task_id = tasks[idx]["id"]

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for kp_id in kp_ids:
            c.execute(
                "INSERT OR IGNORE INTO task_knowledge_points (task_id, knowledge_id, create_time) VALUES (?, ?, ?)",
                (task_id, kp_id, now_str)
            )
        conn.commit()
        conn.close()
        print(f"[强关联] 任务{idx+1} 关联了 {len(kp_ids)} 个知识点", flush=True)
        return jsonify({"message": f"成功关联 {len(kp_ids)} 个知识点"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/task/<int:idx>/knowledge-unlink", methods=["POST"])
def unlink_knowledge_from_task(idx):
    """移除任务关联的知识点"""
    try:
        data = request.json or {}
        kp_id = data.get("knowledge_id")
        if not kp_id:
            return jsonify({"error": "请提供知识点ID"}), 400

        conn = agent.memory._get_conn()
        c = conn.cursor()
        c.execute("SELECT id FROM tasks ORDER BY priority DESC")
        tasks = c.fetchall()
        if idx < 0 or idx >= len(tasks):
            conn.close()
            return jsonify({"error": "任务不存在"}), 400
        task_id = tasks[idx]["id"]

        c.execute(
            "DELETE FROM task_knowledge_points WHERE task_id=? AND knowledge_id=?",
            (task_id, kp_id)
        )
        conn.commit()
        conn.close()
        print(f"[强关联] 任务{idx+1} 移除了知识点 {kp_id}", flush=True)
        return jsonify({"message": "已移除关联"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/knowledge/explain", methods=["POST"])
def knowledge_explain():
    """讲解一个知识点，流式输出讲解内容"""
    data = request.json or {}
    kp_name = data.get("name", "")
    kp_type = data.get("type", "")
    kp_desc = data.get("description", "")

    if not kp_name:
        return jsonify({"error": "请提供知识点名称"}), 400

    def generate():
        system_prompt = f"""你是一位知识渊博、耐心细致的学习导师，负责为学生讲解知识点。

请用通俗易懂的方式讲解以下知识点：
- 知识点名称：{kp_name}
- 知识点类型：{kp_type or '未指定'}
- 简短描述：{kp_desc or '未提供'}

讲解要求：
1. 先给出一个简洁的定义（1-2句话）
2. 然后详细讲解核心概念和原理
3. 举1-2个具体的例子帮助理解
4. 说明这个知识点的应用场景/为什么重要
5. 最后给出一个简单的记忆技巧/学习建议

讲解风格：
- 通俗易懂，像老师给学生讲课一样
- 条理清晰，分点说明
- 适当使用比喻帮助理解
- 不要太学术化，要接地气
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请帮我详细讲解一下「{kp_name}」这个知识点"}
        ]

        stream_resp = agent.client.chat.completions.create(
            model="glm-4-flash",
            messages=messages,
            temperature=0.6,
            timeout=120,
            stream=True
        )

        full_content = ""
        for chunk in stream_resp:
            delta = chunk.choices[0].delta
            if delta.content:
                safe_text = ChatSession._clean_surrogates(delta.content)
                full_content += safe_text
                yield f"data: {json.dumps({'type': 'text', 'content': safe_text}, ensure_ascii=False)}\n\n"

        yield f"data: {json.dumps({'type': 'done', 'full_text': full_content}, ensure_ascii=False)}\n\n"

    return Response(generate(), mimetype="text/event-stream")


@app.route("/api/quiz/start", methods=["POST"])
def quiz_start():
    """开始考察模式，流式返回第一道题
    支持传入 task_index 或 knowledge_points 来指定考察内容
    """
    try:
        data = request.get_json(silent=True) or {}
        task_index = data.get("task_index")
        custom_knowledge_points = data.get("knowledge_points")
        custom_title = data.get("title", "")
        source_page = data.get("source_page", "")

        records = agent.memory.data.get("daily_record", {})
        today = datetime.datetime.now()

        knowledge_points_for_quiz = []
        tasks_str = ""
        quiz_context = ""

        # 如果指定了知识点或任务，就用指定的内容
        if custom_knowledge_points:
            knowledge_points_for_quiz = [
                {"name": kp.get("name", ""), "type": kp.get("type", ""), "description": kp.get("description", "")}
                for kp in custom_knowledge_points
            ]
            tasks_str = custom_title or "指定知识点考察"
            quiz_context = f"本次考察范围：{custom_title or '指定知识点'}"
        elif task_index is not None:
            # 根据任务索引找对应的任务
            conn = agent.memory._get_conn()
            c = conn.cursor()
            c.execute("SELECT id, task, category, mastery FROM tasks ORDER BY priority DESC")
            tasks = c.fetchall()
            if task_index < 0 or task_index >= len(tasks):
                conn.close()
                return jsonify({"error": "任务不存在"}), 400
            task = tasks[task_index]
            task_id = task["id"]
            task_name = task["task"]
            task_category = task["category"]
            task_mastery = task["mastery"]

            # 先查强关联的知识点（优先用强关联）
            c.execute("""
                SELECT kp.id, kp.name, kp.type, kp.description
                FROM knowledge_points kp
                INNER JOIN task_knowledge_points tkp ON kp.id = tkp.knowledge_id
                WHERE tkp.task_id = ?
                ORDER BY tkp.id
            """, (task_id,))
            linked_kps = c.fetchall()

            if linked_kps:
                matched_kps = linked_kps
                conn.close()
            else:
                # 没有强关联，fallback到关键词匹配
                c.execute("SELECT * FROM knowledge_points ORDER BY id DESC LIMIT 100")
                all_kps = c.fetchall()
                conn.close()

                clean_name = task_name.replace("复习：", "").replace("（第1天）", "").replace("（第7天）", "").strip()
                raw_words = re.findall(r'[\u4e00-\u9fa5A-Za-z0-9+#]{2,}', clean_name)
                keywords = set(w for w in raw_words if w not in STOP_WORDS)

                matched_kps = []
                for kp in all_kps:
                    kp_name = kp["name"]
                    score = 0
                    for kw in keywords:
                        if len(kw) >= 2 and kw in kp_name:
                            score += len(kw) * 3
                    if score >= 6:
                        matched_kps.append(kp)

                matched_kps.sort(key=lambda x: len(x["name"]), reverse=True)
                matched_kps = matched_kps[:5]

            if matched_kps:
                knowledge_points_for_quiz = [
                    {"name": kp["name"], "type": kp["type"], "description": kp["description"]}
                    for kp in matched_kps
                ]
            else:
                knowledge_points_for_quiz = [
                    {"name": task_name, "type": "任务", "description": task_name}
                ]

            tasks_str = f"{task_name}（{task_mastery}）"
            quiz_context = f"本次考察任务：{task_name}（掌握程度：{task_mastery}）"
        else:
            # 默认模式：从所有学习记录的知识点中选
            conn = agent.memory._get_conn()
            c = conn.cursor()
            c.execute("""
                SELECT kp.id, kp.name, kp.type, kp.description, dr.date
                FROM knowledge_points kp
                INNER JOIN daily_records dr ON kp.record_id = dr.id
                ORDER BY dr.date DESC
                LIMIT 50
            """)
            all_kps = c.fetchall()
            conn.close()

            if not all_kps:
                return jsonify({"error": "暂无知识点，请先记录学习内容"}), 400

            kp_with_urgency = []
            for kp in all_kps:
                try:
                    record_date = datetime.datetime.strptime(kp["date"], "%Y-%m-%d")
                    days_since = (today - record_date).days
                except ValueError:
                    days_since = 0
                forgetting_nodes = [1, 2, 4, 7, 15]
                need_review = any(abs(days_since - n) <= 1 for n in forgetting_nodes) or days_since >= 15
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
                kp_with_urgency.append({
                    "name": kp["name"],
                    "type": kp["type"],
                    "description": kp["description"],
                    "days_since": days_since,
                    "urgency": urgency,
                    "need_review": need_review
                })

            kp_with_urgency.sort(key=lambda x: (x["need_review"], x["urgency"]), reverse=True)
            knowledge_points_for_quiz = kp_with_urgency[:8]
            tasks_str = agent.memory.get_task_ranking()
            quiz_context = "本次考察范围：按遗忘紧急度排序的知识点"

        # 构造知识点列表文本
        kp_list_text = ""
        for i, kp in enumerate(knowledge_points_for_quiz, 1):
            kp_list_text += f"{i}. [{kp.get('type', '其他')}] {kp.get('name', '')}\n"
            if kp.get('description'):
                kp_list_text += f"   描述：{kp['description']}\n"
            if 'days_since' in kp:
                kp_list_text += f"   距今{kp['days_since']}天，遗忘紧急度{kp.get('urgency', '未知')}\n"
            kp_list_text += "\n"

        quiz_system_prompt = f"""你是一位来自一线大厂（字节/阿里/腾讯级）的资深技术面试官，正在进行一场高强度的压力面试。你的风格是：犀利、直接、不留情面、追问到底，像真实大厂面试一样给候选人施压。

【面试官人设】
- 你是技术委员会成员，面试过几百个候选人，眼光毒辣
- 说话直接、犀利，不绕弯子，对基础不扎实的回答毫不客气
- 喜欢连环追问，一层层往下挖，直到候选人答不上来为止
- 会质疑候选人的答案，即使答对了也会故意挑战，看候选人是否真的理解
- 对"大概"、"可能"、"应该是"这种模糊回答零容忍，要求精准
- 面试结束后会给出犀利的评价和残酷的定级（比如"连XX都不知道，简历是怎么过的？"）

当前日期：{agent.memory.get_now_date()}
{quiz_context}

【待考察知识点列表】
{kp_list_text}

候选人的任务列表（按优先级排序）：
{tasks_str}

【考察核心规则 —— 非常重要！】
1. 你是围绕上面的【知识点】来出题，考察候选人对知识点的**理解、应用、迁移能力**，绝对不是考原文背诵！
2. 严禁出"XX的定义是什么"、"XX的描述是什么"这种直接考原文记忆的题目！
3. 要出的题目类型包括：
   - 原理理解题：为什么是这样？底层机制是什么？
   - 应用场景题：在什么场景下用？解决什么问题？
   - 对比分析题：和XX有什么区别？各自优劣？
   - 场景设计题：给一个具体场景，怎么用这个知识点解决？
   - 排错分析题：出了XX问题，可能是什么原因？怎么排查？
   - 手撕代码题：如果是算法/编程知识点，现场写代码实现
   - 边界case题：极端情况怎么处理？有什么坑？
4. 优先考察遗忘紧急度高的知识点（距今较久、快忘了的）
5. 优先考察掌握程度"生疏"的任务相关知识点
6. 题型混合使用，难度递增
7. 难度策略：上来先扔一道中等难度的下马威，然后根据回答情况动态调整——答得好立刻加码，答不好直接降级但犀利嘲讽
8. 每次只出1道题，不要给出答案
9. 连环追问：如果候选人答对了，要追问更底层的原理、边界case、性能优化等，往深了挖
10. 如果回答模糊或有错误，直接指出，毫不客气，比如"这个理解有问题"、"你确定吗？"、"再想想"
11. 【非常重要】批改时不要直接甩答案！要先用【思路引导】带着候选人一步步思考，从考点分析→推理路径→常见误区→最终结论，像老师带学生解题一样，让候选人跟着你的思路走，最后再给出【正确答案】
12. 结束时给出犀利的综合评价，指出硬伤和薄弱点，像真实大厂面试反馈一样

【出题时的输出格式】（只输出题目，不要输出答案和解析）
【题目】(题型：xxx | 难度：xxx | 考察知识点：xxx)
题目内容

【收到候选人答案后的输出格式】（必须严格按照这个格式输出，每个板块都不能少！）
【结果】✅ 回答正确 / ❌ 回答错误 / ⚠️ 回答不完整
【面试官点评】（犀利直接的点评，可以有追问，可以质疑，可以指出硬伤）
【思路引导】（不要直接甩答案！先带着候选人一步步思考，像老师带学生解题一样：
  第一步：先点明这道题的核心考点是什么
  第二步：分析正确的解题思路应该从哪几个角度切入
  第三步：指出候选人的思路哪里对、哪里走偏了
  第四步：一步步推导，让候选人跟着你的思路得出结论
  语气要引导式，多用"你想想看"、"为什么呢"、"如果是这样的话"这种引导性语言）
【正确答案】（在思路引导之后，给出简洁、明确、完整的正确答案，让用户看完思路引导后能在这里看到最终结论）
【理解分析】哪些理解是对的，哪些有偏差，哪些知识点完全没掌握
【追问/下一题】（如果答得不错就继续追问加深；答得不好就出下一题但加点嘲讽）
（如果继续追问就输出【追问】，如果出下一题就输出【下一题】）
"""

        quiz_history = [{"role": "user", "content": "请根据我的知识点列表，优先考察遗忘紧急度高的，出第一道题。注意考察理解和应用，不要考原文背诵。只输出题目，不要给出答案。"}]
        messages = [{"role": "system", "content": quiz_system_prompt}] + quiz_history

        def generate():
            stream_resp = agent.client.chat.completions.create(
                model="glm-4-flash", messages=messages, temperature=0.7, stream=True
            )
            full_content = ""
            for chunk in stream_resp:
                delta = chunk.choices[0].delta
                if delta.content:
                    safe_text = ChatSession._clean_surrogates(delta.content)
                    full_content += safe_text
                    yield f"data: {json.dumps({'type': 'text', 'content': safe_text}, ensure_ascii=False)}\n\n"

            quiz_history.append({"role": "assistant", "content": full_content})
            app.config["quiz_history"] = quiz_history
            app.config["quiz_system_prompt"] = quiz_system_prompt
            app.config["quiz_source_page"] = source_page
            app.config["quiz_task_index"] = task_index

            question = _extract_question(full_content)
            yield f"data: {json.dumps({'type': 'done', 'question': question, 'raw': full_content, 'source_page': source_page, 'task_index': task_index}, ensure_ascii=False)}\n\n"

        print(f"[考察] 开始考察，知识点数: {len(knowledge_points_for_quiz)}", flush=True)
        return Response(generate(), mimetype="text/event-stream")
    except Exception as e:
        print(f"[考察] 出题失败: {e}", flush=True)
        return jsonify({"error": str(e)}), 500


def _extract_question(text):
    """从 LLM 返回中提取题目部分（下一题或追问）"""
    if "【下一题】" in text:
        parts = text.split("【下一题】")
        return "【下一题】" + parts[-1].strip()
    if "【追问】" in text:
        parts = text.split("【追问】")
        return "【追问】" + parts[-1].strip()
    return text.strip()


def _extract_answer_result(text):
    """从 LLM 返回中提取答案解析部分（不含下一题/追问）"""
    result_text = text
    if "【下一题】" in text:
        idx = text.find("【下一题】")
        result_text = text[:idx].strip()
    elif "【追问】" in text:
        idx = text.find("【追问】")
        result_text = text[:idx].strip()
    return result_text


def _analyze_quiz_results(quiz_history):
    """统计考察历史中的答题结果
    返回: {total, correct, partial, wrong, correct_rate}
    """
    total = 0
    correct = 0
    partial = 0
    wrong = 0

    for msg in quiz_history:
        if msg["role"] == "assistant":
            content = msg["content"]
            if "【结果】" not in content:
                continue
            total += 1
            if "✅ 回答正确" in content or "结果】✅" in content:
                correct += 1
            elif "⚠️ 回答不完整" in content or "结果】⚠️" in content:
                partial += 1
            elif "❌ 回答错误" in content or "结果】❌" in content:
                wrong += 1

    if total == 0:
        correct_rate = 0
    else:
        correct_rate = (correct + partial * 0.5) / total

    return {
        "total": total,
        "correct": correct,
        "partial": partial,
        "wrong": wrong,
        "correct_rate": round(correct_rate, 2)
    }


def _calc_new_mastery(old_mastery, correct_rate, total_questions):
    """根据正确率计算新的掌握程度
    - 正确率 >= 85% 且答题数 >= 3: 升一级
    - 正确率 50%-85%: 保持不变
    - 正确率 < 50% 且答题数 >= 3: 降一级
    """
    mastery_levels = ["生疏", "一般", "熟悉", "精通"]
    if old_mastery not in mastery_levels:
        old_mastery = "生疏"
    idx = mastery_levels.index(old_mastery)

    if total_questions >= 3:
        if correct_rate >= 0.85:
            new_idx = min(idx + 1, len(mastery_levels) - 1)
        elif correct_rate < 0.5:
            new_idx = max(idx - 1, 0)
        else:
            new_idx = idx
    else:
        new_idx = idx

    return mastery_levels[new_idx]


def _update_task_after_quiz(task_index, stats):
    """考察结束后更新任务信息（掌握程度、复习次数、最后复习时间）"""
    if task_index is None:
        return None

    try:
        conn = agent.memory._get_conn()
        c = conn.cursor()
        c.execute("SELECT id, task, review_count, mastery FROM tasks ORDER BY priority DESC")
        tasks = c.fetchall()
        if task_index < 0 or task_index >= len(tasks):
            conn.close()
            return None

        task = tasks[task_index]
        task_id = task["id"]
        old_mastery = task["mastery"]
        old_count = task["review_count"]

        new_mastery = _calc_new_mastery(old_mastery, stats["correct_rate"], stats["total"])
        new_count = old_count + 1
        now = agent.memory.get_now_date()

        c.execute(
            "UPDATE tasks SET review_count=?, mastery=?, last_review=? WHERE id=?",
            (new_count, new_mastery, now, task_id)
        )
        conn.commit()
        conn.close()

        agent.memory._recalc_priorities()
        agent.memory._sync_from_db()

        return {
            "task_name": task["task"],
            "old_mastery": old_mastery,
            "new_mastery": new_mastery,
            "mastery_changed": old_mastery != new_mastery,
            "old_review_count": old_count,
            "new_review_count": new_count,
        }
    except Exception as e:
        print(f"[考察] 更新任务掌握程度失败: {e}", flush=True)
        return None


@app.route("/api/quiz/answer", methods=["POST"])
def quiz_answer():
    """提交考察答案，流式返回批改结果"""
    data = request.json
    answer = data.get("answer", "")

    quiz_history = app.config.get("quiz_history", [])
    quiz_system_prompt = app.config.get("quiz_system_prompt", "")
    task_index = app.config.get("quiz_task_index")
    source_page = app.config.get("quiz_source_page", "")

    if answer.lower() == "q":
        quiz_history.append({"role": "user", "content": "面试结束，给我一个综合评价。说说我的硬伤在哪里，哪些知识点是薄弱项，离大厂要求还差多远，以及怎么改进。犀利一点，不要客气。"})
    else:
        quiz_history.append({"role": "user", "content": answer})

    messages = [{"role": "system", "content": quiz_system_prompt}] + quiz_history

    def generate():
        stream_resp = agent.client.chat.completions.create(
            model="glm-4-flash", messages=messages, temperature=0.6, stream=True
        )
        full_content = ""
        for chunk in stream_resp:
            delta = chunk.choices[0].delta
            if delta.content:
                safe_text = ChatSession._clean_surrogates(delta.content)
                full_content += safe_text
                yield f"data: {json.dumps({'type': 'text', 'content': safe_text}, ensure_ascii=False)}\n\n"

        quiz_history.append({"role": "assistant", "content": full_content})
        app.config["quiz_history"] = quiz_history

        if answer.lower() == "q":
            print(f"[考察] 考察结束", flush=True)
            stats = _analyze_quiz_results(quiz_history)
            mastery_update = _update_task_after_quiz(task_index, stats)
            done_data = json.dumps({
                "type": "done",
                "reply": full_content,
                "ended": True,
                "stats": stats,
                "mastery_update": mastery_update,
                "source_page": source_page,
                "task_index": task_index
            }, ensure_ascii=False)
            yield f"data: {done_data}\n\n"
        else:
            result = _extract_answer_result(full_content)
            next_question = _extract_question(full_content)
            has_next = "【下一题】" in full_content or "【追问】" in full_content
            print(f"[考察] 收到答案，已批改", flush=True)
            done_data = json.dumps({
                "type": "done",
                "result": result,
                "next_question": next_question if has_next else "",
                "has_next": has_next,
                "ended": False,
                "raw": full_content
            }, ensure_ascii=False)
            yield f"data: {done_data}\n\n"

    return Response(generate(), mimetype="text/event-stream")


@app.route("/api/stats", methods=["GET"])
def get_stats():
    """获取统计信息"""
    tasks = agent.memory.data.get("tasks", [])
    records = agent.memory.data.get("daily_record", {})
    total_tasks = len(tasks)
    completed = sum(1 for t in tasks if t["status"] == "已完成")
    total_reviews = sum(t.get("review_count", 0) for t in tasks)
    total_records = len(records)
    return jsonify({
        "total_tasks": total_tasks,
        "completed_tasks": completed,
        "total_reviews": total_reviews,
        "total_records": total_records,
    })


if __name__ == "__main__":
    app.run(debug=False, port=5000)
