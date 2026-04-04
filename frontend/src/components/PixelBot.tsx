import React from 'react';
// @ts-ignore
import { SpriteAnimator } from 'react-sprite-animator';

interface PixelBotProps {
  mood: 'idle' | 'analyzing' | 'executing';
}

const PixelBot: React.FC<PixelBotProps> = ({ mood }) => {
  // Map mood to starting frame (each row is 4 frames)
  const moodConfig = {
    idle: { startFrame: 0, fps: 4 },
    analyzing: { startFrame: 4, fps: 6 },
    executing: { startFrame: 8, fps: 10 }
  };

  const { startFrame, fps } = moodConfig[mood];

  return (
    <div className="pixel-bot-container" style={{ 
      width: '512px', 
      height: '512px', 
      display: 'flex', 
      justifyContent: 'center', 
      alignItems: 'center',
      position: 'relative',
      overflow: 'visible'
    }}>
      <div style={{ transform: 'scale(8)', imageRendering: 'pixelated' }}>
        <SpriteAnimator
          sprite="/assets/bot_spritesheet.png"
          width={64}
          height={64}
          fps={fps}
          startFrame={startFrame}
          frameCount={4}
          wrapAfter={4}
        />
      </div>
    </div>
  );
};

export default PixelBot;
