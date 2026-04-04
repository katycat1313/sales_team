#!/bin/bash
# Run this once on the G14 in WSL2
# Sets up the entire agent team folder structure

echo "🤖 Setting up Agent Team..."

mkdir -p agent_team/{orchestrator/{agents,memory,logs,tools},telegram_bot,dashboard}

# Copy your brief into memory
cp katy_brief.md agent_team/orchestrator/memory/ 2>/dev/null || echo "⚠️  Copy katy_brief.md into agent_team/orchestrator/memory/ manually"

echo "✅ Folders created"
echo ""
echo "Next: cd agent_team && cp .env.example .env then fill in your keys"
