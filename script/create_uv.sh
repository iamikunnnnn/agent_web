#!/usr/bin/env bash

# 功能：在项目根目录生成 requirements.txt 和 uv.lock
#  - 优先使用 uv 来 freeze（如果已安装）
#  - 否则回退到 python3 / python 的 pip freeze
#  - 如 uv 不存在则自动安装一次
#  - 新增：过滤掉 win32 相关依赖包

set -euo pipefail

GREEN="\033[32m"
YELLOW="\033[33m"
RED="\033[31m"
RESET="\033[0m"

log_info() {
  echo -e "${YELLOW}$*${RESET}"
}

log_ok() {
  echo -e "${GREEN}$*${RESET}"
}

log_error() {
  echo -e "${RED}$*${RESET}" >&2
}

# 统一将工作目录切到项目根目录（脚本所在目录的上一级）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

log_info "Working directory: ${PROJECT_ROOT}"

generate_requirements() {
  log_info "=== Step 1/3: Generating requirements.txt (exclude win32 packages) ==="

  # 定义过滤命令：剔除包含 win32 关键字的行（不区分大小写，兼容 Win32、WIN32 等）
  local FILTER_CMD="grep -v -i 'win32'"

  if command -v uv >/dev/null 2>&1; then
    # 改动 1：uv pip freeze 输出后通过管道过滤 win32 相关包
    uv pip freeze | ${FILTER_CMD} > requirements.txt
  else
    if command -v python3 >/dev/null 2>&1; then
      # 改动 2：原生 pip freeze 输出后同样过滤 win32 相关包
      python3 -m pip freeze | ${FILTER_CMD} > requirements.txt
    elif command -v python >/dev/null 2>&1; then
      python -m pip freeze | ${FILTER_CMD} > requirements.txt
    else
      log_error "Python 未找到，无法生成 requirements.txt"
      exit 1
    fi
  fi

  if [[ ! -s requirements.txt ]]; then
    log_error "requirements.txt 未生成或为空，请检查当前环境的 Python 安装和依赖"
    exit 1
  fi

  log_ok "requirements.txt 已生成（已忽略 win32 相关包）：$(pwd)/requirements.txt"
}

ensure_uv() {
  log_info "=== Step 2/3: Ensuring uv is installed ==="

  if command -v uv >/dev/null 2>&1; then
    local uv_version
    uv_version="$(uv --version 2>/dev/null | awk '{print $2}')"
    log_ok "检测到 uv，版本：${uv_version}"
    return 0
  fi

  if ! command -v curl >/dev/null 2>&1; then
    log_error "未检测到 curl，无法自动安装 uv，请手动执行：curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
  fi

  log_info "未检测到 uv，开始自动安装..."
  if curl -LsSf https://astral.sh/uv/install.sh | sh; then
    log_ok "uv 基础安装成功，刷新环境变量..."
    [[ -f "$HOME/.cargo/env" ]] && source "$HOME/.cargo/env" >/dev/null 2>&1
    [[ -f "$HOME/.profile" ]] && source "$HOME/.profile" >/dev/null 2>&1
  else
    log_error "uv 安装失败，请手动执行：curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
  fi

  if ! command -v uv >/dev/null 2>&1; then
    log_error "安装 uv 后仍然无法在 PATH 中找到 uv，可尝试重新登录终端或手动配置 PATH"
    exit 1
  fi

  local uv_version
  uv_version="$(uv --version 2>/dev/null | awk '{print $2}')"
  log_ok "uv 安装完成，版本：${uv_version}"
}

generate_uv_lock() {
  log_info "=== Step 3/3: Generating uv.lock from requirements.txt ==="

  if ! command -v uv >/dev/null 2>&1; then
    log_error "未找到 uv 命令，无法生成 uv.lock"
    exit 1
  fi

  if [[ ! -f "requirements.txt" ]]; then
    log_error "requirements.txt 不存在，无法生成 uv.lock"
    exit 1
  fi

  # 显式指定输出文件名，避免目录中已有其他 lock 文件时产生混淆
  if uv pip compile requirements.txt -o uv.lock; then
    log_ok "uv.lock 已生成：$(pwd)/uv.lock"
  else
    log_error "生成 uv.lock 失败，请检查 requirements.txt 格式是否正确"
    exit 1
  fi
}

main() {
  generate_requirements
  ensure_uv
  generate_uv_lock

  log_ok "=== All done: requirements.txt & uv.lock generated in project root ==="
}

main "$@"