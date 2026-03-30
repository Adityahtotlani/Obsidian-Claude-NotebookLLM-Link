#!/bin/bash
# Install the obsidian-bridge as a global 'bridge' command

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Create a launcher in /usr/local/bin
cat > /usr/local/bin/bridge << EOF
#!/bin/bash
python3 "$SCRIPT_DIR/bridge.py" "\$@"
EOF

chmod +x /usr/local/bin/bridge

echo "Installed. You can now run: bridge --help"
echo ""
echo "Next: bridge config --anthropic-key YOUR_KEY"
