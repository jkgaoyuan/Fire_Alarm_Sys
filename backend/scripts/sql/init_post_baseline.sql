BEGIN;


CREATE TABLE linkage_plans (
    plan_name VARCHAR(100) NOT NULL, 
    org_id INTEGER, 
    fire_type VARCHAR(20), 
    trigger_device_type_id INTEGER, 
    trigger_alarm_type VARCHAR(20), 
    actions JSONB NOT NULL, 
    is_enabled BOOLEAN DEFAULT 'true' NOT NULL, 
    is_simulation_allowed BOOLEAN DEFAULT 'true' NOT NULL, 
    created_by INTEGER, 
    id SERIAL NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(created_by) REFERENCES users (id), 
    FOREIGN KEY(org_id) REFERENCES organizations (id), 
    FOREIGN KEY(trigger_device_type_id) REFERENCES device_types (id)
);

CREATE INDEX idx_linkage_plans_org ON linkage_plans (org_id);

CREATE INDEX idx_linkage_plans_trigger ON linkage_plans (trigger_device_type_id, trigger_alarm_type);

CREATE INDEX idx_linkage_plans_enabled ON linkage_plans (is_enabled);

CREATE TABLE alarm_linkage_logs (
    alarm_id INTEGER NOT NULL, 
    plan_id INTEGER, 
    action_type VARCHAR(50) NOT NULL, 
    target_device_id INTEGER, 
    status VARCHAR(20) DEFAULT 'pending' NOT NULL, 
    executed_at TIMESTAMP WITH TIME ZONE, 
    completed_at TIMESTAMP WITH TIME ZONE, 
    result_message TEXT, 
    is_simulation BOOLEAN DEFAULT 'false' NOT NULL, 
    delay_seconds INTEGER DEFAULT '0' NOT NULL, 
    id SERIAL NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(alarm_id) REFERENCES alarms (id), 
    FOREIGN KEY(plan_id) REFERENCES linkage_plans (id), 
    FOREIGN KEY(target_device_id) REFERENCES devices (id)
);

CREATE INDEX idx_alarm_linkage_logs_alarm ON alarm_linkage_logs (alarm_id);

CREATE INDEX idx_alarm_linkage_logs_plan ON alarm_linkage_logs (plan_id);

CREATE INDEX idx_alarm_linkage_logs_status ON alarm_linkage_logs (status);

CREATE INDEX idx_alarm_linkage_logs_created ON alarm_linkage_logs (created_at);

CREATE INDEX idx_alarm_linkage_logs_target ON alarm_linkage_logs (target_device_id);

UPDATE alembic_version SET version_num='xxx_linkage_tables' WHERE alembic_version.version_num = '54d02fd0cebb';


CREATE TABLE inspection_plans (
    id SERIAL NOT NULL, 
    plan_name VARCHAR(100) NOT NULL, 
    org_id INTEGER, 
    device_type_id INTEGER, 
    responsible_user_id INTEGER, 
    cycle_type VARCHAR(20) NOT NULL, 
    cycle_days INTEGER, 
    start_date DATE, 
    end_date DATE, 
    is_enabled BOOLEAN DEFAULT true NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(org_id) REFERENCES organizations (id), 
    FOREIGN KEY(device_type_id) REFERENCES device_types (id), 
    FOREIGN KEY(responsible_user_id) REFERENCES users (id)
);

CREATE TABLE inspection_tasks (
    id SERIAL NOT NULL, 
    plan_id INTEGER NOT NULL, 
    responsible_user_id INTEGER, 
    task_date DATE NOT NULL, 
    status VARCHAR(20) DEFAULT 'pending' NOT NULL, 
    completed_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(plan_id) REFERENCES inspection_plans (id), 
    FOREIGN KEY(responsible_user_id) REFERENCES users (id)
);

