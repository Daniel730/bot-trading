# Tasks: Sprite Bot Refactor

## Phase 1: Sprite Animation Setup
- [X] T001 Update `dashboard/style.css` to replace SVG logic with `.bot-sprite` CSS animation.
- [X] T002 Implement states: `.state-idle`, `.state-analyzing`, `.state-executing` using `steps()` on sprite sheet `/static/bot_spritesheet.png`.

## Phase 2: HTML Structure Refactor
- [X] T003 Remove `<svg class="robot-svg-assembly">` and its children from `dashboard/index.html`.
- [X] T004 Replace with `<div id="pixel-bot" class="bot-sprite state-idle"></div>`.

## Phase 3: JavaScript State Controller
- [X] T005 Update `PixelBot` class in `dashboard/app.js` to toggle CSS classes on `#pixel-bot` for mood switching.

## Phase 4: UI Refinement
- [X] T006 Update `dashboard/style.css` with new background image `/static/dashboard_bg.png`.
- [X] T007 Enhance glassmorphism for `.side-panel` and `.bottom-hud`.
- [X] T008 Verify text contrast for `--text-main` and `--text-muted`.
