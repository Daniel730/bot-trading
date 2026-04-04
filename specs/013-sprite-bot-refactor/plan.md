# Implementation Plan: Sprite Bot Refactor

## 1. Goal
Refactor the web dashboard to use a sprite-sheet based animated 2D pixel art robot instead of the current layered SVG components.

## 2. Tech Stack
- CSS3 (Sprites, Animations, Glassmorphism)
- HTML5
- Vanilla JavaScript

## 3. Key Components
- `dashboard/style.css`: Sprite animation logic and UI refinement.
- `dashboard/index.html`: Structural change from SVG to div-based sprite container.
- `dashboard/app.js`: Update `PixelBot` class for class-based state switching.

## 4. Assets Required
- `/static/bot_spritesheet.png`
- `/static/dashboard_bg.png`
