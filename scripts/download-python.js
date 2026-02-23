/**
 * Downloads Python embeddable package for bundling with the app.
 * Run: node scripts/download-python.js
 *
 * Downloads the Python 3.11 embeddable zip for Windows x64,
 * extracts it to python-embed/, ready for electron-builder to bundle.
 */
const https = require('https');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const PYTHON_VERSION = '3.11.9';
const PYTHON_URL = `https://www.python.org/ftp/python/${PYTHON_VERSION}/python-${PYTHON_VERSION}-embed-amd64.zip`;
const OUTPUT_DIR = path.join(__dirname, '..', 'python-embed');
const ZIP_PATH = path.join(__dirname, '..', 'python-embed.zip');

function download(url, dest) {
  return new Promise((resolve, reject) => {
    console.log(`Downloading ${url}...`);
    const file = fs.createWriteStream(dest);

    const request = (reqUrl) => {
      https.get(reqUrl, (res) => {
        // Follow redirects
        if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
          console.log(`Redirecting to ${res.headers.location}`);
          request(res.headers.location);
          return;
        }
        if (res.statusCode !== 200) {
          reject(new Error(`HTTP ${res.statusCode}`));
          return;
        }

        const total = parseInt(res.headers['content-length'], 10) || 0;
        let downloaded = 0;

        res.on('data', (chunk) => {
          downloaded += chunk.length;
          if (total > 0) {
            const pct = Math.round((downloaded / total) * 100);
            process.stdout.write(`\r  ${pct}% (${(downloaded / 1024 / 1024).toFixed(1)} MB)`);
          }
        });

        res.pipe(file);
        file.on('finish', () => {
          file.close();
          console.log('\n  Download complete.');
          resolve();
        });
      }).on('error', (err) => {
        fs.unlinkSync(dest);
        reject(err);
      });
    };

    request(url);
  });
}

async function main() {
  // Check if already downloaded
  if (fs.existsSync(path.join(OUTPUT_DIR, 'python.exe'))) {
    console.log('Python embeddable already exists at python-embed/. Skipping download.');
    console.log('Delete python-embed/ to re-download.');
    return;
  }

  // Download
  await download(PYTHON_URL, ZIP_PATH);

  // Extract using PowerShell (available on all modern Windows)
  console.log('Extracting...');
  if (fs.existsSync(OUTPUT_DIR)) {
    fs.rmSync(OUTPUT_DIR, { recursive: true });
  }
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });

  execSync(
    `powershell -Command "Expand-Archive -Path '${ZIP_PATH}' -DestinationPath '${OUTPUT_DIR}' -Force"`,
    { stdio: 'inherit' }
  );

  // Clean up zip
  fs.unlinkSync(ZIP_PATH);

  // Verify
  const pythonExe = path.join(OUTPUT_DIR, 'python.exe');
  if (fs.existsSync(pythonExe)) {
    console.log(`\nPython embeddable ready at: ${OUTPUT_DIR}`);
    console.log(`Python exe: ${pythonExe}`);

    // Quick version check
    try {
      const version = execSync(`"${pythonExe}" --version`, { encoding: 'utf-8' }).trim();
      console.log(`Version: ${version}`);
    } catch {
      console.log('(Could not verify version)');
    }
  } else {
    console.error('ERROR: python.exe not found after extraction!');
    process.exit(1);
  }
}

main().catch((err) => {
  console.error('Failed to download Python:', err.message);
  process.exit(1);
});
