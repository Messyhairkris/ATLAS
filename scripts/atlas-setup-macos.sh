#!/usr/bin/env bash
# ATLAS macOS setup (#32 hybrid path) — installs the native llama-server
# build with Metal acceleration plus the brew deps the rest of the
# install needs. Docker still runs the other 4 ATLAS services (proxy,
# v3, lens, sandbox) via docker-compose.macos.yml.
#
# Why hybrid: Apple Silicon under MoltenVK in Docker Desktop is 5-10x
# slower than native Metal. Running ONLY llama-server natively gets us
# the inference perf without rewriting the entire service stack as
# native Mac binaries (the bulk of the slowdown is inference, not the
# small Python/Go services). See docs/SETUP_MACOS.md for the full
# walkthrough.
#
# Usage:
#   ./scripts/atlas-setup-macos.sh                # default install
#   ./scripts/atlas-setup-macos.sh --rebuild      # force rebuild llama-server
#   ./scripts/atlas-setup-macos.sh --prefix DIR   # install root override
#
# Idempotent — re-running is cheap, only rebuilds when --rebuild is
# passed or when LLAMA_CPP_REV in the Dockerfiles has changed since
# the last build.

set -euo pipefail

# ---------------------------------------------------------------------------
# Config — keep LLAMA_CPP_REV aligned with inference/Dockerfile.v31.
# The CI smoke test (`llama-patches-apply`) gates on cross-Dockerfile
# agreement; this script reads the SHA from the Dockerfile so there's
# one source of truth. If the Dockerfile is missing, fall back to a
# pinned default that we update in lockstep.
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ATLAS_ROOT="$(dirname "$SCRIPT_DIR")"
DEFAULT_PREFIX="$HOME/.atlas/macos"
PREFIX="$DEFAULT_PREFIX"
REBUILD=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --rebuild) REBUILD=1; shift;;
    --prefix)  PREFIX="$2"; shift 2;;
    -h|--help)
      sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'
      exit 0;;
    *) echo "unknown flag: $1" >&2; exit 2;;
  esac
done

LLAMA_BUILD_DIR="$PREFIX/llama.cpp"
LLAMA_BIN_DIR="$PREFIX/bin"
LLAMA_SERVER="$LLAMA_BIN_DIR/llama-server-metal"
PATCH_DIR="$ATLAS_ROOT/inference/patches"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

bold()   { printf '\033[1m%s\033[0m\n' "$*"; }
green()  { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
red()    { printf '\033[31m%s\033[0m\n' "$*" >&2; }
step()   { printf '\n\033[1m[%s]\033[0m %s\n' "$1" "$2"; }

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    red "required command not found: $1"
    red "  $2"
    exit 1
  fi
}

extract_llama_rev() {
  # Read the SHA pin from inference/Dockerfile.v31 so this script and
  # the docker builds always agree. If we can't read it, error out
  # rather than guess — a wrong SHA means the patch won't apply.
  local dockerfile="$ATLAS_ROOT/inference/Dockerfile.v31"
  if [[ ! -f "$dockerfile" ]]; then
    red "Dockerfile.v31 not found at $dockerfile"
    red "  Are you running this from inside the ATLAS repo?"
    exit 1
  fi
  local rev
  rev=$(grep -oE 'ARG LLAMA_CPP_REV=[a-f0-9]+' "$dockerfile" | head -1 | cut -d= -f2)
  if [[ -z "$rev" ]]; then
    red "could not extract LLAMA_CPP_REV from $dockerfile"
    exit 1
  fi
  echo "$rev"
}

# ---------------------------------------------------------------------------
# Step 1 — sanity check: macOS + Apple Silicon
# ---------------------------------------------------------------------------

step "1/7" "Verifying macOS + Apple Silicon"

if [[ "$(uname -s)" != "Darwin" ]]; then
  red "this script is for macOS only — got $(uname -s)."
  red "  On Linux use the bootstrap installer or docker compose directly."
  exit 1
fi

ARCH="$(uname -m)"
if [[ "$ARCH" != "arm64" ]]; then
  yellow "Detected $ARCH (Intel Mac). Metal acceleration is Apple-Silicon-only."
  yellow "  llama.cpp will still build but use CPU. For Intel Macs the Docker"
  yellow "  + Vulkan path is usually a better tradeoff. Continue anyway? [y/N]"
  read -r ans
  case "$ans" in y|Y|yes) ;; *) exit 0;; esac
