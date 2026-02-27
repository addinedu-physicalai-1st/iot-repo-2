#!/usr/bin/env bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SQL_FILE="${SCRIPT_DIR}/init.sql"

if ! command -v mysql >/dev/null 2>&1; then
  echo "mysql 명령을 찾을 수 없습니다. MySQL 클라이언트가 설치되어 있는지 확인하세요."
  exit 1
fi

echo "MySQL root 비밀번호를 입력하면 smart_parking DB를 초기화합니다."
mysql -u root -p < "${SQL_FILE}"

echo "DB 초기화가 완료되었습니다."

