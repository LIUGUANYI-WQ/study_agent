import json
import datetime
import sqlite3
import os


class MemoryStore:
    """管理任务和学习日志的持久化存储 - SQLite 版本"""

    MASTERY_LEVELS = ["生疏", "一般", "熟悉", "精通"]
    STATUS_OPTIONS = ["未完成", "进行中", "已完成"]
    CATEGORIES = ["编程", "算法", "数学", "英语", "其他"]
    KNOWLEDGE_TYPES = ["概念", "原理", "方法", "工具", "案例", "其他"]

    def __init__(self, db_path="study_memory.db"):
        self.db_path = db_path
        self._init_db()
        # 兼容属性：data 字典供外部直接读取（如 web_app.py 的 quiz_start）
        self.data = self._load_to_dict()

    # ============================================================
    #  数据库初始化
    # ============================================================
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self):
        conn = self._get_conn()
        c = conn.cursor()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                task          TEXT NOT NULL,
                deadline      TEXT NOT NULL,
                status        TEXT DEFAULT '未完成',
                review_count  INTEGER DEFAULT 0,
                create_time   TEXT,
                category      TEXT DEFAULT '其他',
                mastery       TEXT DEFAULT '生疏',
                last_review   TEXT,
                estimated_hours REAL DEFAULT 1.0,
                priority      INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS daily_records (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                date          TEXT UNIQUE NOT NULL,
                raw_content   TEXT,
                mastery_level TEXT DEFAULT '生疏',
                tags          TEXT DEFAULT '[]',
                summary       TEXT DEFAULT '',
                quality_score INTEGER DEFAULT 0,
                create_time   TEXT
            );

            CREATE TABLE IF NOT EXISTS knowledge_points (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id     INTEGER NOT NULL,
                name          TEXT,
                type          TEXT,
                description   TEXT,
                FOREIGN KEY (record_id) REFERENCES daily_records(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS task_knowledge_points (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id         INTEGER NOT NULL,
                knowledge_id    INTEGER NOT NULL,
                create_time     TEXT,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                FOREIGN KEY (knowledge_id) REFERENCES knowledge_points(id) ON DELETE CASCADE,
                UNIQUE(task_id, knowledge_id)
            );

            CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority DESC);
            CREATE INDEX IF NOT EXISTS idx_records_date   ON daily_records(date);
            CREATE INDEX IF NOT EXISTS idx_kp_record_id   ON knowledge_points(record_id);
            CREATE INDEX IF NOT EXISTS idx_tkp_task_id    ON task_knowledge_points(task_id);
            CREATE INDEX IF NOT EXISTS idx_tkp_kp_id      ON task_knowledge_points(knowledge_id);
        """)
        conn.commit()
        conn.close()

    # ============================================================
    #  同步：DB → data 字典（兼容旧代码）
    # ============================================================
    def _load_to_dict(self):
        conn = self._get_conn()
        c = conn.cursor()

        # tasks
        c.execute("SELECT * FROM tasks ORDER BY priority DESC")
        tasks = []
        for row in c.fetchall():
            tasks.append({
                "task": row["task"],
                "deadline": row["deadline"],
                "status": row["status"],
                "review_count": row["review_count"],
                "create_time": row["create_time"],
                "category": row["category"],
                "mastery": row["mastery"],
                "last_review": row["last_review"],
                "estimated_hours": row["estimated_hours"],
                "priority": row["priority"],
            })

        # daily_records + knowledge_points
        daily_record = {}
        c.execute("SELECT * FROM daily_records ORDER BY date DESC")
        for row in c.fetchall():
            date_str = row["date"]
            c2 = conn.cursor()
            c2.execute("SELECT name, type, description FROM knowledge_points WHERE record_id=?", (row["id"],))
            kps = [{"name": r["name"], "type": r["type"], "description": r["description"]} for r in c2.fetchall()]

            tags = json.loads(row["tags"]) if row["tags"] else []
            record = {
                "raw_content": row["raw_content"] or "",
                "knowledge_points": kps,
                "mastery_level": row["mastery_level"] or "生疏",
                "tags": tags,
                "summary": row["summary"] or "",
                "quality_score": row["quality_score"] or 0,
                "create_time": row["create_time"] or "",
            }
            daily_record[date_str] = record

        conn.close()
        return {"tasks": tasks, "daily_record": daily_record}

    def _sync_from_db(self):
        """重新从数据库加载 data 字典"""
        self.data = self._load_to_dict()

    # ============================================================
    #  优先级算法（与之前完全一致）
    # ============================================================
    def _recalc_priorities(self):
        today = datetime.datetime.now()
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT id, deadline, mastery, last_review, status FROM tasks")
        rows = c.fetchall()
        for row in rows:
            if row["status"] == "已完成":
                priority = 0
            else:
                try:
                    deadline_date = datetime.datetime.strptime(row["deadline"], "%Y-%m-%d")
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
                mastery_score = mastery_scores.get(row["mastery"], 15)

                if row["last_review"] is None:
                    interval_score = 30
                else:
                    try:
                        last = datetime.datetime.strptime(row["last_review"], "%Y-%m-%d")
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

                priority = urgency_score + mastery_score + interval_score

            c.execute("UPDATE tasks SET priority=? WHERE id=?", (priority, row["id"]))
        conn.commit()
        conn.close()

    # ============================================================
    #  任务操作
    # ============================================================
    def add_task(self, task_name, deadline, category="其他",
                 mastery="生疏", estimated_hours=1.0):
        now = self.get_now_date()
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            """INSERT INTO tasks (task, deadline, status, review_count, create_time,
               category, mastery, last_review, estimated_hours, priority)
               VALUES (?, ?, '未完成', 0, ?, ?, ?, NULL, ?, 0)""",
            (task_name, deadline, now, category, mastery, estimated_hours)
        )
        task_id = c.lastrowid
        conn.commit()
        conn.close()
        self._recalc_priorities()
        self._sync_from_db()
        message = f"任务添加成功：{task_name}，截止日期：{deadline}，分类：{category}，掌握程度：{mastery}"
        return {"message": message, "task_id": task_id, "task": task_name, "deadline": deadline}

    def update_task(self, task_index, **kwargs):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT id FROM tasks ORDER BY priority DESC")
        rows = c.fetchall()
        if task_index < 0 or task_index >= len(rows):
            conn.close()
            return f"错误：任务索引 {task_index} 不存在"
        task_id = rows[task_index]["id"]
        sets = []
        vals = []
        for key, value in kwargs.items():
            sets.append(f"{key}=?")
            vals.append(value)
        vals.append(task_id)
        c.execute(f"UPDATE tasks SET {','.join(sets)} WHERE id=?", vals)
        conn.commit()
        conn.close()
        if any(k in ("deadline", "mastery", "review_count", "last_review") for k in kwargs):
            self._recalc_priorities()
        self._sync_from_db()
        task = self.data["tasks"][task_index] if task_index < len(self.data["tasks"]) else {}
        return f"任务更新成功：{task.get('task', '')}"

    def mark_reviewed(self, task_index):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT id, review_count, mastery FROM tasks ORDER BY priority DESC")
        rows = c.fetchall()
        if task_index < 0 or task_index >= len(rows):
            conn.close()
            return f"错误：任务索引 {task_index} 不存在"
        row = rows[task_index]
        new_count = row["review_count"] + 1
        mastery_idx = self.MASTERY_LEVELS.index(row["mastery"]) if row["mastery"] in self.MASTERY_LEVELS else 0
        new_mastery = self.MASTERY_LEVELS[min(mastery_idx + 1, len(self.MASTERY_LEVELS) - 1)]
        now = self.get_now_date()
        c.execute("UPDATE tasks SET review_count=?, mastery=?, last_review=? WHERE id=?",
                  (new_count, new_mastery, now, row["id"]))
        conn.commit()
        conn.close()
        self._recalc_priorities()
        self._sync_from_db()
        task = self.data["tasks"][task_index]
        return f"已标记复习：{task['task']}，累计复习{new_count}次，掌握程度：{new_mastery}"

    def delete_task(self, task_index):
        """按优先级排序后的索引删除任务"""
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT id, task FROM tasks ORDER BY priority DESC")
        rows = c.fetchall()
        if task_index < 0 or task_index >= len(rows):
            conn.close()
            return f"错误：任务索引 {task_index} 不存在"
        task_id = rows[task_index]["id"]
        task_name = rows[task_index]["task"]
        c.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        conn.commit()
        conn.close()
        self._sync_from_db()
        return f"已删除任务：{task_name}"

    def get_tasks(self):
        return json.dumps(self.data["tasks"], ensure_ascii=False)

    def get_task_ranking(self):
        sorted_tasks = sorted(
            self.data["tasks"],
            key=lambda t: t.get("priority", 0),
            reverse=True
        )
        return json.dumps(sorted_tasks, ensure_ascii=False)

    # ============================================================
    #  日志操作
    # ============================================================
    def record_daily(self, content):
        today = self.get_now_date()
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO daily_records (date, raw_content, create_time) VALUES (?, ?, ?)",
                  (today, content, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()
        self._sync_from_db()
        return f"已记录今日学习内容：{content}"

    def get_daily_record(self, date_str=None):
        if date_str is None:
            date_str = self.get_now_date()
        record = self.data["daily_record"].get(date_str)
        if record is None:
            return f"{date_str} 无学习记录"
        return record

    # ============================================================
    #  结构化学习记录
    # ============================================================
    def record_daily_structured(self, content, knowledge_points=None, mastery_level="生疏",
                                tags=None, summary=None):
        today = self.get_now_date()
        quality_score = self._calculate_quality_score(content, knowledge_points)
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tags_json = json.dumps(tags if tags else [], ensure_ascii=False)

        conn = self._get_conn()
        c = conn.cursor()
        # 先删除同一天的旧记录及关联知识点
        c.execute("SELECT id FROM daily_records WHERE date=?", (today,))
        old = c.fetchone()
        if old:
            c.execute("DELETE FROM knowledge_points WHERE record_id=?", (old["id"],))
            c.execute("DELETE FROM daily_records WHERE id=?", (old["id"],))

        c.execute(
            """INSERT INTO daily_records (date, raw_content, mastery_level, tags, summary, quality_score, create_time)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (today, content, mastery_level, tags_json, summary or content, quality_score, now_str)
        )
        record_id = c.lastrowid

        saved_kps = []
        if knowledge_points:
            for kp in knowledge_points:
                c.execute(
                    "INSERT INTO knowledge_points (record_id, name, type, description) VALUES (?, ?, ?, ?)",
                    (record_id, kp.get("name", ""), kp.get("type", ""), kp.get("description", ""))
                )
                saved_kps.append({
                    "id": c.lastrowid,
                    "name": kp.get("name", ""),
                    "type": kp.get("type", ""),
                    "description": kp.get("description", "")
                })

        conn.commit()
        conn.close()
        self._sync_from_db()
        return {
            "message": f"已记录结构化学习内容，包含 {len(knowledge_points) if knowledge_points else 0} 个知识点",
            "record_id": record_id,
            "knowledge_points": saved_kps,
            "quality_score": quality_score
        }

    def _calculate_quality_score(self, content, knowledge_points):
        score = 0
        content_length = len(content.strip()) if content else 0
        if content_length >= 50:
            score += 30
        elif content_length >= 20:
            score += 15
        if knowledge_points and len(knowledge_points) >= 3:
            score += 40
        elif knowledge_points and len(knowledge_points) >= 1:
            score += 20
        if knowledge_points:
            detailed_points = sum(1 for kp in knowledge_points if kp.get("description") and len(kp["description"]) > 10)
            score += min(detailed_points * 10, 30)
        return min(score, 100)

    def get_structured_record(self, date_str=None):
        if date_str is None:
            date_str = self.get_now_date()
        record = self.data["daily_record"].get(date_str)
        if isinstance(record, dict) and "raw_content" in record:
            return record
        return None

    def get_all_knowledge_points(self):
        all_points = []
        for date, record in self.data.get("daily_record", {}).items():
            if isinstance(record, dict) and "knowledge_points" in record:
                for kp in record["knowledge_points"]:
                    kp["source_date"] = date
                    all_points.append(kp)
        return all_points

    # ============================================================
    #  任务-知识点 关联
    # ============================================================
    def link_task_knowledge(self, task_id, knowledge_id):
        """关联任务和知识点"""
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = self._get_conn()
        c = conn.cursor()
        try:
            c.execute(
                "INSERT OR IGNORE INTO task_knowledge_points (task_id, knowledge_id, create_time) VALUES (?, ?, ?)",
                (task_id, knowledge_id, now_str)
            )
            conn.commit()
        finally:
            conn.close()

    def get_task_knowledge_points(self, task_index):
        """获取任务关联的知识点"""
        conn = self._get_conn()
        c = conn.cursor()
        # 先获取任务id
        c.execute("SELECT id FROM tasks ORDER BY priority DESC")
        tasks = c.fetchall()
        if task_index < 0 or task_index >= len(tasks):
            conn.close()
            return []
        task_id = tasks[task_index]["id"]

        # 查询关联的知识点
        c.execute("""
            SELECT kp.id, kp.name, kp.type, kp.description
            FROM knowledge_points kp
            INNER JOIN task_knowledge_points tkp ON kp.id = tkp.knowledge_id
            WHERE tkp.task_id = ?
            ORDER BY tkp.id
        """, (task_id,))
        kps = [dict(row) for row in c.fetchall()]
        conn.close()
        return kps

    def get_task_by_index(self, task_index):
        """根据索引获取任务（含id）"""
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM tasks ORDER BY priority DESC")
        tasks = c.fetchall()
        conn.close()
        if task_index < 0 or task_index >= len(tasks):
            return None
        return dict(tasks[task_index])

    # ============================================================
    #  数据迁移：JSON → SQLite
    # ============================================================
    def migrate_from_json(self, json_path="study_memory.json"):
        """将旧 JSON 数据文件导入 SQLite（仅执行一次）"""
        if not os.path.exists(json_path):
            return False
        with open(json_path, "r", encoding="utf-8") as f:
            old_data = json.load(f)

        conn = self._get_conn()
        c = conn.cursor()

        # 迁移 tasks
        for t in old_data.get("tasks", []):
            c.execute(
                """INSERT OR IGNORE INTO tasks
                   (task, deadline, status, review_count, create_time, category, mastery, last_review, estimated_hours, priority)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (t.get("task"), t.get("deadline"), t.get("status", "未完成"),
                 t.get("review_count", 0), t.get("create_time", ""), t.get("category", "其他"),
                 t.get("mastery", "生疏"), t.get("last_review"), t.get("estimated_hours", 1.0),
                 t.get("priority", 0))
            )

        # 迁移 daily_records
        for date_str, record in old_data.get("daily_record", {}).items():
            if isinstance(record, str):
                # 旧格式：纯文本
                c.execute(
                    """INSERT OR IGNORE INTO daily_records (date, raw_content, create_time)
                       VALUES (?, ?, ?)""",
                    (date_str, record, "")
                )
            elif isinstance(record, dict):
                tags_json = json.dumps(record.get("tags", []), ensure_ascii=False)
                c.execute(
                    """INSERT OR IGNORE INTO daily_records
                       (date, raw_content, mastery_level, tags, summary, quality_score, create_time)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (date_str, record.get("raw_content", ""),
                     record.get("mastery_level", "生疏"), tags_json,
                     record.get("summary", ""), record.get("quality_score", 0),
                     record.get("create_time", ""))
                )
                record_id = c.lastrowid
                for kp in record.get("knowledge_points", []):
                    c.execute(
                        "INSERT INTO knowledge_points (record_id, name, type, description) VALUES (?, ?, ?, ?)",
                        (record_id, kp.get("name", ""), kp.get("type", ""), kp.get("description", ""))
                    )

        conn.commit()
        conn.close()
        self._recalc_priorities()
        self._sync_from_db()
        return True

    # ============================================================
    #  工具方法
    # ============================================================
    @staticmethod
    def get_now_date():
        return datetime.datetime.now().strftime("%Y-%m-%d")

    @staticmethod
    def get_yesterday_date():
        yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
        return yesterday.strftime("%Y-%m-%d")
