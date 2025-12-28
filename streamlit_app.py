import json
import random
import time
from pathlib import Path
from typing import Iterable
import tempfile

import streamlit as st

from study.app import DEFAULT_DB_PATH, Question, StudyStore


def load_store(db_path: Path) -> StudyStore:
    store = StudyStore(db_path)
    store.init_db()
    return store


def load_questions(store: StudyStore) -> list[Question]:
    return store.fetch_questions()


def collect_tags(questions: Iterable[Question]) -> list[str]:
    tags: set[str] = set()
    for question in questions:
        tags.update(question.tags)
    return sorted(tags)


def collect_difficulties(questions: Iterable[Question]) -> list[str]:
    return sorted({question.difficulty for question in questions})


def init_session_state() -> None:
    st.session_state.setdefault("quiz_questions", [])
    st.session_state.setdefault("quiz_index", 0)
    st.session_state.setdefault("quiz_started_at", None)
    st.session_state.setdefault("quiz_message", "")


def start_quiz(
    store: StudyStore,
    tags: list[str],
    difficulty: str | None,
    mode: str,
    limit: int | None,
    only_wrong: bool,
) -> None:
    questions = store.fetch_questions(tags=tags or None, difficulty=difficulty, only_wrong=only_wrong)
    if mode == "random":
        random.shuffle(questions)
    else:
        questions.sort(key=lambda item: item.qid)
    total = limit or len(questions)
    st.session_state.quiz_questions = questions[:total]
    st.session_state.quiz_index = 0
    st.session_state.quiz_started_at = time.perf_counter()
    st.session_state.quiz_message = ""


def record_answer(store: StudyStore, result: str) -> None:
    questions: list[Question] = st.session_state.quiz_questions
    index: int = st.session_state.quiz_index
    if index >= len(questions):
        return
    question = questions[index]
    start_time = st.session_state.quiz_started_at
    if start_time is None:
        start_time = time.perf_counter()
    duration = time.perf_counter() - start_time
    store.record_result(question.qid, result, duration)
    st.session_state.quiz_message = f"已记录：{result}，耗时 {duration:.1f} 秒"
    st.session_state.quiz_index = index + 1
    st.session_state.quiz_started_at = time.perf_counter()


st.set_page_config(page_title="Study 刷题", layout="wide")

init_session_state()

st.title("Study 刷题 Web App")

with st.sidebar:
    st.header("数据库")
    db_input = st.text_input("数据库路径", value=str(DEFAULT_DB_PATH))
    db_path = Path(db_input).expanduser()
    store = load_store(db_path)

    if st.button("初始化数据库"):
        store.init_db()
        st.success(f"数据库初始化完成：{db_path}")

    st.divider()
    st.subheader("导入题库")
    upload = st.file_uploader("选择题库 JSON", type=["json"])
    if upload is not None:
        payload = json.loads(upload.getvalue().decode("utf-8"))
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            temp_path = Path(handle.name)
        count = store.import_questions(temp_path)
        st.success(f"成功导入 {count} 道题目")

questions = load_questions(store)
all_tags = collect_tags(questions)
all_difficulties = collect_difficulties(questions)

quiz_tab, wrong_tab, stats_tab = st.tabs(["刷题", "错题本", "今日统计"])

with quiz_tab:
    st.subheader("开始刷题")
    tags = st.multiselect("标签", options=all_tags)
    difficulty = st.selectbox("难度", options=["全部"] + all_difficulties)
    mode = st.radio("出题模式", options=["random", "sorted"], horizontal=True)
    limit = st.number_input("题目数量", min_value=1, value=5)

    if st.button("开始刷题", key="start_quiz"):
        start_quiz(
            store,
            tags=tags,
            difficulty=None if difficulty == "全部" else difficulty,
            mode=mode,
            limit=int(limit) if limit else None,
            only_wrong=False,
        )

    questions = st.session_state.quiz_questions
    index = st.session_state.quiz_index
    if questions:
        if index < len(questions):
            question = questions[index]
            st.markdown(f"### 第 {index + 1} / {len(questions)} 题")
            st.markdown(f"**{question.title}**")
            st.write(question.content)
            st.caption(f"难度：{question.difficulty} | 标签：{', '.join(question.tags) or '无'}")

            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("AC", key=f"ac_{question.qid}"):
                    record_answer(store, "AC")
                    st.rerun()
            with col2:
                if st.button("WA", key=f"wa_{question.qid}"):
                    record_answer(store, "WA")
                    st.rerun()
            with col3:
                if st.button("SKIP", key=f"skip_{question.qid}"):
                    record_answer(store, "SKIP")
                    st.rerun()

            if st.session_state.quiz_message:
                st.success(st.session_state.quiz_message)
        else:
            st.success("刷题完成！")
    else:
        st.info("还没有开始刷题，或题库为空。")

with wrong_tab:
    st.subheader("错题本练习")
    if st.button("开始错题本", key="start_wrong"):
        start_quiz(store, tags=[], difficulty=None, mode="random", limit=None, only_wrong=True)

    wrong_questions = st.session_state.quiz_questions
    wrong_index = st.session_state.quiz_index
    if wrong_questions:
        if wrong_index < len(wrong_questions):
            question = wrong_questions[wrong_index]
            st.markdown(f"### 第 {wrong_index + 1} / {len(wrong_questions)} 题")
            st.markdown(f"**{question.title}**")
            st.write(question.content)
            st.caption(f"难度：{question.difficulty} | 标签：{', '.join(question.tags) or '无'}")

            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("AC", key=f"wrong_ac_{question.qid}"):
                    record_answer(store, "AC")
                    st.rerun()
            with col2:
                if st.button("WA", key=f"wrong_wa_{question.qid}"):
                    record_answer(store, "WA")
                    st.rerun()
            with col3:
                if st.button("SKIP", key=f"wrong_skip_{question.qid}"):
                    record_answer(store, "SKIP")
                    st.rerun()
        else:
            st.success("错题本刷题完成！")
    else:
        st.info("错题本为空，或者尚未开始。")

with stats_tab:
    st.subheader("今日统计")
    stats = store.get_today_stats()
    col1, col2, col3 = st.columns(3)
    col1.metric("刷题数", str(stats["total"]))
    col2.metric("正确率", f"{stats['accuracy']:.1f}%")
    col3.metric("平均耗时(秒)", f"{stats['avg_time']:.1f}")
