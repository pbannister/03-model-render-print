// support-view.js — interactive viewer for the interior support + hemisphere tiles.
// Loads support-north.obj (grouped: the support shell + the hemisphere tiles), colors
// each piece by latitude band, and offers drag-to-rotate / scroll-to-zoom.
import * as THREE from './three.module.min.js';

const canvas = document.getElementById('support-canvas');
const statusEl = document.getElementById('support-status');
const legendEl = document.getElementById('support-legend');

const BAND_COLORS = {
  SUPPORT: 0x9aa0a6,
  S90: 0x8ecae6,
  S60: 0x219ebc,
  S30: 0x8338ec,
  N00: 0xfb8500,
  N30: 0xff006e,
  N90: 0xffb703,
};
const BAND_LABELS = {
  SUPPORT: 'support (shell)',
  S90: 'south cap (S90)',
  S60: 'band 60–30 S',
  S30: 'band 30–0 S',
  N00: 'band 0–30 N',
  N30: 'band 30–60 N',
  N90: 'north cap (N90)',
};

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0a1030);
const camera = new THREE.PerspectiveCamera(45, 1, 1, 4000);
camera.up.set(0, 0, 1);  // Earth's rotation axis is +Z
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

scene.add(new THREE.AmbientLight(0xffffff, 0.55));
const sun = new THREE.DirectionalLight(0xffffff, 0.9);
sun.position.set(250, 300, 400);
scene.add(sun);
const fill = new THREE.DirectionalLight(0x88aaff, 0.25);
fill.position.set(-300, -200, -250);
scene.add(fill);

// faint wireframe of the globe surface, so the frame's extent is clear
const globeOutline = new THREE.Mesh(
    new THREE.SphereGeometry(103, 48, 24),
    new THREE.MeshBasicMaterial({ wireframe: true, color: 0x3a6ea5,
                                  transparent: true, opacity: 0.22 }));
scene.add(globeOutline);

const view = { radius: 430, theta: 0.6, phi: 1.25 };
let dragging = false;
let lastX = 0;
let lastY = 0;

function clamp(value, low, high) {
    return Math.min(high, Math.max(low, value));
}

function bandOf(group) {
    if (group === 'SUPPORT') {
        return 'SUPPORT';
    }
    const match = group.match(/^(S90|S60|S30|N00|N30|N90)/);
    return match ? match[1] : 'SUPPORT';
}

function parseObj(text) {
    const groups = {};
    let current = null;
    let globalCount = 0;
    for (const line of text.split('\n')) {
        const trimmed = line.trim();
        if (!trimmed) {
            continue;
        }
        if (trimmed.startsWith('o ')) {
            current = trimmed.slice(2).trim();
            groups[current] = { vertices: [], indices: [], start: globalCount };
        } else if (trimmed.startsWith('v ')) {
            const parts = trimmed.slice(2).trim().split(/\s+/).map(Number);
            groups[current].vertices.push(parts[0], parts[1], parts[2]);
            globalCount += 1;
        } else if (trimmed.startsWith('f ')) {
            const [a, b, c] = trimmed.slice(2).trim().split(/\s+/)
                .map((part) => parseInt(part, 10) - 1);
            const group = groups[current];
            group.indices.push(a - group.start, b - group.start,
                               c - group.start);
        }
    }
    const geometries = {};
    for (const [name, group] of Object.entries(groups)) {
        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute('position', new THREE.Float32BufferAttribute(
            group.vertices, 3));
        geometry.setIndex(group.indices);
        geometry.computeVertexNormals();
        geometries[name] = geometry;
    }
    return geometries;
}

async function loadModel() {
    const response = await fetch('./support-north.obj');
    if (!response.ok) {
        throw new Error('frame model not found (HTTP ' + response.status + ')');
    }
    const geometries = parseObj(await response.text());
    let triangleCount = 0;
    for (const [name, geometry] of Object.entries(geometries)) {
        const color = BAND_COLORS[bandOf(name)];
        const isSupport = bandOf(name) === 'SUPPORT';
        const material = new THREE.MeshStandardMaterial({
            color,
            flatShading: true,
            metalness: 0.1,
            roughness: 0.55,
            transparent: isSupport,
            opacity: isSupport ? 0.55 : 1.0,
        });
        scene.add(new THREE.Mesh(geometry, material));
        triangleCount += geometry.index.count / 3;
    }
    statusEl.textContent = 'support loaded: ' + triangleCount + ' triangles, '
        + Object.keys(geometries).length + ' pieces';
}

function buildLegend() {
    for (const [band, label] of Object.entries(BAND_LABELS)) {
        const swatch = document.createElement('span');
        swatch.className = 'support-swatch';
        swatch.style.background = '#' + BAND_COLORS[band].toString(16)
            .padStart(6, '0');
        const entry = document.createElement('span');
        entry.className = 'support-legend-entry';
        entry.appendChild(swatch);
        entry.appendChild(document.createTextNode(label));
        legendEl.appendChild(entry);
    }
}

function resize() {
    const width = canvas.clientWidth || canvas.parentElement.clientWidth;
    const height = canvas.clientHeight || canvas.parentElement.clientHeight;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
}

function frame() {
    if (!dragging) {
        view.theta += 0.0022;
    }
    const sinPhi = Math.sin(view.phi);
    camera.position.set(
        view.radius * sinPhi * Math.cos(view.theta),
        view.radius * sinPhi * Math.sin(view.theta),
        view.radius * Math.cos(view.phi));
    camera.lookAt(0, 0, 0);
    renderer.render(scene, camera);
    requestAnimationFrame(frame);
}

canvas.addEventListener('pointerdown', (event) => {
    dragging = true;
    lastX = event.clientX;
    lastY = event.clientY;
});
window.addEventListener('pointerup', () => {
    dragging = false;
});
window.addEventListener('pointermove', (event) => {
    if (!dragging) {
        return;
    }
    view.theta -= (event.clientX - lastX) * 0.005;
    view.phi = clamp(view.phi - (event.clientY - lastY) * 0.005, 0.1,
                     Math.PI - 0.1);
    lastX = event.clientX;
    lastY = event.clientY;
});
canvas.addEventListener('wheel', (event) => {
    event.preventDefault();
    view.radius = clamp(view.radius * (1 + event.deltaY * 0.001), 130, 1400);
}, { passive: false });

window.addEventListener('resize', resize);
buildLegend();
resize();
loadModel().catch((error) => {
    statusEl.textContent = 'load failed: ' + error.message;
});
frame();
