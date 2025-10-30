#!/bin/bash
# Setup script to create .env file for GitLab API token
# 
# IMPORTANT: The .env file is gitignored and will NOT be committed to the repository.
# Keep your token secure and never commit it to version control.

echo "GitLab API Token Setup"
echo "======================"
echo ""
echo "⚠️  SECURITY NOTE:"
echo "   - Your token will be stored in a .env file"
echo "   - The .env file is gitignored and will NOT be published"
echo "   - Never commit .env files to the repository"
echo "   - Keep your token secure and private"
echo ""
echo "You need a GitLab Personal Access Token."
echo "Create one at: https://gitlab.com/-/user_settings/personal_access_tokens"
echo ""
read -p "Enter your GitLab token (glpat-...): " GITLAB_TOKEN

if [ -z "$GITLAB_TOKEN" ]; then
    echo "Error: Token cannot be empty"
    exit 1
fi

# Create .env file in the tools directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"

cat > "${ENV_FILE}" << EOF
# GitLab Configuration
# WARNING: This file contains sensitive information and is gitignored
# DO NOT commit this file to version control

GITLAB_TOKEN=${GITLAB_TOKEN}

# Optional: Uncomment and set if needed
# GITLAB_URL=https://gitlab.com
# GITLAB_PR_URL=https://gitlab.com/group/project/-/merge_requests/123
EOF

echo ""
echo "✓ Created .env file with your token at: ${ENV_FILE}"
echo ""
echo "🔒 Security reminder:"
echo "   - Your .env file is gitignored (will not be published)"
echo "   - Extracted data files in tools/data/ are also gitignored"
echo "   - Never share your GitLab token publicly"
echo ""
echo "To use it, run:"
echo "  cd ${SCRIPT_DIR}"
echo "  source .env  # or export GITLAB_TOKEN=\${GITLAB_TOKEN}"
echo "  python extract_pr_data.py <pr_url>"
echo ""
echo "Or use the .env file automatically with python-dotenv (installed via requirements.txt)"
