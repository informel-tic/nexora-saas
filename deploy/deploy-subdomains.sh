#!/bin/bash
# deploy-subdomains.sh — Configure nginx vhosts for the 3-subdomain architecture
#
# Usage: ./deploy/deploy-subdomains.sh <BASE_DOMAIN> [PORT]
#
# Example:
#   ./deploy/deploy-subdomains.sh srv2testrchon.nohost.me 38120
#
# This script:
#   1. Generates nginx configs for www.*, console.*, saas.* from templates
#   2. Creates DNS records (if using YunoHost domain management)
#   3. Installs nginx configs and reloads nginx
#   4. Sets up SSL certificates for subdomains
#
# Prerequisites:
#   - Run as root on the YunoHost server
#   - Base domain already configured in YunoHost

set -euo pipefail

DOMAIN="${1:?Usage: $0 <BASE_DOMAIN> [PORT]}"
PORT="${2:-38120}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE_DIR="${SCRIPT_DIR}/templates"
NGINX_DIR="/etc/nginx/conf.d"

echo "=== Nexora subdomain deployment ==="
echo "Base domain: ${DOMAIN}"
echo "Backend port: ${PORT}"
echo ""

# Check templates exist (check both sets — we'll select later based on YunoHost detection)
for tpl in ynh-www.conf ynh-console.conf ynh-saas.conf; do
    if [ ! -f "${TEMPLATE_DIR}/${tpl}" ]; then
        echo "WARNING: YunoHost template not found: ${TEMPLATE_DIR}/${tpl}"
    fi
done
for tpl in nginx-www.conf nginx-console.conf nginx-saas.conf; do
    if [ ! -f "${TEMPLATE_DIR}/${tpl}" ]; then
        echo "WARNING: Standalone template not found: ${TEMPLATE_DIR}/${tpl}"
    fi
done

# Function to create subdomain in YunoHost
setup_subdomain() {
    local sub="$1"
    local fqdn="${sub}.${DOMAIN}"
    echo "--- Setting up ${fqdn} ---"

    # Add subdomain if not already present
    if ! yunohost domain list --output-as json 2>/dev/null | grep -q "\"${fqdn}\""; then
        echo "Adding domain: ${fqdn}"
        yunohost domain add "${fqdn}" 2>/dev/null || echo "  (domain may already exist)"
    else
        echo "  Domain ${fqdn} already exists"
    fi

    # Install SSL cert
    echo "  Requesting SSL certificate for ${fqdn}..."
    yunohost domain cert install "${fqdn}" --no-checks 2>/dev/null || echo "  (cert may already be installed)"
}

# Detect if running on YunoHost (location-only templates) or standalone (full server blocks)
if command -v yunohost >/dev/null 2>&1; then
    TPL_PREFIX="ynh"
    echo "Detected YunoHost — using location-only nginx templates (ynh-*.conf)"
else
    TPL_PREFIX="nginx"
    echo "Standalone mode — using full server-block nginx templates (nginx-*.conf)"
fi

# Function to install nginx config from template
install_nginx_config() {
    local sub="$1"
    local fqdn="${sub}.${DOMAIN}"

    if [ "${TPL_PREFIX}" = "ynh" ]; then
        # YunoHost mode: install as location blocks inside YunoHost's auto-generated server{}
        local tpl_name="${TPL_PREFIX}-${sub}.conf"
        local output_name="nexora-${sub}.conf"
        local target="${NGINX_DIR}/${fqdn}.d/${output_name}"
        echo "  Installing nginx config: ${output_name} → ${fqdn}.d/"
        mkdir -p "${NGINX_DIR}/${fqdn}.d"
        sed -e "s/__DOMAIN__/${DOMAIN}/g" \
            -e "s/__PORT__/${PORT}/g" \
            "${TEMPLATE_DIR}/${tpl_name}" > "${target}"
    else
        # Standalone mode: install full server-block as separate conf file
        local tpl_name="nginx-${sub}.conf"
        local output_name="nexora-${sub}.conf"
        local target="${NGINX_DIR}/${fqdn}.d/${output_name}"
        echo "  Installing nginx config: ${output_name} → ${fqdn}.d/"
        mkdir -p "${NGINX_DIR}/${fqdn}.d"
        sed -e "s/__DOMAIN__/${DOMAIN}/g" \
            -e "s/__PORT__/${PORT}/g" \
            "${TEMPLATE_DIR}/${tpl_name}" > "${target}"
    fi

    echo "  -> ${target}"
}

# Step 1: Create subdomains
echo ""
echo "=== Step 1: Creating subdomains in YunoHost ==="
for sub in www console saas; do
    setup_subdomain "${sub}"
done

# Step 2: Install nginx configs
echo ""
echo "=== Step 2: Installing nginx configurations ==="
install_nginx_config "www"
install_nginx_config "console"
install_nginx_config "saas"

# Step 3: Test and reload nginx
echo ""
echo "=== Step 3: Testing and reloading nginx ==="
nginx -t
systemctl reload nginx

echo ""
echo "=== Deployment complete ==="
echo ""
echo "URLs:"
echo "  Public site:        https://www.${DOMAIN}/"
echo "  Subscriber console: https://console.${DOMAIN}/"
echo "  Owner console:      https://saas.${DOMAIN}/"
echo ""
echo "Next steps:"
echo "  1. Set owner passphrase:"
echo "     curl -X POST https://saas.${DOMAIN}/api/auth/owner-passphrase \\"
echo "       -H 'Content-Type: application/json' \\"
echo "       -H 'X-Nexora-Action: setup' \\"
echo "       -H 'Origin: https://saas.${DOMAIN}' \\"
echo "       -d '{\"passphrase\": \"your-secret-passphrase\"}'"
echo ""
echo "  2. Test owner login:"
echo "     Open https://saas.${DOMAIN}/ in a browser"
echo ""
echo "  3. DNS: Ensure www, console, saas CNAME/A records point to this server"
