#!/bin/sh
set -eu

: "${API_BASE_URL:?API_BASE_URL must be set to the public backend URL}"
escaped_url=$(printf '%s' "$API_BASE_URL" | sed 's/[&|\\]/\\&/g')
sed -i "s|__API_BASE_URL__|$escaped_url|g" /usr/share/nginx/html/config.js
