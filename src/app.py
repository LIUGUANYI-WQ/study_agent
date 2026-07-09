import json
import datetime
import schedule
import time
import threading
from .agent import StudyAgent
from .memory import MemoryStore


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
            structured_record = self.agent.optimize_learning_record(content)
            
            print("\n📝 即将保存的学习记录：")
            print(f"   原始内容：{structured_record['raw_content'][:50]}..." if len(structured_record['raw_content']) > 50 else f"   原始内容：{structured_record['raw_content']}")
            print(f"   核心要点：{structured_record['summary']}")
            print(f"   知识点数：{len(structured_record['knowledge_points'])}")
            print(f"   掌握程度：{structured_record['mastery_level']}")
            print(f"   质量评分：{structured_record['quality_score']}分")
            
            while True:
                try:
                    confirm = input("\n确认保存此记录？(y/n) ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    confirm = 'n'
                
                if confirm == 'y':
                    result = self.agent.memory.record_daily_structured(
                        content=structured_record['raw_content'],
                        knowledge_points=structured_record['knowledge_points'],
                        mastery_level=structured_record['mastery_level'],
                        tags=structured_record['tags'],
                        summary=structured_record['summary']
                    )
                    print(f"\n✅ {result}")
                    break
                elif confirm == 'n':
                    print("\n已取消保存\n")
                    break
                else:
                    print("请输入 y 或 n")
                    
        except Exception as e:
            print(f"记录失败：{e}\n")
            print("将以原始方式保存...")
            try:
                print(self.agent.memory.record_daily(content))
            except Exception as e2:
                print(f"保存失败：{e2}\n")

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

    def _is_menu_command(self, text):
        return text.isdigit() and 1 <= int(text) <= 8

    def _handle_natural_language(self, text):
        try:
            print("助手：", end="")
            self.agent.chat(text, stream=True, use_tools=True)
        except Exception as e:
            print(f"\n处理失败：{e}\n请稍后重试\n")

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
