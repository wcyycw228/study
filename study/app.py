import argparse
import json
import random
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Iterable, Sequence

from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table


DEFAULT_DB_PATH = Path.home() / ".study" / "study.db"
RESULTS = {"AC", "WA", "SKIP"}


@dataclass(frozen=True)
class Question:
    qid: int
    title: str
    content: str
    tags: list[str]
    difficulty: str


class StudyStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS questions (
                    id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    difficulty TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY,
                    question_id INTEGER NOT NULL,
                    result TEXT NOT NULL,
                    duration_sec REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(question_id) REFERENCES questions(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS wrong_questions (
                    question_id INTEGER PRIMARY KEY,
                    FOREIGN KEY(question_id) REFERENCES questions(id)
                )
                """
            )

    def import_questions(self, path: Path) -> int:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        with self.connect() as conn:
            row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM questions").fetchone()
            next_id = int(row[0]) if row else 0
        questions = []
        for item in payload:
            tags = item.get("tags") or []
            qid = item.get("id")
            if qid is None:
                next_id += 1
                qid = next_id
            questions.append(
                (
                    qid,
                    item["title"],
                    item["content"],
                    ",".join(tags),
                    item.get("difficulty", "unknown"),
                )
            )
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO questions (id, title, content, tags, difficulty)
                VALUES (?, ?, ?, ?, ?)
                """,
                questions,
            )
        return len(questions)

    def fetch_questions(
        self,
        tags: Sequence[str] | None = None,
        difficulty: str | None = None,
        only_wrong: bool = False,
    ) -> list[Question]:
        clauses = []
        params: list[str] = []
        if difficulty:
            clauses.append("difficulty = ?")
            params.append(difficulty)
        if tags:
            for tag in tags:
                clauses.append("tags LIKE ?")
                params.append(f"%{tag}%")
        if only_wrong:
            clauses.append("id IN (SELECT question_id FROM wrong_questions)")
        where = " AND ".join(clauses)
        sql = "SELECT id, title, content, tags, difficulty FROM questions"
        if where:
            sql += " WHERE " + where
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            Question(
                qid=row["id"],
                title=row["title"],
                content=row["content"],
                tags=[tag for tag in row["tags"].split(",") if tag],
                difficulty=row["difficulty"],
            )
            for row in rows
        ]

    def record_result(self, question_id: int, result: str, duration: float) -> None:
        timestamp = datetime.now().isoformat(timespec="seconds")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO history (question_id, result, duration_sec, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (question_id, result, duration, timestamp),
            )
            if result == "AC":
                conn.execute(
                    "DELETE FROM wrong_questions WHERE question_id = ?",
                    (question_id,),
                )
            else:
                conn.execute(
                    "INSERT OR IGNORE INTO wrong_questions (question_id) VALUES (?)",
                    (question_id,),
                )

    def get_today_stats(self) -> dict[str, float]:
        today = date.today().isoformat()
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT result, duration_sec FROM history
                WHERE created_at LIKE ?
                """,
                (f"{today}%",),
            ).fetchall()
        total = len(rows)
        ac_count = sum(1 for row in rows if row["result"] == "AC")
        avg_time = sum(row["duration_sec"] for row in rows) / total if total else 0.0
        accuracy = (ac_count / total * 100) if total else 0.0
        return {"total": total, "accuracy": accuracy, "avg_time": avg_time}


class StudyCLI:
    def __init__(self, store: StudyStore, console: Console) -> None:
        self.store = store
        self.console = console

    def run_quiz(
        self,
        tags: Sequence[str] | None,
        difficulty: str | None,
        mode: str,
        limit: int | None,
        only_wrong: bool,
    ) -> None:
        questions = self.store.fetch_questions(tags, difficulty, only_wrong)
        if not questions:
            self.console.print("[yellow]未找到符合条件的题目。[/yellow]")
            return
        if mode == "random":
            random.shuffle(questions)
        elif mode == "sorted":
            questions.sort(key=lambda q: q.qid)
        total_limit = limit or len(questions)
        for index, question in enumerate(questions[:total_limit], start=1):
            self.console.rule(f"第 {index} 题 / {total_limit}")
            self.console.print(f"[bold]{question.title}[/bold]")
            self.console.print(question.content)
            self.console.print(
                f"[dim]难度：{question.difficulty} | 标签：{', '.join(question.tags) or '无'}[/dim]"
            )
            start_time = time.perf_counter()
            result = Prompt.ask("提交结果 (AC/WA/SKIP/QUIT)", default="AC").upper()
            if result == "QUIT":
                self.console.print("[yellow]已退出刷题。[/yellow]")
                break
            if result not in RESULTS:
                self.console.print("[red]输入无效，已记为 SKIP。[/red]")
                result = "SKIP"
            duration = time.perf_counter() - start_time
            self.store.record_result(question.qid, result, duration)
            self.console.print(
                f"[green]已记录：{result}，耗时 {duration:.1f} 秒[/green]"
            )

    def show_stats(self) -> None:
        stats = self.store.get_today_stats()
        table = Table(title="今日统计")
        table.add_column("刷题数", justify="right")
        table.add_column("正确率", justify="right")
        table.add_column("平均耗时(秒)", justify="right")
        table.add_row(
            str(stats["total"]),
            f"{stats['accuracy']:.1f}%",
            f"{stats['avg_time']:.1f}",
        )
        self.console.print(table)


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="study", description="刷题 CLI MVP")
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="SQLite 数据库路径",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="初始化数据库")

    import_parser = subparsers.add_parser("import", help="导入题库 JSON")
    import_parser.add_argument("path", type=Path, help="题库 JSON 文件路径")

    start_parser = subparsers.add_parser("start", help="开始刷题")
    start_parser.add_argument("--tags", help="按标签过滤（逗号分隔）")
    start_parser.add_argument("--difficulty", help="按难度过滤")
    start_parser.add_argument(
        "--mode",
        choices=["random", "sorted"],
        default="random",
        help="出题模式",
    )
    start_parser.add_argument("--limit", type=int, help="题目数量")
    start_parser.add_argument(
        "--wrong",
        action="store_true",
        help="仅练习错题本",
    )

    subparsers.add_parser("wrongbook", help="错题本练习")
    subparsers.add_parser("stats", help="查看今日统计")

    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> None:
    args = parse_args(argv)
    console = Console()
    store = StudyStore(args.db)
    cli = StudyCLI(store, console)

    if args.command == "init":
        store.init_db()
        console.print(f"[green]数据库初始化完成：{args.db}[/green]")
        return
    if args.command == "import":
        store.init_db()
        count = store.import_questions(args.path)
        console.print(f"[green]成功导入 {count} 道题目[/green]")
        return
    if args.command == "start":
        store.init_db()
        tags = args.tags.split(",") if args.tags else None
        cli.run_quiz(tags, args.difficulty, args.mode, args.limit, args.wrong)
        return
    if args.command == "wrongbook":
        store.init_db()
        cli.run_quiz(None, None, "random", None, True)
        return
    if args.command == "stats":
        store.init_db()
        cli.show_stats()
        return


if __name__ == "__main__":
    main()
