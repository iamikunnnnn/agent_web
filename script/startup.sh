#!/usr/bin/env bash

# 功能：一键初始化并启动项目
# 1. 检查/安装 uv（并尽量升级到较新版本）
# 2. 检查/安装 Python（优先 3.12，否则回退已有的 python3）
# 3. 使用 uv 安装 Python 依赖（优先 uv.lock，其次 requirements.txt）
# 4. 运行 mcp_main.py 和 main.py
# 5. 检查并启动 Docker 容器 metamcp-pg

set -euo pipefail

GREEN="\033[32m"
YELLOW="\033[33m"
RED="\033[31m"
RESET="\033[0m"

PYTHON_CMD=""
UV_PIP_MIRROR_FLAGS=""

log_info() {
  echo -e "${YELLOW}$*${RESET}"
}

log_ok() {
  echo -e "${GREEN}$*${RESET}"
}

log_warn() {
  echo -e "${YELLOW}$*${RESET}" >&2
}

log_error() {
  echo -e "${RED}$*${RESET}" >&2
}

log_step() {
  echo -e "${YELLOW}=== $* ===${RESET}"
}

is_windows_platform() {
  # 仅在真正的 Windows shell / Git Bash 下返回 0，WSL 归为类 Linux
  local uname_s
  uname_s="$(uname -s 2>/dev/null | tr '[:upper:]' '[:lower:]' || echo "")"
  case "${uname_s}" in
    mingw*|msys*|cygwin*|windows*)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

# 统一将工作目录切到项目根目录（脚本所在目录的上一级）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

log_info "Working directory: ${PROJECT_ROOT}"

check_and_install_uv() {
  log_step "Step 1/5: Checking uv installation"

  local uv_path=""

  if command -v uv >/dev/null 2>&1; then
    uv_path="$(command -v uv)"
  else
    # 常见安装路径（包括 WSL 下的默认 cargo 安装路径）
    local candidates=(
      "$HOME/.cargo/bin/uv"
      "$HOME/.local/bin/uv"
      "/usr/local/bin/uv"
      "$HOME/AppData/Local/Programs/uv/uv"
    )

    for p in "${candidates[@]}"; do
      if [[ -x "$p" ]]; then
        uv_path="$p"
        PATH="$(dirname "$p"):$PATH"
        break
      fi
    done
  fi

  if [[ -n "${uv_path}" ]]; then
    local before
    before="$("${uv_path}" --version 2>/dev/null | awk '{print $2}' | head -n1)"
    log_ok "Found uv at ${uv_path}, version: ${before}"

    # 尝试升级到最新版本（失败仅告警不退出）
    log_info "Trying to update uv to the latest version..."
    if "${uv_path}" self update >/dev/null 2>&1; then
      local after
      after="$(uv --version 2>/dev/null | awk '{print $2}' | head -n1)"
      if [[ -n "${after}" && "${after}" != "${before}" ]]; then
        log_ok "uv updated to version: ${after}"
      else
        log_ok "uv is already up to date"
      fi
    else
      log_warn "uv self update failed，可手动执行：uv self update"
    fi
    return 0
  fi

  log_info "uv not found, trying to install via official script..."

  if ! command -v curl >/dev/null 2>&1; then
    log_error "curl 未安装，无法自动安装 uv，请手动执行：curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
  fi

  if curl -LsSf https://astral.sh/uv/install.sh | sh; then
    log_ok "uv base installation succeeded, refreshing environment..."
    [[ -f "$HOME/.cargo/env" ]] && source "$HOME/.cargo/env" >/dev/null 2>&1
    [[ -f "$HOME/.profile" ]] && source "$HOME/.profile" >/dev/null 2>&1
    [[ -f "$HOME/.bashrc" ]] && source "$HOME/.bashrc" >/dev/null 2>&1
    PATH="$HOME/.cargo/bin:$HOME/.local/bin:/usr/local/bin:$PATH"

    log_info "Updating uv to the latest version..."
    if command -v uv >/dev/null 2>&1 && uv self update >/dev/null 2>&1; then
      local ver
      ver="$(uv --version 2>/dev/null | awk '{print $2}')"
      log_ok "uv now at version: ${ver}"
    else
      log_warn "uv 已安装但无法自动更新，如有需要可手动执行：uv self update"
    fi
  else
    log_error "uv 安装失败，请手动执行：curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
  fi
}

