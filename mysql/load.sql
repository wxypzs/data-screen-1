-- ============================================================
-- load.sql  ·  导入四张 .dat (TSV, CRLF, 含表头)
-- 用法(容器启动后):
--   docker compose exec mysql sh -c "cp /seed/host_detail.dat /seed/mod_detail.dat /seed/disk_tsar.dat /seed/pref_tsar.dat /var/lib/mysql-files/"
--   docker compose exec -T mysql mysql -uroot -proot123456 data_screen < mysql/load.sql
-- 文件经 cp 放入容器可写目录 /var/lib/mysql-files (secure-file-priv 指向此处)
-- ============================================================
USE data_screen;

LOAD DATA INFILE '/var/lib/mysql-files/host_detail.dat'
  INTO TABLE host_detail
  CHARACTER SET utf8mb4
  FIELDS TERMINATED BY '\t' ESCAPED BY ''
  LINES TERMINATED BY '\r\n'
  IGNORE 1 LINES
  (hostid, hostname, owner, model, location1, location2);

LOAD DATA INFILE '/var/lib/mysql-files/mod_detail.dat'
  INTO TABLE mod_detail
  CHARACTER SET utf8mb4
  FIELDS TERMINATED BY '\t' ESCAPED BY ''
  LINES TERMINATED BY '\r\n'
  IGNORE 1 LINES
  (`mod`, type, `desc`, unit, tag);

LOAD DATA INFILE '/var/lib/mysql-files/disk_tsar.dat'
  INTO TABLE disk_tsar
  CHARACTER SET utf8mb4
  FIELDS TERMINATED BY '\t' ESCAPED BY ''
  LINES TERMINATED BY '\r\n'
  IGNORE 1 LINES
  (ts, hostid, type, `mod`, value, tag);

LOAD DATA INFILE '/var/lib/mysql-files/pref_tsar.dat'
  INTO TABLE pref_tsar
  CHARACTER SET utf8mb4
  FIELDS TERMINATED BY '\t' ESCAPED BY ''
  LINES TERMINATED BY '\r\n'
  IGNORE 1 LINES
  (ts, hostid, type, `mod`, value, tag);
