# study

刷题 CLI MVP，基于 Python + SQLite + Rich。

## 安装

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 初始化数据库

```bash
python -m study init
```

默认数据库路径为 `~/.study/study.db`，可用 `--db` 指定。

## 导入题库

```bash
python -m study import sample_questions.json
```

题库 JSON 格式示例见 `sample_questions.json`。

## 开始刷题

随机出题：

```bash
python -m study start
```

按标签/难度：

```bash
python -m study start --tags 字符串,滑动窗口 --difficulty medium
```

顺序出题并限制数量：

```bash
python -m study start --mode sorted --limit 5
```

仅练习错题本：

```bash
python -m study start --wrong
# 或
python -m study wrongbook
```

## 今日统计

```bash
python -m study stats
```