check_and_install_python() {
  log_step "Step 2/5: Checking Python (prefer 3.12)"

  if command -v python3.12 >/dev/null 2>&1; then
    local py_ver
    py_ver="$(python3.12 --version | awk '{print $2}')"
    log_ok "Found Python 3.12, version: ${py_ver}"
    PYTHON_CMD="python3.12"
    return 0
  fi

  if command -v python3 >/dev/null 2>&1; then
    local py_ver
    py_ver="$(python3 --version | awk '{print $2}')"
    log_warn "Python 3.12 not found, using existing python3 (${py_ver}). 如果需要强制 3.12，请手动升级。"
    PYTHON_CMD="python3"
    return 0
  fi

  log_info "Python 未安装，尝试在 Debian/Ubuntu/WSL 上自动安装 Python 3.12..."

  if command -v apt >/dev/null 2>&1; then
    if sudo apt update >/dev/null 2>&1 && sudo apt install -y python3.12 python3.12-pip python3.12-venv; then
      log_ok "Python 3.12 installed via apt"
      PYTHON_CMD="python3.12"
      [[ -f "$HOME/.bashrc" ]] && source "$HOME/.bashrc" >/dev/null 2>&1
      return 0
    else
      log_error "自动安装 Python 3.12 失败（apt）。"
      log_error "在 CentOS/RHEL 可使用：sudo yum install -y python3.12"
      exit 1
    fi
  else
    log_error "当前系统不支持自动安装 Python，请手动安装 Python 3.12 或 python3。"
    exit 1
  fi
}

setup_cn_pypi_mirror() {
  if [[ "${USE_CN_MIRROR:-1}" != "1" ]]; then
    UV_PIP_MIRROR_FLAGS=""
    return 0
  fi

  local url
  url="${PYPI_MIRROR_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"

  UV_PIP_MIRROR_FLAGS="--index-url ${url}"
  export PIP_INDEX_URL="${url}"

  log_info "Using China PyPI mirror: ${url}"
}

ensure_uv_venv() {
  # 如果设置了 UV_USE_SYSTEM=1，则跳过虚拟环境，直接用系统环境安装
  if [[ "${UV_USE_SYSTEM:-0}" == "1" ]]; then
    log_warn "UV_USE_SYSTEM=1，使用系统环境安装依赖（不创建 .venv）"
    return 0
  fi

  local venv_dir="${PROJECT_ROOT}/.venv"

  if [[ ! -d "${venv_dir}" ]]; then
    if [[ -z "${PYTHON_CMD}" ]]; then
      log_error "PYTHON_CMD 未设置，无法创建 uv 虚拟环境。"
      exit 1
    fi

    log_info "Creating uv virtual environment at ${venv_dir} (python: ${PYTHON_CMD})..."
    if uv venv --python "${PYTHON_CMD}" "${venv_dir}"; then
      log_ok "uv virtual environment created: ${venv_dir}"
    else
      log_warn "创建 uv 虚拟环境失败，将改为使用系统环境安装依赖（等价于设置 UV_USE_SYSTEM=1）"
      UV_USE_SYSTEM=1
      return 0
    fi
  else
    log_info "Using existing virtual environment: ${venv_dir}"
  fi

  # 激活虚拟环境，让后续的 uv pip 在该环境中执行
  if [[ -f "${venv_dir}/bin/activate" ]]; then
    if [[ "${VIRTUAL_ENV:-}" != "${venv_dir}" ]]; then
      log_info "Activating virtual environment: ${venv_dir}"
      # shellcheck disable=SC1090
      source "${venv_dir}/bin/activate"
    fi
  else
    log_warn "未找到 ${venv_dir}/bin/activate，可能不是标准 venv 结构，将退回使用系统环境（UV_USE_SYSTEM=1）"
    UV_USE_SYSTEM=1
  fi
}

install_deps_with_uv() {
  log_step "Step 3/5: Installing project dependencies with uv"

  if ! command -v uv >/dev/null 2>&1; then
    log_error "uv 命令不存在，无法安装依赖。"
    exit 1
  fi

  ensure_uv_venv
  setup_cn_pypi_mirror

  if [[ -f "uv.lock" ]]; then
    log_info "Found uv.lock, installing dependencies according to lockfile..."
    if uv pip sync ${UV_PIP_MIRROR_FLAGS} uv.lock; then
      log_ok "Dependencies installed from uv.lock"
      return 0
    fi

    log_warn "uv pip sync uv.lock 失败，尝试使用 requirements.txt 回退安装..."
    if [[ -f "requirements.txt" ]]; then
      if uv pip install ${UV_PIP_MIRROR_FLAGS} -r requirements.txt; then
        log_ok "Dependencies installed from requirements.txt"
        log_info "Re-generating uv.lock from requirements.txt (best-effort)..."
        uv pip compile requirements.txt -o uv.lock >/dev/null 2>&1 || \
          log_warn "自动生成 uv.lock 失败，可手动执行：uv pip compile requirements.txt -o uv.lock"
        return 0
      else
        log_error "基于 requirements.txt 安装依赖失败。"
        exit 1
      fi
    else
      log_error "既没有 uv.lock 也没有 requirements.txt，无法安装依赖。"
      exit 1
    fi
  elif [[ -f "requirements.txt" ]]; then
    log_info "No uv.lock found, installing from requirements.txt..."
    if uv pip install ${UV_PIP_MIRROR_FLAGS} -r requirements.txt; then
      log_ok "Dependencies installed from requirements.txt"
      log_info "Generating uv.lock from requirements.txt (best-effort)..."
      uv pip compile requirements.txt -o uv.lock >/dev/null 2>&1 || \
        log_warn "自动生成 uv.lock 失败，可手动执行：uv pip compile requirements.txt -o uv.lock"
      return 0
    else
      log_error "基于 requirements.txt 安装依赖失败。"
      exit 1
    fi
  else
    log_warn "未找到 uv.lock 或 requirements.txt，跳过依赖安装。"
  fi
}

