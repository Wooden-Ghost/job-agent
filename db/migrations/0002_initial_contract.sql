-- 0002_initial_contract.sql
-- 幂等：全部 CREATE ... IF NOT EXISTS；可重复执行。
-- 单事务：BEGIN IMMEDIATE ... COMMIT；中途失败整批回滚。
-- 注意：本文件只建结构 + 盖版本号，**不搬数据**。
-- 数据搬迁在 etl/import_jobhunt.py（时间换算必须走 Python，不能写 SQL 时间函数）。
-- 与 db/schema.sql 的同构由 tests/test_schema_parity.py 守护。

PRAGMA foreign_keys = OFF;
BEGIN IMMEDIATE;

-- JobAgent 0002_initial_contract：v7 初始契约
-- 用途：新建空库直接可用。
--   sqlite3 new.db < db/schema.sql
-- 约定：
--   * 主键一律 TEXT（uuid4 hex），不用 INTEGER AUTOINCREMENT，便于将来换库。
--   * 时间一律 UTC ISO8601（2026-11-04T07:12:35Z）；biz_date 例外，是业务日 YYYY-MM-DD。
--   * 每张可写表带 version（乐观锁，从 1 起）、created_at、updated_at、deleted_at。
--   * 软删一律写 deleted_at，唯一索引全部带 WHERE deleted_at IS NULL。
--   * 本文件只建结构，不写数据；数据由 etl/import_jobhunt.py 灌入。

-- PRAGMA foreign_keys 在事务内是 no-op，故此处不设；由连接层设置。

CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);

