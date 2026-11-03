#!/bin/bash
# Install age 1.3+ (post-quantum ML-KEM-768 + X25519 keys) into /usr/local/bin.
set -e
AGE_VERSION="${AGE_VERSION:-v1.3.2}"
if /usr/local/bin/age-keygen --help 2>&1 | grep -q -- '-pq'; then
  echo "age with post-quantum keys is already installed"
  exit 0
fi
command -v go >/dev/null || apt-get install -y golang-go
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
GOPATH="$work/go" GOCACHE="$work/cache" GOBIN=/usr/local/bin GOTOOLCHAIN=auto \
  go install "filippo.io/age/cmd/age@$AGE_VERSION" "filippo.io/age/cmd/age-keygen@$AGE_VERSION"
/usr/local/bin/age-keygen --help 2>&1 | grep -q -- '-pq'
echo "Installed $(/usr/local/bin/age --version)"
