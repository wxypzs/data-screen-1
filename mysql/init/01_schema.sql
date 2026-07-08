-- ============================================================
-- 01_schema.sql  ·  数据库与四张表结构定义
-- 数据库: data_screen  (utf8mb4, 支持中文)
-- 四张表:
--   host_detail  主机元数据
--   mod_detail   指标元数据
--   disk_tsar    磁盘分钟级指标 (ts, hostid, type, mod, value, tag)
--   pref_tsar    性能分钟级指标 (ts, hostid, type, mod, value, tag)
-- 另建两个视图, 将指标与主机/指标元数据关联, 便于后续大屏查询。
-- ============================================================

CREATE DATABASE IF NOT EXISTS data_screen
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;
USE data_screen;

DROP VIEW IF EXISTS v_disk_metrics;
DROP VIEW IF EXISTS v_pref_metrics;
DROP TABLE IF EXISTS host_detail, mod_detail, disk_tsar, pref_tsar;

-- ---------- 1. 主机元数据 ----------
CREATE TABLE host_detail (
  hostid    VARCHAR(32)  NOT NULL COMMENT '主机ID',
  hostname  VARCHAR(64)  NOT NULL COMMENT '主机名',
  owner     VARCHAR(32)           COMMENT '负责人',
  model     VARCHAR(32)           COMMENT '机型',
  location1 VARCHAR(32)           COMMENT '机房',
  location2 VARCHAR(32)           COMMENT '机柜',
  PRIMARY KEY (hostid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='主机元数据';

-- ---------- 2. 指标元数据 ----------
CREATE TABLE mod_detail (
  `mod`  VARCHAR(32) NOT NULL COMMENT '指标编码',
  type   VARCHAR(20)          COMMENT '类型(disk/pref)',
  `desc` VARCHAR(64)          COMMENT '指标描述',
  unit   VARCHAR(32)          COMMENT '单位',
  tag    VARCHAR(40)          COMMENT '指标分组标签',
  PRIMARY KEY (`mod`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='指标元数据';

-- ---------- 3. 磁盘分钟级指标 ----------
CREATE TABLE disk_tsar (
  id     BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  ts     BIGINT          COMMENT 'epoch 毫秒时间戳',
  hostid VARCHAR(32)     COMMENT '主机ID',
  type   VARCHAR(20)     COMMENT '类型',
  `mod`  VARCHAR(32)     COMMENT '指标编码',
  value  DECIMAL(14,4)   COMMENT '指标值',
  tag    VARCHAR(40)     COMMENT '指标分组标签',
  PRIMARY KEY (id),
  INDEX idx_disk_ts   (ts),
  INDEX idx_disk_host (hostid),
  INDEX idx_disk_mod  (`mod`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='磁盘分钟级指标';

-- ---------- 4. 性能分钟级指标 ----------
CREATE TABLE pref_tsar (
  id     BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  ts     BIGINT          COMMENT 'epoch 毫秒时间戳',
  hostid VARCHAR(32)     COMMENT '主机ID',
  type   VARCHAR(20)     COMMENT '类型',
  `mod`  VARCHAR(32)     COMMENT '指标编码',
  value  DECIMAL(14,4)   COMMENT '指标值',
  tag    VARCHAR(40)     COMMENT '指标分组标签',
  PRIMARY KEY (id),
  INDEX idx_pref_ts   (ts),
  INDEX idx_pref_host (hostid),
  INDEX idx_pref_mod  (`mod`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='性能分钟级指标';

-- ---------- 视图: 关联后的指标(便于大屏查询) ----------
CREATE VIEW v_disk_metrics AS
SELECT d.ts, d.hostid, h.hostname, h.owner, h.model, h.location1, h.location2,
       d.type, d.`mod`, m.`desc` AS metric_desc, m.unit, d.value, d.tag
FROM disk_tsar d
LEFT JOIN host_detail h ON d.hostid = h.hostid
LEFT JOIN mod_detail  m ON d.`mod` = m.`mod`;

CREATE VIEW v_pref_metrics AS
SELECT p.ts, p.hostid, h.hostname, h.owner, h.model, h.location1, h.location2,
       p.type, p.`mod`, m.`desc` AS metric_desc, m.unit, p.value, p.tag
FROM pref_tsar p
LEFT JOIN host_detail h ON p.hostid = h.hostid
LEFT JOIN mod_detail  m ON p.`mod` = m.`mod`;