-- ============================================================
-- 公司
-- ============================================================
CREATE TABLE IF NOT EXISTS company (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    norm_name TEXT NOT NULL,
    full_name TEXT,
    founded_year INTEGER,
    capital TEXT,
    insured_count INTEGER,
    city TEXT,
    industry TEXT,
    source TEXT,                                          -- 采集侧：zhaopin / boss / liepin
    conclusion TEXT,                                      -- 决策侧冗余快照（真值见 due_diligence_verdict）
    summary TEXT,
    -- 用户侧字段（v7）：只有 UI / Excel 通道能写，harvest_*() 与 decide_*() 一律不许碰
    is_starred INTEGER NOT NULL DEFAULT 0,                -- 值得关注
    tags TEXT,                                            -- JSON 数组，如 ["国企","成都","已投"]
    note TEXT,                                            -- 人工备注
    updated_by TEXT,                                      -- 最后改它的人：ui / excel / harvest / decide
    version INTEGER NOT NULL DEFAULT 1,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_company_norm
    ON company(norm_name) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS company_alias (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES company(id),
    alias TEXT NOT NULL,
    norm_alias TEXT NOT NULL,
    source TEXT,
    created_at TEXT NOT NULL,
    deleted_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_alias_norm
    ON company_alias(norm_alias) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_alias_company ON company_alias(company_id);

-- ============================================================
-- 岗位（主表）
-- ============================================================
CREATE TABLE IF NOT EXISTS job (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES company(id),
    legacy_key TEXT,                                      -- 指向 legacy jobs.job_key(16)，仅追溯
    job_key TEXT NOT NULL,                                -- sha1(norm_company|norm_title)[:12]，快查，非唯一键
    title TEXT NOT NULL,
    title_norm TEXT NOT NULL,
    salary_text TEXT,
    salary_min INTEGER,
    salary_max INTEGER,
    salary_months INTEGER,
    city TEXT,
    city_norm TEXT,                                       -- 成都/成都市→成都；空或远程→remote
    district TEXT,
    area TEXT,
    experience TEXT,
    education TEXT,
    jd_text TEXT,
    jd_len INTEGER,
    jd_hash TEXT,
    needs_manual_check INTEGER NOT NULL DEFAULT 0,
    company_meta TEXT,
    company_size TEXT,
    company_stage TEXT,
    hiring_count INTEGER,
    source_keyword TEXT,                                  -- 命中的搜索词；无真值就 NULL（不得由 tab 顶替）
    status TEXT DEFAULT 'open',                           -- open / closed / unknown
    -- 用户侧字段（v7）：写权归 UI / Excel 通道
    is_starred INTEGER NOT NULL DEFAULT 0,
    tags TEXT,
    note TEXT,
    updated_by TEXT,
    biz_date TEXT NOT NULL,
    seen_count INTEGER NOT NULL DEFAULT 1,
    version INTEGER NOT NULL DEFAULT 1,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_job_key3
    ON job(company_id, title_norm, city_norm) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_job_key  ON job(job_key);
CREATE INDEX IF NOT EXISTS ix_job_biz  ON job(biz_date);
CREATE INDEX IF NOT EXISTS ix_job_comp ON job(company_id);
CREATE INDEX IF NOT EXISTS ix_job_legacy ON job(legacy_key);

-- ============================================================
-- 岗位来源（同城同岗跨平台合并为一条 job，链接进子表）
-- ============================================================
CREATE TABLE IF NOT EXISTS job_source (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES job(id),
    source_app TEXT NOT NULL,                             -- 智联招聘 / BOSS直聘 / 猎聘
    external_id TEXT,                                     -- 平台岗 ID；NULL 不参与唯一冲突
    url TEXT,
    -- 平台侧原样值：同一岗位在不同平台薪资文案/上下限/抓取时间都可能不同
    salary_text TEXT,
    salary_month_lo INTEGER,
    salary_month_hi INTEGER,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    seen_count INTEGER NOT NULL DEFAULT 1,
    version INTEGER NOT NULL DEFAULT 1,
    deleted_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_source_ext
    ON job_source(source_app, external_id)
    WHERE external_id IS NOT NULL AND deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_source_job ON job_source(job_id);

-- job 上的 salary_text/first_seen/last_seen/seen_count/url/external_id 只是「选定最佳」的冗余：
-- 采集侧只写 job_source；每轮结束由应用层 fn_sync_job_best_source(job_id) 回填主表。

-- ============================================================
-- JD 版本（jd_hash 变化即落一条）
-- ============================================================
CREATE TABLE IF NOT EXISTS job_revision (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES job(id),
    jd_hash TEXT NOT NULL,
    jd_len INTEGER,
    captured_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_rev_job ON job_revision(job_id, captured_at);

-- ============================================================
-- 背调：证据与结论分表，避免互相覆盖
-- ============================================================
CREATE TABLE IF NOT EXISTS due_diligence_evidence (   -- 采集侧写
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES company(id),
    insured_count INTEGER,
    founded_year INTEGER,
    capital TEXT,
    captured_at TEXT NOT NULL,
    source TEXT,
    version INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS ix_evidence_company ON due_diligence_evidence(company_id, captured_at);

CREATE TABLE IF NOT EXISTS due_diligence_verdict (    -- 决策侧写
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES company(id),
    level TEXT,
    conclusion TEXT,
    evidence_json TEXT,
    checked_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_verdict_company ON due_diligence_verdict(company_id, checked_at);

-- ============================================================
-- 筛选记录（v6 收敛为一张表，直接挂 job；不预设投递/面试流程）
-- ============================================================
CREATE TABLE IF NOT EXISTS screening (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES job(id),
    company_id TEXT REFERENCES company(id),               -- 冗余，便于按公司聚合
    round_no INTEGER NOT NULL DEFAULT 1,                  -- 1=一重(快速淘汰) 2=二重(完整六维)
    dims TEXT,                                            -- JSON 六维 0-100
    total INTEGER,                                        -- 代码按权重加权，不由模型直出
    weights_version TEXT NOT NULL,
    conclusion TEXT,                                      -- 可投 / 谨慎投递 / 不合适 / 未达标
    fail_reason TEXT,                                     -- 失败原因（模型输出）
    suggestion TEXT,                                      -- 建议提升（模型输出）
    note TEXT,                                            -- 人工补注：与上面两列分开存，不许覆盖模型输出
    evaluator TEXT,
    created_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_screening_job ON screening(job_id, created_at);
CREATE INDEX IF NOT EXISTS ix_screening_company ON screening(company_id, created_at);

-- ============================================================
-- 检索层（standalone FTS5；不用 external content，避免 VACUUM 重排 rowid 指错行）
-- 中文必须 trigram：unicode61 会把整段 JD 当成 1 个 token。
-- 注意：trigram 只索引三元组，2 字查询（国企/专利/算法）召回为 0，需回退 LIKE。
-- ============================================================
CREATE VIRTUAL TABLE IF NOT EXISTS job_fts USING fts5(
    job_id UNINDEXED,
    title,
    jd_text,
    tokenize='trigram'
);

-- ============================================================
-- 视图
-- ============================================================
-- 软删的岗不得被搜出
CREATE VIEW IF NOT EXISTS v_job_search AS
SELECT j.* FROM job j WHERE j.deleted_at IS NULL;

-- 待筛视图：只回答「筛过没、结论如何、值不值得投」，不涉及投递流程
CREATE VIEW IF NOT EXISTS v_todo_all AS
SELECT j.id AS job_id, c.name AS company, j.title, j.salary_text, j.city, j.city_norm,
       s.total, s.conclusion, s.evaluator, s.created_at AS screened_at,
       CASE WHEN s.id IS NULL THEN 0 ELSE 1 END AS screened
FROM job j
JOIN company c ON c.id = j.company_id
LEFT JOIN screening s ON s.job_id = j.id AND s.deleted_at IS NULL
WHERE j.deleted_at IS NULL;
-- 用法：store.todo_jobs(city="成都", only_unscreened=True, min_total=60)


-- 盖版本号（幂等：先清后写，避免重复执行堆多行）
DELETE FROM schema_version;
INSERT INTO schema_version(version) VALUES (2);

COMMIT;
PRAGMA foreign_keys = ON;
