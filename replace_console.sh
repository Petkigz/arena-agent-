#!/bin/bash

# Files to process
FILES=(
  "components/ui/ErrorBoundary.tsx"
  "components/ui/ScreenCapture.tsx"
  "components/ui/WakeWordTrainer.tsx"
  "components/onboarding/steps/PermissionRequests.tsx"
  "hooks/useVoice.ts"
  "services/websocket.ts"
  "services/api.ts"
  "services/conversationExport.ts"
  "stores/privacySettingsStore.ts"
)

cd /home/user/arena-agent-/frontend/src

for file in "${FILES[@]}"; do
  echo "Processing $file..."
  
  # Add logger import if not present
  if ! grep -q "import { logger }" "$file"; then
    # Check if file already has imports
    if grep -q "^import " "$file"; then
      # Add after first import
      sed -i "0,/^import /s/^import /import { logger } from '..\/services\/logger';\nimport /" "$file"
    else
      # Add at top
      sed -i "1i import { logger } from '../services/logger';" "$file"
    fi
  fi
  
  # Replace console.error with logger.error
  sed -i "s/console\.error(/logger.error(/g" "$file"
  
  # Replace console.warn with logger.warn
  sed -i "s/console\.warn(/logger.warn(/g" "$file"
  
  # Replace console.log with logger.info
  sed -i "s/console\.log(/logger.info(/g" "$file"
  
  # Replace console.debug with logger.debug
  sed -i "s/console\.debug(/logger.debug(/g" "$file"
  
  echo "  ✓ Done"
done

echo "All files processed!"
