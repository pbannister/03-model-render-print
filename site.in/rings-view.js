// rings-view.js — interactive viewer for the support ring lattice.
// Loads rings-north.obj and rings-south.obj (grouped by piece name), merges
// each piece category into one mesh so the whole lattice can be shown as a
// single solid, and offers drag-to-rotate / scroll-to-zoom.
import * as THREE from './three.module.min.js';

const canvas = document.getElementById('rings-canvas');
const statusEl = document.getElementById('rings-status');
const legendEl = document.getElementById('rings-legend');

// Categories are matched on the OBJ group name written by rings_build.py:
// ring-n00 / ring-n30 / ring-n90, meridian-01..12, and cap-stem.
const CATEGORIES = [
  { key: 'ring-equator', label: 'equatorial ring (N00 / S30)', color: 0xfb8500 },
  { key: 'ring-mid', label: 'temperate ring (N30 / S60)', color: 0xff006e },
  { key: 'ring-cap', label: 'cap ring (N90 / S90)', color: 0xffb703 },
  { key: 'meridian', label: 'meridian arcs (12)', color: 0x8ecae6 },
  { key: 'stem', label: 'cap stem + spokes', color: 0x9aa0a6 },
];
const HEMISPHERES = ['north', 'south'];

function categoryOf(group) {
  if (group === 'cap-stem') {
    return 'stem';
  }
  if (group === 'ring-n00' || group === 'ring-s30') {
    return 'ring-equator';
  }
  if (group === 'ring-n30' || group === 'ring-s60') {
    return 'ring-mid';
  }
  if (group === 'ring-n90' || group === 'ring-s90') {
    return 'ring-cap';
  }
  if (group.startsWith('meridian-')) {
    return 'meridian';
  }
  return null;
}

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

// faint wireframe of the globe surface, so the lattice's extent is clear
scene.add(new THREE.Mesh(
    new THREE.SphereGeometry(103, 48, 24),
    new THREE.MeshBasicMaterial({ wireframe: true, color: 0x3a6ea5,
                                  transparent: true, opacity: 0.22 })));

const view = { radius: 430, theta: 0.6, phi: 1.25 };
let dragging = false;
let lastX = 0;
let lastY = 0;

function clamp(value, low, high) {
    return Math.min(high, Math.max(low, value));
}

// Reads one OBJ file into { groupName: { vertices, indices } }.
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
    return groups;
}

function mergeInto(target, group) {
    const offset = target.vertices.length / 3;
    for (const value of group.vertices) {
        target.vertices.push(value);
    }
    for (const index of group.indices) {
        target.indices.push(index + offset);
    }
}

function buildMesh(category, merged) {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position',
                          new THREE.Float32BufferAttribute(merged.vertices, 3));
    geometry.setIndex(merged.indices);
    geometry.computeVertexNormals();
    const mesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({
        color: category.color,
        flatShading: true,
        metalness: 0.1,
        roughness: 0.55,
    }));
    scene.add(mesh);
    return mesh;
}

async function loadModel() {
    const merged = {};
    let files = 0;
    let pieces = 0;
    for (const hemisphere of HEMISPHERES) {
        const response = await fetch('./rings-' + hemisphere + '.obj');
        if (!response.ok) {
            continue;
        }
        files += 1;
        const groups = parseObj(await response.text());
        for (const [name, group] of Object.entries(groups)) {
            const category = categoryOf(name);
            if (category === null) {
                continue;
            }
            pieces += 1;
            if (!merged[category]) {
                merged[category] = { vertices: [], indices: [] };
            }
            mergeInto(merged[category], group);
        }
    }
    if (files === 0) {
        throw new Error('no ring model found (run make rings)');
    }
    let triangles = 0;
    for (const category of CATEGORIES) {
        if (!merged[category.key]) {
            continue;
        }
        category.mesh = buildMesh(category, merged[category.key]);
        triangles += category.mesh.geometry.index.count / 3;
    }
    statusEl.textContent = 'lattice loaded: ' + triangles + ' triangles, '
        + pieces + ' pieces, ' + files + ' hemisphere file(s)';
}

function buildLegend() {
    for (const category of CATEGORIES) {
        const entry = document.createElement('label');
        entry.className = 'rings-legend-entry';
        const box = document.createElement('input');
        box.type = 'checkbox';
        box.checked = true;
        box.addEventListener('change', () => {
            if (category.mesh) {
                category.mesh.visible = box.checked;
            }
        });
        const swatch = document.createElement('span');
        swatch.className = 'rings-swatch';
        swatch.style.background = '#'
            + category.color.toString(16).padStart(6, '0');
        entry.appendChild(box);
        entry.appendChild(swatch);
        entry.appendChild(document.createTextNode(category.label));
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
