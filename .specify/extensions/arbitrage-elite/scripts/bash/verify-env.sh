#!/usr/bin/env bash

# verify-env.sh - Checks for mandatory arbitrage-elite API keys

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Verifying Arbitrage-Elite-Python Environment...${NC}"

MANDATORY_KEYS=(
  "POLYGON_API_KEY"
  "GEMINI_API_KEY"
  "TELEGRAM_BOT_TOKEN"
  "TELEGRAM_CHAT_ID"
  "T212_API_KEY"
)

MISSING=0

for KEY in "${MANDATORY_KEYS[@]}"; do
  if [ -z "${!KEY}" ]; then
    # Try loading from .env if not in environment
    if [ -f ".env" ]; then
      VAL=$(grep "^$KEY=" .env | cut -d '=' -f2)
      if [ -z "$VAL" ]; then
        echo -e "${RED}✗ $KEY is missing${NC}"
        MISSING=$((MISSING + 1))
      else
        echo -e "${GREEN}✓ $KEY (found in .env)${NC}"
      fi
    else
      echo -e "${RED}✗ $KEY is missing and no .env file found${NC}"
      MISSING=$((MISSING + 1))
    fi
  else
    echo -e "${GREEN}✓ $KEY (found in environment)${NC}"
  fi
done

if [ $MISSING -eq 0 ]; then
  echo -e "\n${GREEN}Environment is compliant with Project Constitution Principle I.${NC}"
  exit 0
else
  echo -e "\n${RED}Environment is NOT compliant. Missing $MISSING mandatory keys.${NC}"
  exit 1
fi
