-- 3.3 实时监控与电子地图：既有表增列
--
-- 背景（DEC-006 / 计划 4.2）：项目建表沿用 Base.metadata.create_all()，
-- 而 create_all 只建新表、**不会给已存在的表补列**。3.3 首次需要给
-- 3.1/3.2 已有的 organizations / devices 两张表加列，因此已有库必须执行本脚本。
--
-- 用法（二选一）：
--   1) docker compose exec -T postgres psql -U fire -d fire_alarm_sys < backend/scripts/sql/3_3_alter.sql
--   2) 开发期直接重建数据卷：docker compose down -v && docker compose up -d --build
--
-- 全部语句幂等（IF NOT EXISTS），可重复执行。
-- alarms 为新表，由 create_all 自动创建，无需在此处理。
--
-- 计划 4.2 里的可选列 devices.offline_since 未纳入：模型未声明，
-- 离线判定统一以 last_report_at + OFFLINE_THRESHOLD_SECONDS 计算，避免两处真相。

ALTER TABLE organizations ADD COLUMN IF NOT EXISTS map_image_url    VARCHAR(500);
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS map_image_width  INTEGER;
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS map_image_height INTEGER;
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS map_origin       VARCHAR(20) DEFAULT 'top_left';

ALTER TABLE devices ADD COLUMN IF NOT EXISTS last_report_at TIMESTAMPTZ;

-- alarms 表及其两个索引由 models/alarm.py 的 __table_args__ 交给 create_all 创建，
-- 本脚本不重复声明，避免 DDL 与 ORM 定义漂移。
