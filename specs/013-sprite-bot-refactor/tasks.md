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

## Phase 5: React Frontend Fixes
- [X] T009 Slow down animation durations in `frontend/src/components/PixelBot.tsx` for a smoother look.
- [X] T010 Remove thought-bubble (subtitles) from `frontend/src/App.tsx` and `frontend/src/App.css` to declutter UI.

## Phase 6: React Sprite Animator Integration
- [X] T011 Install `react-sprite-animator` in the `frontend` project.
- [X] T012 Refactor `frontend/src/components/PixelBot.tsx` to use the `react-sprite-animator` component.
- [X] T013 Verify animation states (idle, analyzing, executing) transition smoothly in the UI.
