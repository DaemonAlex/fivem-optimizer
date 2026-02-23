/**
 * Generates a placeholder app icon (256x256 PNG) for FiveM Optimizer.
 * Uses a simple approach: creates an SVG and converts via sharp or canvas.
 *
 * If neither sharp nor canvas is available, creates the SVG file directly
 * and you can convert it manually (e.g., at https://convertio.co/svg-png/).
 *
 * Run: node scripts/generate-icon.js
 */
const fs = require('fs');
const path = require('path');

const ASSETS_DIR = path.join(__dirname, '..', 'assets');

// FiveM Optimizer icon: a stylized gauge/speedometer with "FO" text
const SVG_ICON = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#6c5ce7"/>
      <stop offset="100%" style="stop-color:#8b5cf6"/>
    </linearGradient>
    <linearGradient id="gauge" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" style="stop-color:#4ade80"/>
      <stop offset="50%" style="stop-color:#ffb347"/>
      <stop offset="100%" style="stop-color:#ff4d6a"/>
    </linearGradient>
  </defs>
  <!-- Rounded square background -->
  <rect width="256" height="256" rx="48" ry="48" fill="url(#bg)"/>
  <!-- Gauge arc background -->
  <circle cx="128" cy="140" r="70" fill="none" stroke="rgba(255,255,255,0.15)" stroke-width="12"
    stroke-dasharray="220 220" stroke-dashoffset="-110" stroke-linecap="round"/>
  <!-- Gauge arc colored -->
  <circle cx="128" cy="140" r="70" fill="none" stroke="url(#gauge)" stroke-width="12"
    stroke-dasharray="165 220" stroke-dashoffset="-110" stroke-linecap="round"/>
  <!-- Gauge needle -->
  <line x1="128" y1="140" x2="88" y2="100" stroke="white" stroke-width="4" stroke-linecap="round"/>
  <circle cx="128" cy="140" r="8" fill="white"/>
  <!-- Speed lines -->
  <line x1="56" y1="140" x2="66" y2="140" stroke="rgba(255,255,255,0.4)" stroke-width="2" stroke-linecap="round"/>
  <line x1="72" y1="84" x2="79" y2="90" stroke="rgba(255,255,255,0.4)" stroke-width="2" stroke-linecap="round"/>
  <line x1="128" y1="68" x2="128" y2="78" stroke="rgba(255,255,255,0.4)" stroke-width="2" stroke-linecap="round"/>
  <line x1="184" y1="84" x2="177" y2="90" stroke="rgba(255,255,255,0.4)" stroke-width="2" stroke-linecap="round"/>
  <line x1="200" y1="140" x2="190" y2="140" stroke="rgba(255,255,255,0.4)" stroke-width="2" stroke-linecap="round"/>
  <!-- "FO" text -->
  <text x="128" y="54" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-weight="800"
    font-size="30" fill="white" letter-spacing="2">FO</text>
  <!-- "OPTIMIZER" subtitle -->
  <text x="128" y="220" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-weight="600"
    font-size="14" fill="rgba(255,255,255,0.7)" letter-spacing="3">OPTIMIZER</text>
</svg>`;

// Ensure assets dir exists
if (!fs.existsSync(ASSETS_DIR)) {
  fs.mkdirSync(ASSETS_DIR, { recursive: true });
}

// Write SVG
const svgPath = path.join(ASSETS_DIR, 'icon.svg');
fs.writeFileSync(svgPath, SVG_ICON);
console.log(`Created: ${svgPath}`);

// Try to convert to PNG using sharp (if available)
async function tryConvert() {
  try {
    const sharp = require('sharp');

    // Generate multiple sizes
    const sizes = [256, 128, 64, 48, 32, 16];

    // Main icon PNG
    await sharp(Buffer.from(SVG_ICON))
      .resize(256, 256)
      .png()
      .toFile(path.join(ASSETS_DIR, 'icon.png'));
    console.log('Created: assets/icon.png (256x256)');

    // Generate ICO-compatible sizes
    for (const size of sizes) {
      await sharp(Buffer.from(SVG_ICON))
        .resize(size, size)
        .png()
        .toFile(path.join(ASSETS_DIR, `icon-${size}.png`));
    }
    console.log('Created: icon-{16,32,48,64,128,256}.png');

    console.log('\nTo create .ico file, use: https://icoconvert.com/ or similar tool');
    console.log('Upload icon-256.png and select all sizes.');

  } catch (e) {
    console.log('\nNote: sharp not installed. SVG created but PNG conversion skipped.');
    console.log('To convert manually:');
    console.log('  1. Open assets/icon.svg in a browser');
    console.log('  2. Screenshot or use https://convertio.co/svg-png/');
    console.log('  3. Save as assets/icon.png (256x256)');
    console.log('  4. Convert PNG to ICO at https://icoconvert.com/');
    console.log('\nOr install sharp: npm install --save-dev sharp');
  }
}

tryConvert();
