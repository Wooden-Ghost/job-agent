-- ============================================================
-- 0003 · 人工干预区 + 状态值改名
-- ------------------------------------------------------------
-- 幂等说明：SQLite 的 ALTER TABLE ADD COLUMN 没有 IF NOT EXISTS，
-- 所以本文件由 etl/migrate_0003.py 逐条执行，执行前先查 pragma table_info
-- 判断列是否已存在；UPDATE 本身幂等。直接重复跑本文件也安全（会报 duplicate
-- column，由 runner 忽略）。
-- ============================================================

-- 1) 三个可编辑文本框（人工干预区）
ALTER TABLE job ADD COLUMN analysis TEXT;      -- 岗位分析：核心业务 / 考察点
ALTER TABLE job ADD COLUMN fail_reason TEXT;   -- 失败原因：为何没投 / 面试为何挂
ALTER TABLE job ADD COLUMN advice TEXT;        -- 投递建议：面试前补什么、话术怎么答

-- 2) 状态值改名（旧库只有 open / jd_too_short 两种）
UPDATE job SET status = 'pending'  WHERE status = 'open';
UPDATE job SET status = 'excluded' WHERE status = 'jd_too_short';

-- 3) 记账
DELETE FROM schema_version;
INSERT INTO schema_version (version) VALUES (3);
