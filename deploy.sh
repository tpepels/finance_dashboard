#!/bin/sh
# Build and deploy a distinct, monotonically versioned release.
# Call: sh finance_dashboard/deploy.sh (from ~/media-stack), or
#       sh ./deploy.sh (from the finance_dashboard checkout).
set -eu

repository=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -f "$repository/../compose.yaml" ] || [ -f "$repository/../compose.yml" ] || \
   [ -f "$repository/../docker-compose.yml" ] || [ -f "$repository/../docker-compose.yaml" ]; then
    cd "$repository/.."
else
    cd "$repository"
fi

if [ -n "${FINANCE_BUILD_NONCE:-}" ]; then
    echo "FINANCE_BUILD_NONCE is managed by deploy.sh; unset it before deployment" >&2
    exit 2
fi
nonce=$(od -An -N16 -tx1 /dev/urandom | tr -d '[:space:]')
case "$nonce" in
    ????????*)
        ;;
    *)
        echo "Failed to create unique release nonce" >&2
        exit 2
        ;;
esac

echo "Building a distinct Global Capital Monitor release..."
# Build the image first. A failed test/build must not replace the running
# container or advance the stored numeric release sequence.
docker compose build --build-arg "FINANCE_BUILD_NONCE=$nonce" finance-dashboard

# Do not invoke build a second time with an unversioned default argument.
docker compose up -d --no-build --wait --wait-timeout 120 finance-dashboard

echo "Deployed release metadata:"
docker compose exec -T finance-dashboard python -c 'import json; from finance_dashboard.runtime_release import release_info; print(json.dumps(release_info(), sort_keys=True))'