CREATE TABLE inspection_records (
    id SERIAL NOT NULL, 
    task_id INTEGER NOT NULL, 
    device_id INTEGER NOT NULL, 
    inspected_by INTEGER, 
    created_by INTEGER, 
    result VARCHAR(20) NOT NULL, 
    abnormal_desc TEXT, 
    photos JSONB DEFAULT '[]' NOT NULL, 
    inspected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(task_id) REFERENCES inspection_tasks (id), 
    FOREIGN KEY(device_id) REFERENCES devices (id), 
    FOREIGN KEY(inspected_by) REFERENCES users (id), 
    FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE INDEX idx_inspection_plans_org_id ON inspection_plans (org_id);

CREATE INDEX idx_inspection_plans_device_type_id ON inspection_plans (device_type_id);

CREATE INDEX idx_inspection_plans_responsible_user_id ON inspection_plans (responsible_user_id);

CREATE INDEX idx_inspection_tasks_plan_id ON inspection_tasks (plan_id);

CREATE INDEX idx_inspection_tasks_responsible_user_id ON inspection_tasks (responsible_user_id);

CREATE INDEX idx_inspection_tasks_task_date ON inspection_tasks (task_date);

CREATE INDEX idx_inspection_records_task_id ON inspection_records (task_id);

CREATE INDEX idx_inspection_records_device_id ON inspection_records (device_id);

CREATE INDEX idx_inspection_records_created_by ON inspection_records (created_by);

INSERT INTO alembic_version (version_num) VALUES ('add_inspection') RETURNING alembic_version.version_num;


CREATE TABLE repair_orders (
    id SERIAL NOT NULL, 
    order_no VARCHAR(50) NOT NULL, 
    device_id INTEGER NOT NULL, 
    alarm_id INTEGER, 
    inspection_record_id INTEGER, 
    fault_desc TEXT NOT NULL, 
    status VARCHAR(20) DEFAULT 'pending' NOT NULL, 
    reporter_id INTEGER, 
    repairer_id INTEGER, 
    acceptor_id INTEGER, 
    assigned_at TIMESTAMP WITH TIME ZONE, 
    completed_at TIMESTAMP WITH TIME ZONE, 
    accepted_at TIMESTAMP WITH TIME ZONE, 
    repair_result TEXT, 
    return_reason TEXT, 
    created_by INTEGER, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (order_no), 
    UNIQUE (inspection_record_id), 
    FOREIGN KEY(device_id) REFERENCES devices (id), 
    FOREIGN KEY(alarm_id) REFERENCES alarms (id), 
    FOREIGN KEY(inspection_record_id) REFERENCES inspection_records (id), 
    FOREIGN KEY(reporter_id) REFERENCES users (id), 
    FOREIGN KEY(repairer_id) REFERENCES users (id), 
    FOREIGN KEY(acceptor_id) REFERENCES users (id), 
    FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE INDEX idx_repair_orders_device_id ON repair_orders (device_id);

CREATE INDEX idx_repair_orders_alarm_id ON repair_orders (alarm_id);

CREATE INDEX idx_repair_orders_inspection_record_id ON repair_orders (inspection_record_id);

CREATE INDEX idx_repair_orders_status ON repair_orders (status);

CREATE INDEX idx_repair_orders_reporter_id ON repair_orders (reporter_id);

CREATE INDEX idx_repair_orders_repairer_id ON repair_orders (repairer_id);

CREATE INDEX idx_repair_orders_created_by ON repair_orders (created_by);

CREATE INDEX idx_repair_orders_device_status ON repair_orders (device_id, status);

CREATE INDEX idx_repair_orders_repairer_status ON repair_orders (repairer_id, status);

UPDATE alembic_version SET version_num='add_repair_orders' WHERE alembic_version.version_num = 'add_inspection';


DELETE FROM alembic_version WHERE alembic_version.version_num = 'add_repair_orders';

UPDATE alembic_version SET version_num='merge_branches' WHERE alembic_version.version_num = 'xxx_linkage_tables';


ALTER TABLE inspection_plans ADD COLUMN created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL;

ALTER TABLE inspection_plans ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE inspection_tasks ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE inspection_records ADD COLUMN created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL;

ALTER TABLE inspection_records ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE;

CREATE INDEX idx_inspection_plans_created_at ON inspection_plans (created_at);

CREATE INDEX idx_inspection_plans_updated_at ON inspection_plans (updated_at);

CREATE INDEX idx_inspection_tasks_updated_at ON inspection_tasks (updated_at);

CREATE INDEX idx_inspection_records_created_at ON inspection_records (created_at);

CREATE INDEX idx_inspection_records_updated_at ON inspection_records (updated_at);

UPDATE alembic_version SET version_num='add_inspection_audit' WHERE alembic_version.version_num = 'merge_branches';


CREATE TABLE drill_events (
    id BIGSERIAL NOT NULL, 
    drill_name VARCHAR(100) NOT NULL, 
    drill_type VARCHAR(20) NOT NULL, 
    planned_at TIMESTAMP WITH TIME ZONE, 
    actual_start_at TIMESTAMP WITH TIME ZONE, 
    actual_end_at TIMESTAMP WITH TIME ZONE, 
    location VARCHAR(255), 
    participants JSON, 
    status VARCHAR(20) DEFAULT 'planned', 
    summary TEXT, 
    photos JSON, 
    videos JSON, 
    created_by BIGINT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(), 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(), 
    PRIMARY KEY (id), 
    FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE INDEX idx_drill_events_status ON drill_events (status);

CREATE INDEX idx_drill_events_planned ON drill_events (planned_at);

CREATE INDEX idx_drill_events_type ON drill_events (drill_type);

CREATE INDEX idx_drill_events_created_by ON drill_events (created_by);

CREATE TABLE drill_evaluations (
    id BIGSERIAL NOT NULL, 
    drill_id BIGINT NOT NULL, 
    evaluator_id BIGINT NOT NULL, 
    evaluated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(), 
    items JSON NOT NULL, 
    total_score INTEGER, 
    problems TEXT, 
    improvements TEXT, 
    evaluation_summary TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(), 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(), 
    PRIMARY KEY (id), 
    FOREIGN KEY(drill_id) REFERENCES drill_events (id), 
    FOREIGN KEY(evaluator_id) REFERENCES users (id), 
    CONSTRAINT uq_drill_evaluations_drill_id UNIQUE (drill_id)
);

CREATE INDEX idx_drill_evaluations_drill ON drill_evaluations (drill_id);

CREATE INDEX idx_drill_evaluations_evaluator ON drill_evaluations (evaluator_id);

UPDATE alembic_version SET version_num='create_drill_tables' WHERE alembic_version.version_num = 'add_inspection_audit';


CREATE TABLE report_export_tasks (
    task_no VARCHAR(50) NOT NULL, 
    task_type VARCHAR(50) NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    file_path VARCHAR(500), 
    file_name VARCHAR(200), 
    total_rows INTEGER, 
    params JSON, 
    error_message TEXT, 
    created_by INTEGER NOT NULL, 
    completed_at TIMESTAMP WITH TIME ZONE, 
    id SERIAL NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(created_by) REFERENCES users (id), 
    UNIQUE (task_no)
);

COMMENT ON COLUMN report_export_tasks.task_no IS '任务编号';

COMMENT ON COLUMN report_export_tasks.task_type IS '导出类型';

COMMENT ON COLUMN report_export_tasks.status IS '状态 pending/running/completed/failed';

COMMENT ON COLUMN report_export_tasks.file_path IS '文件存储路径';

COMMENT ON COLUMN report_export_tasks.file_name IS '下载文件名';

COMMENT ON COLUMN report_export_tasks.total_rows IS '总行数';

COMMENT ON COLUMN report_export_tasks.params IS '导出参数';

COMMENT ON COLUMN report_export_tasks.error_message IS '失败原因';

COMMENT ON COLUMN report_export_tasks.created_by IS '创建人（DEC-004）';

COMMENT ON COLUMN report_export_tasks.completed_at IS '完成时间';

CREATE INDEX ix_report_export_tasks_created_by ON report_export_tasks (created_by);

CREATE INDEX ix_report_export_tasks_status ON report_export_tasks (status);

UPDATE alembic_version SET version_num='4767a93d67a0' WHERE alembic_version.version_num = 'create_drill_tables';

COMMIT;

