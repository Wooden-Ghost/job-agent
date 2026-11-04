# 贡献指南

这个小工具是为「安卓端招聘 App 信息采集 → 本地筛选」写的，代码量不大，但结构是认真分的。改之前请先读这一页。

## 环境

- Windows 10/11
- Python 3.12（3.10+ 应该也能跑，但没测）
- 模拟器：雷电 / MuMu / 夜神 / 真机均可（走 `adb`）

```bash
python -m pip install -r requirements.txt
python launch.py          # 起界面
python -m job_agent check # 只做环境自检，不开界面
```

## 目录约定

| 目录 | 放什么 |
|---|---|
| `job_agent/` | 应用代码。`ui/` 只放界面，业务逻辑在 `flow/harvest/enrich/store` |
| `db/` | `schema.sql` 是唯一结构真相；结构变更必须新增 `db/migrations/000N_*.sql` |
| `etl/` | 外部数据导入（从别的表格搬数据进来） |
| `tests/` | `unittest`；`tests/fixtures/` 是合成数据，不含真实岗位 |
| `tools/` | 开发期脚本（界面原型、打包、截图），不进运行时依赖 |
| `docs/` | 设计文档；`docs/preview/` 是脱敏展示图 |

## 提交规范

Conventional Commits，正文中文：

```
feat: 采集流程支持按关键词过滤
fix: 导出 md 时 job 表缺 url 列导致崩溃
docs: 补充模拟器连接说明
test: 补 salary 解析的边界用例
chore: 升级 PySide6
```

一次提交只做一件事；不要混「改功能 + 重排版」。

## 数据库改动

1. 先改 `db/schema.sql`（新库直接建对）
2. 再写 `db/migrations/000N_xxx.sql`（已装用户能升级，必须幂等）
3. 补测试：`tests/test_migration_idempotent.py` 的思路是「跑两次结果一样」
4. 跑全量：`python -m unittest discover -s tests -v`

## 跑测试

```bash
python -m unittest discover -s tests -v
```

测试只依赖标准库 + `openpyxl`，不需要模拟器，也不会碰 `data/jobs.db`（都用临时库）。

## 不要提交的东西

`data/`、`exports/`、`logs/`、`config.json`、`docs/shots/`、任何 `.db` 与 `.xlsx`。
里面是真实公司名、薪资、JD 全文——这是别人的数据，也是你的隐私。
`.gitignore` 已经挡住了，但提交前还是看一眼 `git status`。

## 别做的事

- 不要为了跑通而把采集频率调高；封号风险是使用者自己承担的
- 不要在代码里写死本机绝对路径（配置项留空走默认值即可）
- 不要给 `ui/` 加业务逻辑
