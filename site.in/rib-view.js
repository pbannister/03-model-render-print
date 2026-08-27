// rib-view.js — interactive viewer for the rib + first-row assembly plan.
// Loads rib-firstrow.obj (grouped: two reinforcing ribs, the equator ring,
// and the first-row tiles of each hemisphere), colors each piece by role,
// and offers drag-to-rotate / scroll-to-zoom.  Tiles render semi-transparent
// so the rib can be seen pressing against their inner faces.
import * as THREE from './three.module.min.js';

const canvas = document.getElementById('rib-canvas');
const statusEl = document.getElementById('rib-status');
const legendEl = document.getElementById('rib-legend');

const STYLE = {
  'rib-north': { color: 0xff4d4d, opaque: true, label: 'north rib (just above the equator)' },
  'rib-south': { color: 0x4da6ff, opaque: true, label: 'south rib (just below the equator)' },
  equator:     { color: 0x8b95a5, opaque: true, label: 'equator reference ring' },
  N00:         { color: 0xffca3a, opaque: false, label: 'first row north (N00, 0–30°N)' },
  S30:         { color: 0x2ec4b6, opaque: false, label: 'first row south (S30, 30°S–0)' },
};

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0a1030);
const camera = new THREE.PerspectiveCamera(45, 1, 1, 4000);
camera.up.set(0, 0, 1);  // Earth's rotation axis is +Z
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

scene.add(new THREE.AmbientLight(0xffffff, 0.6));
const sun = new THREE.DirectionalLight(0xffffff, 0.95);
sun.position.set(250, 300, 400);
scene.add(sun);
const fill = new THREE.DirectionalLight(0x88aaff, 0.3);
fill.position.set(-300, -200, -250);
scene.add(fill);

// faint wireframe of the globe surface, so the assembly's extent is clear
const globeOutline = new THREE.Mesh(
    new THREE.SphereGeometry(103, 48, 24),
    new THREE.MeshBasicMaterial({ wireframe: true, color: 0x3a6ea5,
                                  transparent: true, opacity: 0.2 }));
scene.add(globeOutline);

const view = { radius: 430, theta: 0.6, phi: 1.25 };
let dragging = false;
let lastX = 0;
let lastY = 0;

function clamp(value, low, high) {
    return Math.min(high, Math.max(low, value));
}

function roleOf(group) {
    if (group.startsWith('rib-north')) return 'rib-north';
    if (group.startsWith('rib-south')) return 'rib-south';
    if (group.startsWith('equator')) return 'equator';
    if (group.startsWith('tile-N00')) return 'N00';
    if (group.startsWith('tile-S30')) return 'S30';
    return 'equator';
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
    const response = await fetch('./rib-firstrow.obj');
    if (!response.ok) {
        throw new Error('rib model not found (HTTP ' + response.status + ')');
    }
    const geometries = parseObj(await response.text());
    let triangleCount = 0;
    for (const [name, geometry] of Object.entries(geometries)) {
        const style = STYLE[roleOf(name)];
        const material = new THREE.MeshStandardMaterial({
            color: style.color,
            flatShading: true,
            metalness: 0.1,
            roughness: 0.55,
            transparent: !style.opaque,
            opacity: style.opaque ? 1.0 : 0.55,
            depthWrite: style.opaque,
        });
        scene.add(new THREE.Mesh(geometry, material));
        triangleCount += geometry.index.count / 3;
    }
    statusEl.textContent = 'rib + first row loaded: ' + triangleCount
        + ' triangles, ' + Object.keys(geometries).length + ' pieces';
}

function buildLegend() {
    for (const [role, style] of Object.entries(STYLE)) {
        const swatch = document.createElement('span');
        swatch.className = 'rib-swatch';
        swatch.style.background = '#' + style.color.toString(16)
            .padStart(6, '0');
        swatch.style.opacity = style.opaque ? '1' : '0.55';
        const entry = document.createElement('span');
        entry.className = 'rib-legend-entry';
        entry.appendChild(swatch);
        entry.appendChild(document.createTextNode(style.label));
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