fi

green "  OK: $(uname -s) $(uname -m), $(sw_vers -productVersion)"

# ---------------------------------------------------------------------------
# Step 2 — Xcode Command Line Tools (required for cmake + git +
# Apple's metal-cpp headers).
# ---------------------------------------------------------------------------

step "2/7" "Checking Xcode Command Line Tools"

if ! xcode-select -p >/dev/null 2>&1; then
  yellow "  Xcode CLT not installed. Triggering installer (a GUI dialog will appear)."
  yellow "  Re-run this script once the install completes."
  xcode-select --install || true
  exit 1
fi
green "  OK: $(xcode-select -p)"

# ---------------------------------------------------------------------------
# Step 3 — Homebrew + deps. Don't auto-install brew (security: never
# run a third-party install script unattended). Tell the user how.
# ---------------------------------------------------------------------------

step "3/7" "Checking Homebrew + dependencies"

if ! command -v brew >/dev/null 2>&1; then
  red "Homebrew not installed. Install it manually before re-running:"
  red ""
  red "  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
  red ""
  red "Then follow the post-install instructions to add brew to your PATH."
  exit 1
fi
green "  OK: $(brew --version | head -1)"

# cmake + git + python are the hard requirements. uv is the
# recommended Python package manager (10-100x faster than pip for
# resolving) but optional — fall back to pip if missing.
NEED=()
for pkg in cmake git python@3.12; do
  if ! brew list --formula "$pkg" >/dev/null 2>&1; then
    NEED+=("$pkg")
  fi
done

