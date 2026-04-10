// Decorative waveform visualizer — animated bars that oscillate while agent is thinking.

const canvas = document.getElementById('waveform');
const ctx = canvas.getContext('2d');
let animId = null;
let startTime = 0;

const BAR_COUNT = 40;
const BAR_WIDTH = 6;
const BAR_GAP = 4;
const BASE_HEIGHT = 4;
const MAX_HEIGHT = 50;
const COLOR = '#58a6ff';

function drawFrame(now) {
    const elapsed = (now - startTime) / 1000;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const totalWidth = BAR_COUNT * (BAR_WIDTH + BAR_GAP) - BAR_GAP;
    const offsetX = (canvas.width - totalWidth) / 2;

    for (let i = 0; i < BAR_COUNT; i++) {
        // Layered sine waves for organic feel
        const phase = i * 0.25;
        const wave1 = Math.sin(elapsed * 3.0 + phase) * 0.5;
        const wave2 = Math.sin(elapsed * 1.7 + phase * 0.6) * 0.3;
        const wave3 = Math.sin(elapsed * 5.0 + phase * 1.2) * 0.2;
        const combined = (wave1 + wave2 + wave3 + 1) / 2; // Normalize 0-1

        const h = BASE_HEIGHT + combined * (MAX_HEIGHT - BASE_HEIGHT);
        const x = offsetX + i * (BAR_WIDTH + BAR_GAP);
        const y = (canvas.height - h) / 2;

        ctx.fillStyle = COLOR;
        ctx.globalAlpha = 0.4 + combined * 0.6;
        ctx.beginPath();
        ctx.roundRect(x, y, BAR_WIDTH, h, 3);
        ctx.fill();
    }
    ctx.globalAlpha = 1;
    animId = requestAnimationFrame(drawFrame);
}

function startWaveform() {
    if (animId) return;
    startTime = performance.now();
    animId = requestAnimationFrame(drawFrame);
}

function stopWaveform() {
    if (animId) {
        cancelAnimationFrame(animId);
        animId = null;
    }
    ctx.clearRect(0, 0, canvas.width, canvas.height);
}
