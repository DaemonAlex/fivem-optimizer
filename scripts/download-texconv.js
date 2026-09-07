/**
 * Downloads texconv.exe (Microsoft DirectXTex, MIT) into python/tools/ so Windows builds can
 * resample textures that ship without mipmaps. Run: node scripts/download-texconv.js
 * Skipped silently if the file already exists. Delete python/tools/texconv.exe to re-download.
 */
const https = require('https');
const fs = require('fs');
const path = require('path');

const URL = 'https://github.com/microsoft/DirectXTex/releases/latest/download/texconv.exe';
const OUT_DIR = path.join(__dirname, '..', 'python', 'tools');
const OUT = path.join(OUT_DIR, 'texconv.exe');

function download(url, dest, hops = 0) {
  return new Promise((resolve, reject) => {
    if (hops > 5) return reject(new Error('too many redirects'));
    https.get(url, { headers: { 'User-Agent': 'fivem-optimizer' } }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        res.resume();
        return resolve(download(res.headers.location, dest, hops + 1));
      }
      if (res.statusCode !== 200) return reject(new Error(`HTTP ${res.statusCode}`));
      const file = fs.createWriteStream(dest);
      res.pipe(file);
      file.on('finish', () => file.close(resolve));
      file.on('error', reject);
    }).on('error', reject);
  });
}

async function main() {
  if (fs.existsSync(OUT)) {
    console.log(`texconv.exe already present at ${OUT}`);
    return;
  }
  fs.mkdirSync(OUT_DIR, { recursive: true });
  console.log(`Downloading ${URL} ...`);
  await download(URL, OUT);
  const size = fs.statSync(OUT).size;
  if (size < 100000) {
    fs.unlinkSync(OUT);
    throw new Error(`download looks wrong (${size} bytes)`);
  }
  console.log(`texconv.exe ready (${(size / 1024 / 1024).toFixed(1)} MB)`);
}

main().catch((err) => {
  console.error('Failed to download texconv:', err.message);
  process.exit(1);
});
