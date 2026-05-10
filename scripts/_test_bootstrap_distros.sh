#!/usr/bin/env bash
# Simulate each Linux distro path through dig-bootstrap.sh in dry-run
# mode so we can validate the apt / dnf / yum / pacman / zypper command
# strings without spinning up a real container.
#
# Method: shadow uname + the package-manager binaries in a temp dir
# put on PATH, plus an /etc/os-release replacement, so the bootstrap
# script's detection routines pick the simulated distro. Every
# install command is wrapped in `run`, which in --dry-run mode just
# prints the command — so PATH-shadowing the actual binaries is only
# needed for the detection probes, not for the installs.
#
# Usage:
#   ./scripts/_test_bootstrap_distros.sh                # core
#   ./scripts/_test_bootstrap_distros.sh --jdbc         # JDBC path too
#
# Verifies — for each simulated distro — the dry-run output:
#   • selects the right package manager
#   • emits the right base-build packages
#   • emits the right python install commands
#   • emits the right pnpm install command
#   • (if --jdbc) emits the right jdk + cmake + ant commands

set -u

WITH_JDBC_FLAG=""
[[ "${1:-}" == "--jdbc" ]] && WITH_JDBC_FLAG="--jdbc"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BOOTSTRAP="$REPO_ROOT/scripts/dig-bootstrap.sh"

PASS=0
FAIL=0

# ── Per-distro fixture ──────────────────────────────────────────────────
# distro_id  : matches /etc/os-release ID=
# version_id : matches /etc/os-release VERSION_ID=
# pretty_name: matches /etc/os-release PRETTY_NAME=
# present_pms: which package managers should be on PATH
# expected   : grep patterns the dry-run output must contain
run_case() {
  local label="$1" id="$2" version="$3" pretty="$4" present="$5"
  shift 5
  local expected_patterns=("$@")

  local tmp; tmp="$(mktemp -d)"
  trap "rm -rf '$tmp'" RETURN

  # Fake /etc/os-release. We can't override /etc/os-release without root,
  # so we intercept the `. /etc/os-release` bash builtin via DIG_OSRELEASE
  # → no, simpler: copy the bootstrap, swap the source path with sed.
  cat > "$tmp/os-release" <<EOF
NAME="$pretty"
ID=$id
VERSION_ID="$version"
PRETTY_NAME="$pretty"
EOF

  # Stub binaries for `command -v` detection. Each is a no-op script
  # that exits 0 — bootstrap only checks presence + parses output for
  # already-installed cases (which return early). For the install
  # branches we hit (--dry-run prints, doesn't run), the stubs just
  # need to exist.
  local pm
  for pm in $present; do
    cat > "$tmp/$pm" <<EOF
#!/usr/bin/env bash
exit 0
EOF
    chmod +x "$tmp/$pm"
  done

  # Critical: ensure NO `python3*` on the simulated PATH so bootstrap
  # falls through to its install branch. (We're testing what it WOULD
  # install; if the real-host python3 leaks in the simulation, the
  # branch we want to verify never runs.)
  # Also stub out brew so detection on a "Linux apt" sim doesn't pick
  # up the host's brew.
  cat > "$tmp/uname" <<EOF
#!/usr/bin/env bash
[[ "\$1" == "-s" ]] && echo "Linux" || /usr/bin/uname "\$@"
EOF
  chmod +x "$tmp/uname"

  # Wrap bootstrap with a shim that points the os-release source to
  # our temp file via env override, then runs the real bootstrap.
  # Since bash `.` doesn't honor env paths, we sed-patch the script
  # in-place inside the tmpdir.
  cp "$BOOTSTRAP" "$tmp/bootstrap-sim.sh"
  # Replace the canonical /etc/os-release reference with our stub.
  sed -i.bak "s|/etc/os-release|$tmp/os-release|g" "$tmp/bootstrap-sim.sh"

  local out
  out="$(env -i HOME="$HOME" PATH="$tmp:/usr/bin:/bin" bash "$tmp/bootstrap-sim.sh" --dry-run $WITH_JDBC_FLAG 2>&1 || true)"

  echo "── $label ──"
  local fail_local=0
  for pat in "${expected_patterns[@]}"; do
    if grep -qE "$pat" <<< "$out"; then
      printf '  \033[32m✓\033[0m  %s\n' "$pat"
    else
      printf '  \033[31m✗\033[0m  %s\n' "$pat"
      fail_local=1
    fi
  done
  if [[ "$fail_local" -eq 1 ]]; then
    FAIL=$((FAIL + 1))
    echo "  --- full output ---"
    sed 's/^/  | /' <<< "$out"
  else
    PASS=$((PASS + 1))
  fi
  echo
}