if [[ ${#NEED[@]} -gt 0 ]]; then
  yellow "  Missing brew packages: ${NEED[*]}"
  yellow "  Installing now (may take a few minutes)..."
  brew install "${NEED[@]}"
fi
green "  OK: cmake $(cmake --version | head -1 | awk '{print $3}'), git $(git --version | awk '{print $3}')"

# uv is optional — only install if user wants it. We don't auto-install
# any optional dep to keep the script's surface area small.
if ! command -v uv >/dev/null 2>&1; then
  yellow "  Optional: 'uv' (fast Python installer) not found."
  yellow "    brew install uv     # recommended for atlas-cli install"
  yellow "    or fall back to pip — both work."
fi

# ---------------------------------------------------------------------------
# Step 4 — Pin LLAMA_CPP_REV
# ---------------------------------------------------------------------------

step "4/7" "Reading LLAMA_CPP_REV from inference/Dockerfile.v31"

LLAMA_CPP_REV=$(extract_llama_rev)
green "  Pinned SHA: $LLAMA_CPP_REV"

# Decide whether we need to (re)build. We avoid rebuilding when the
# existing binary's stored SHA matches the current pin AND --rebuild
# wasn't requested.
NEED_BUILD=1
SHA_MARKER="$LLAMA_BIN_DIR/.llama_cpp_rev"
if [[ -x "$LLAMA_SERVER" && -f "$SHA_MARKER" && $REBUILD -eq 0 ]]; then
  PREV_REV=$(cat "$SHA_MARKER")
  if [[ "$PREV_REV" == "$LLAMA_CPP_REV" ]]; then
    NEED_BUILD=0
    green "  Existing build is up-to-date (SHA matches). Skipping rebuild."
    yellow "  Pass --rebuild to force a fresh compile."
  fi
fi

# ---------------------------------------------------------------------------
# Step 5 — Fetch + patch llama.cpp at the pinned SHA
# ---------------------------------------------------------------------------

if [[ $NEED_BUILD -eq 1 ]]; then
  step "5/7" "Fetching llama.cpp at $LLAMA_CPP_REV + applying patches"

  # Clean state — easiest way to guarantee a known-good build. Cheap
  # too: shallow fetch is ~30s.
  rm -rf "$LLAMA_BUILD_DIR"
  mkdir -p "$LLAMA_BUILD_DIR"

  pushd "$LLAMA_BUILD_DIR" >/dev/null
    git init -q
    git remote add origin https://github.com/ggml-org/llama.cpp
    git -c http.postBuffer=524288000 \
        fetch --depth 1 origin "$LLAMA_CPP_REV"
    git checkout -q FETCH_HEAD

    # Apply PC-202 hidden-states patch (real .patch file, must apply
    # cleanly — CI gates on this via llama-patches-apply).
    if ! git apply --check "$PATCH_DIR/expose-hidden-states.patch"; then
      red "PC-202 patch does not apply to $LLAMA_CPP_REV."
      red "  See docs/TROUBLESHOOTING.md § 'llama.cpp patch drift' for the bump runbook."
      exit 1
    fi
    git apply "$PATCH_DIR/expose-hidden-states.patch"

    # spec-decode embeddings fix — uses sed (the .patch file is
    # malformed dead code; the sed is what actually applies, same as
    # the Dockerfiles). || true keeps re-runs idempotent if the line
    # is already present.
    sed -i.bak '/auto params_dft = params_base;/a\
        params_dft.embedding = false;  \/\/ ATLAS: draft never needs embeddings' \
        tools/server/server-context.cpp 2>/dev/null || true
    rm -f tools/server/server-context.cpp.bak

    green "  Patches applied."

  # ---------------------------------------------------------------------------
  # Step 6 — Build with Metal. GGML_METAL=ON is the Apple Silicon path;
  # llama.cpp auto-detects metal-cpp via Xcode CLT.
  # ---------------------------------------------------------------------------

  popd >/dev/null

  step "6/7" "Building llama.cpp with Metal (this is the slow step, ~5-10min)"

  pushd "$LLAMA_BUILD_DIR" >/dev/null
    # Build flags:
    #   GGML_METAL=ON               — Apple GPU compute backend
    #   GGML_METAL_USE_BF16=ON      — bf16 support on M3/M4
    #   BUILD_SHARED_LIBS=OFF       — static linking, no runtime libllama
    #   CMAKE_BUILD_TYPE=Release    — optimizations on
    cmake -B build \
      -DGGML_METAL=ON \
      -DGGML_METAL_USE_BF16=ON \
      -DBUILD_SHARED_LIBS=OFF \
      -DCMAKE_BUILD_TYPE=Release
    cmake --build build --config Release -j"$(sysctl -n hw.ncpu)"
  popd >/dev/null

  # Install binary + ASA cvector tool to the prefix.
  mkdir -p "$LLAMA_BIN_DIR"
  cp "$LLAMA_BUILD_DIR/build/bin/llama-server" "$LLAMA_SERVER"
  cp "$LLAMA_BUILD_DIR/build/bin/llama-cli" "$LLAMA_BIN_DIR/llama-cli-metal"
  cp "$LLAMA_BUILD_DIR/build/bin/llama-cvector-generator" \
     "$LLAMA_BIN_DIR/llama-cvector-generator-metal"

  echo "$LLAMA_CPP_REV" > "$SHA_MARKER"
  green "  Built and installed:"
  green "    $LLAMA_SERVER"
  green "    $LLAMA_BIN_DIR/llama-cli-metal"
  green "    $LLAMA_BIN_DIR/llama-cvector-generator-metal"
fi

# ---------------------------------------------------------------------------
# Step 7 — Install atlas CLI. Prefer uv if installed, fall back to pip.
# Both end up putting `atlas` on PATH (via the user's pip install location).
# ---------------------------------------------------------------------------

step "7/7" "Installing atlas CLI"

if command -v uv >/dev/null 2>&1; then
  (cd "$ATLAS_ROOT" && uv pip install --system -e .)
  green "  Installed via uv."
elif command -v pip3 >/dev/null 2>&1; then
  (cd "$ATLAS_ROOT" && pip3 install --user -e .)
  green "  Installed via pip3."
  yellow "  Make sure ~/.local/bin (or python's user bin dir) is on your PATH."
else
  red "neither uv nor pip3 found. Install one and re-run."
  exit 1
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

cat <<EOF

$(bold "Setup complete.")

Native llama-server: $LLAMA_SERVER
Install prefix:      $PREFIX

Next steps:
  1. atlas init                                       # wizard writes .env (picks Metal hybrid)
  2. ./scripts/atlas-llama-macos.sh                   # start native llama-server (new terminal)
  3. docker compose -f docker-compose.yml \\
                    -f docker-compose.macos.yml up -d # start proxy + v3 + lens + sandbox
  4. atlas doctor                                     # verify install health
  5. atlas                                            # start using ATLAS

If anything in steps 2-5 fails, see docs/SETUP_MACOS.md § Troubleshooting.
EOF