run_python_scripts() {
  log_step "Step 4/5: Running Python entry scripts"

  if [[ -z "${PYTHON_CMD}" ]]; then
    log_error "PYTHON_CMD 未设置，内部错误。"
    exit 1
  fi

  log_info "Running mcp_main.py ..."
  if "${PYTHON_CMD}" mcp_main.py; then
    log_ok "mcp_main.py executed successfully"
  else
    log_warn "mcp_main.py 执行异常，将继续执行后续步骤。"
  fi

  log_info "Running main.py ..."
  if "${PYTHON_CMD}" main.py; then
    log_ok "main.py executed successfully"
  else
    log_warn "main.py 执行异常，请检查日志。"
  fi
}

manage_docker() {
  log_step "Step 5/5: Checking Docker container metamcp-pg"

  if ! command -v docker >/dev/null 2>&1; then
    log_warn "docker 命令未找到，跳过 Docker 容器检查与启动。"
    return 0
  fi

  log_info "cd server/meta_mcp_main"
  if ! cd server/meta_mcp_main; then
    log_error "无法进入目录 server/meta_mcp_main"
    return 1
  fi

  log_info "Checking if container 'metamcp-pg' exists..."
  local container_id
  container_id="$(docker ps -a --filter "name=^/metamcp-pg$" --quiet || true)"

  if [[ -z "${container_id}" ]]; then
    log_info "Container 'metamcp-pg' not found, running 'docker compose up -d'..."
    if docker compose up -d; then
      log_ok "docker compose up -d executed successfully, 'metamcp-pg' should be running."
    else
      log_error "docker compose up -d 执行失败，请手动检查。"
    fi
  else
    log_info "Container 'metamcp-pg' exists, starting it..."
    if docker start metamcp-pg; then
      log_ok "Container 'metamcp-pg' started successfully."
    else
      log_error "启动容器 'metamcp-pg' 失败，请手动检查。"
    fi
  fi
}

install_deps_with_uv_safe() {
  log_step "Step 3/5: Installing project dependencies with uv"

  if ! command -v uv >/dev/null 2>&1; then
    log_error "uv 命令不存在，无法安装依赖。"
    exit 1
  fi

  ensure_uv_venv
  setup_cn_pypi_mirror

  # Windows 平台优先使用 uv.lock；非 Windows/WSL 下跳过 uv.lock，避免 pywin32 等 Windows-only 包解析失败
  local use_lock=1
  if ! is_windows_platform; then
    use_lock=0
    if [[ -f "uv.lock" ]]; then
      log_warn "非 Windows 平台检测到 uv.lock，其中可能包含 Windows-only 依赖（如 pywin32），将跳过 uv.lock，改用 requirements.txt 安装。"
    fi
  fi

  if [[ ${use_lock} -eq 1 && -f "uv.lock" ]]; then
    log_info "Found uv.lock, installing dependencies according to lockfile..."
    if uv pip sync ${UV_PIP_MIRROR_FLAGS} uv.lock; then
      log_ok "Dependencies installed from uv.lock"
      return 0
    fi

    log_warn "uv pip sync uv.lock 失败，将尝试使用 requirements.txt 回退安装..."
  fi

  if [[ -f "requirements.txt" ]]; then
    local req_file="requirements.txt"

    # 在非 Windows/WSL 环境下自动过滤掉 pywin32 这类仅 Windows 支持的依赖
    if ! is_windows_platform; then
      req_file="requirements.uv-nonwin.txt"
      log_warn "非 Windows 平台，将从 requirements.txt 中过滤掉 Windows-only 依赖（如 pywin32）到 ${req_file} 后再安装。"
      sed '/^pywin32\([[:space:]=<>!~]\|$\)/d' requirements.txt > "${req_file}"
    fi

    log_info "Installing dependencies from ${req_file}..."
    if uv pip install ${UV_PIP_MIRROR_FLAGS} -r "${req_file}"; then
      log_ok "Dependencies installed from ${req_file}"
      if [[ -f "requirements.txt" ]]; then
        log_info "Generating uv.lock from requirements.txt (best-effort)..."
        uv pip compile requirements.txt -o uv.lock >/dev/null 2>&1 || \
          log_warn "自动生成 uv.lock 失败，可手动执行：uv pip compile requirements.txt -o uv.lock"
      fi
      return 0
    else
      log_error "基于 ${req_file} 安装依赖失败。"
      exit 1
    fi
  else
    log_warn "未找到 uv.lock 或 requirements.txt，跳过依赖安装。"
  fi
}

# 顺序执行各步骤，保持脚本简单直观
check_and_install_uv
check_and_install_python
install_deps_with_uv
run_python_scripts
manage_docker