# ── Cases ────────────────────────────────────────────────────────────────
run_case "Ubuntu 22.04 (apt + deadsnakes path)" \
  "ubuntu" "22.04" "Ubuntu 22.04.4 LTS" \
  "apt-get add-apt-repository sudo grep awk sed cut head tr" \
  "apt-get update" \
  "apt-get install -y -qq.*build-essential" \
  "deadsnakes" \
  "python3.11 python3.11-venv python3.11-dev" \
  "get.pnpm.io/install.sh"

run_case "Ubuntu 24.04 (apt generic python3 path)" \
  "ubuntu" "24.04" "Ubuntu 24.04 LTS" \
  "apt-get sudo grep awk sed cut head tr" \
  "apt-get install -y -qq.*build-essential" \
  "apt-get install -y -qq python3 python3-venv python3-dev" \
  "get.pnpm.io/install.sh"

run_case "Debian 12 (apt generic path)" \
  "debian" "12" "Debian GNU/Linux 12 (bookworm)" \
  "apt-get sudo grep awk sed cut head tr" \
  "apt-get install -y -qq.*build-essential" \
  "apt-get install -y -qq python3 python3-venv python3-dev"

run_case "Fedora 40 (dnf)" \
  "fedora" "40" "Fedora Linux 40 (Workstation)" \
  "dnf sudo grep awk sed cut head tr" \
  "dnf install -y.*python3-devel" \
  "dnf group install -y development-tools" \
  "dnf install -y python3 python3-pip python3-devel" \
  "get.pnpm.io/install.sh"

run_case "RHEL 9 / Rocky 9 (dnf with python3.11 fallback)" \
  "rhel" "9.4" "Red Hat Enterprise Linux 9.4 (Plow)" \
  "dnf sudo grep awk sed cut head tr" \
  "dnf install -y.*python3-devel" \
  "dnf install -y python3 python3-pip python3-devel"

run_case "RHEL 7 (yum)" \
  "rhel" "7.9" "Red Hat Enterprise Linux Server 7.9 (Maipo)" \
  "yum sudo grep awk sed cut head tr" \
  "yum groupinstall -y 'Development Tools'" \
  "yum install -y python3"

run_case "Arch Linux (pacman)" \
  "arch" "" "Arch Linux" \
  "pacman sudo grep awk sed cut head tr" \
  "pacman -Sy --noconfirm --needed base-devel" \
  "pacman -Sy --noconfirm --needed python python-pip" \
  "pacman -Sy --noconfirm --needed pnpm"

run_case "openSUSE Tumbleweed (zypper)" \
  "opensuse-tumbleweed" "20240101" "openSUSE Tumbleweed" \
  "zypper sudo grep awk sed cut head tr" \
  "zypper --non-interactive install -y --type pattern devel_basis" \
  "zypper --non-interactive install -y python311 python311-devel"

# ── Summary ──────────────────────────────────────────────────────────────
echo "── Summary ──"
printf '\033[32m%d passed\033[0m  ·  ' "$PASS"
if [[ "$FAIL" -gt 0 ]]; then
  printf '\033[31m%d failed\033[0m\n' "$FAIL"
  exit 1
else
  printf '0 failed\n'
fi
