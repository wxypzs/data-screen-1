#!/bin/bash
# 容器首次初始化时自动导入四张 .dat 数据
# 由 docker-compose 挂载:  ./ -> /seed (只读), 容器内可写目录 /var/lib/mysql-files (secure-file-priv)
set -e
echo "[init] 复制 .dat 到 /var/lib/mysql-files ..."
cp /seed/host_detail.dat /seed/mod_detail.dat /seed/disk_tsar.dat /seed/pref_tsar.dat /var/lib/mysql-files/
echo "[init] 导入数据到 data_screen ..."
mysql --default-character-set=utf8mb4 -uroot -p"${MYSQL_ROOT_PASSWORD:-root123456}" data_screen < /seed/mysql/load.sql
echo "[init] 数据导入完成"
