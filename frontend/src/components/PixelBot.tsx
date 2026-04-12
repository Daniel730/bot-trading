import React from 'react';
import { motion } from 'framer-motion';

interface PixelBotProps {
  mood: 'idle' | 'analyzing' | 'executing' | 'doubt' | 'glitch' | 'happy';
}

const PixelBot: React.FC<PixelBotProps> = ({ mood }) => {
  const faceMap = {
    idle: '/assets/face_idle.png',
    analyzing: '/assets/face_idle.png',
    executing: '/assets/face_happy.png',
    doubt: '/assets/face_doubt.png',
    glitch: '/assets/face_glitch.png',
    happy: '/assets/face_happy.png'
  };

  const currentFace = faceMap[mood] || faceMap.idle;

  return (
    <div className="pixel-bot-elite-final" style={{ 
      width: '450px', 
      height: '450px', 
      position: 'relative',
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'center',
      alignItems: 'center'
    }}>
      
      {/* SHADOW BASE */}
      <div 
        className="elite-shadow"
        style={{
          width: '120px',
          height: '20px',
          background: 'rgba(0, 242, 255, 0.25)',
          borderRadius: '50%',
          filter: 'blur(10px)',
          marginTop: '340px',
          zIndex: 0
        }}
      />

      {/* BOT ASSEMBLY */}
      <div
        className="elite-floating"
        style={{ 
            position: 'absolute', 
            width: '300px', 
            height: '300px', 
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            zIndex: 10
        }}
      >
        {/* BODY CONTAINER */}
        <div style={{ position: 'relative', width: '220px', height: '220px' }}>
            <img 
                src="/assets/body.png" 
                className="elite-breathe"
                alt="Bot Body"
                style={{ width: '100%', height: '100%' }}
            />

            {/* HEAD ASSEMBLY (Attached to body) */}
            <div
                style={{ 
                    position: 'absolute', 
                    width: '120px', // Slightly smaller for better proportions
                    height: '120px', 
                    top: '-65px',
                    left: '50px',   // Perfectly centered over 220px body
                    zIndex: 20
                }}
            >
                {/* HEAD BASE */}
                <img src="/assets/head.png" style={{ width: '100%', height: '100%' }} alt="Bot Head" />
                
                {/* FACE AREA (CONSTRAINED TO MONITOR SCREEN) */}
                <div style={{
                    position: 'absolute',
                    width: '56px',  // Exact monitor width
                    height: '36px', // Exact monitor height
                    top: '38px',    // Centered vertically in head frame
                    left: '32px',   // Centered horizontally in head frame
                    overflow: 'hidden',
                    display: 'flex',
                    justifyContent: 'center',
                    alignItems: 'center',
                    background: 'rgba(0,0,0,0.4)',
                    borderRadius: '4px'
                }}>
                    <motion.img 
                        key={mood}
                        src={currentFace} 
                        className="screen-area"
                        alt="Bot Face"
                        initial={{ opacity: 0, scale: 0.8 }}
                        animate={{ opacity: 1, scale: 1 }}
                        style={{ 
                            width: '100%', 
                            height: 'auto',
                            filter: `drop-shadow(0 0 5px ${mood === 'glitch' ? '#ff00ff' : '#00f2ff'})`,
                        }}
                    />
                </div>
            </div>

            {/* LIMB OVERLAYS (Moving parts on top of static body arms) */}
            <motion.img 
                src="/assets/arm_l.png" 
                style={{ 
                    position: 'absolute', 
                    width: '80px', 
                    height: '80px', 
                    left: '-40px', 
                    top: '70px', 
                    zIndex: 15,
                    transformOrigin: 'top right'
                }}
                animate={{ rotate: [-5, 5, -5] }}
                transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
            />
            <motion.img 
                src="/assets/arm_r.png" 
                style={{ 
                    position: 'absolute', 
                    width: '80px', 
                    height: '80px', 
                    right: '-40px', 
                    top: '70px', 
                    zIndex: 15,
                    transformOrigin: 'top left'
                }}
                animate={{ rotate: [5, -5, 5] }}
                transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
            />
        </div>
      </div>

      {/* HUD OVERLAY */}
      <div
        style={{
            marginTop: '360px',
            fontSize: '0.65rem',
            fontFamily: 'var(--font-mono)',
            color: 'var(--primary)',
            background: 'rgba(0,12,24,0.8)',
            padding: '4px 12px',
            borderRadius: '20px',
            border: '1px solid var(--primary)',
            zIndex: 30
        }}
      >
        AGENT_LINK: {mood.toUpperCase()}
      </div>
    </div>
  );
};

export default PixelBot;
