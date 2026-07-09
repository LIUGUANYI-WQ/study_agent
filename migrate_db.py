"""一次性迁移脚本：将 JSON 数据导入 SQLite"""
import os
import sys
from src.memory import MemoryStore

def main():
    db_path = "study_memory.db"
    # 如果数据库已存在且有数据，不重复迁移
    if os.path.exists(db_path):
        import sqlite3
        conn = sqlite3.connect(db_path)
        cnt = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        conn.close()
        if cnt > 0:
            print("数据库已有数据，跳过迁移")
            return

    print("开始迁移 JSON -> SQLite...")
    store = MemoryStore(db_path)
    result = store.migrate_from_json("study_memory.json")
    if result:
        print("迁移成功！")
        print(f"任务数: {len(store.data['tasks'])}")
        print(f"学习记录数: {len(store.data['daily_record'])}")
        # 打印 tasks 验证
        for i, t in enumerate(store.data['tasks']):
            print(f"  任务{i}: {t['task'][:30]}... priority={t['priority']}")
        # 打印 records 验证
        for date, rec in store.data['daily_record'].items():
            if isinstance(rec, dict):
                print(f"  {date}: {rec.get('summary', rec.get('raw_content', ''))[:40]}... kp={len(rec.get('knowledge_points', []))}")
            else:
                print(f"  {date}: {str(rec)[:40]}...")
    else:
        print("未找到 study_memory.json，跳过迁移")
    print("完成。")

if __name__ == "__main__":
    main()
