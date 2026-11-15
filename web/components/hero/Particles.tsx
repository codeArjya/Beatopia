"use client";

import { useFrame } from "@react-three/fiber";
import { useMemo, useRef, type RefObject } from "react";
import * as THREE from "three";

import { HERO, type HeroRig } from "./config";
import { DIM, seededRandom } from "./parts/dims";

/** Render layer for things the contact shadow must ignore (particles, backdrop). */
export const FX_LAYER = 1;

/** Number of gaps between the six layers. */
export const GAPS = 5;

const vertexShader = /* glsl */ `
  uniform float uTime;
  uniform float uSpread;
  uniform float uBurst;
  uniform float uSize;
  uniform float uPx;
  uniform float uReach;
  uniform float uCurlStrength;
  uniform float uCurlScale;
  uniform float uCurlSpeed;
  uniform float uOpacity;
  uniform float uGapY[${GAPS}];

  attribute vec3 aHome;
  attribute vec3 aDir;
  attribute vec4 aSeed; // x: delay, y: travel, z: size, w: gap index (-1 = ambient dust)
  attribute vec3 aColor;

  varying vec3 vColor;
  varying float vAlpha;

  // Simplex noise by Ian McEwan and Stefan Gustavson (Ashima Arts), MIT license.
  vec4 permute(vec4 x) { return mod(((x * 34.0) + 1.0) * x, 289.0); }
  vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }
  float snoise(vec3 v) {
    const vec2 C = vec2(1.0 / 6.0, 1.0 / 3.0);
    const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
    vec3 i = floor(v + dot(v, C.yyy));
    vec3 x0 = v - i + dot(i, C.xxx);
    vec3 g = step(x0.yzx, x0.xyz);
    vec3 l = 1.0 - g;
    vec3 i1 = min(g.xyz, l.zxy);
    vec3 i2 = max(g.xyz, l.zxy);
    vec3 x1 = x0 - i1 + C.xxx;
    vec3 x2 = x0 - i2 + C.yyy;
    vec3 x3 = x0 - D.yyy;
    i = mod(i, 289.0);
    vec4 p = permute(permute(permute(i.z + vec4(0.0, i1.z, i2.z, 1.0)) + i.y + vec4(0.0, i1.y, i2.y, 1.0)) + i.x + vec4(0.0, i1.x, i2.x, 1.0));
    float n_ = 1.0 / 7.0;
    vec3 ns = n_ * D.wyz - D.xzx;
    vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
    vec4 x_ = floor(j * ns.z);
    vec4 y_ = floor(j - 7.0 * x_);
    vec4 x = x_ * ns.x + ns.yyyy;
    vec4 y = y_ * ns.x + ns.yyyy;
    vec4 h = 1.0 - abs(x) - abs(y);
    vec4 b0 = vec4(x.xy, y.xy);
    vec4 b1 = vec4(x.zw, y.zw);
    vec4 s0 = floor(b0) * 2.0 + 1.0;
    vec4 s1 = floor(b1) * 2.0 + 1.0;
    vec4 sh = -step(h, vec4(0.0));
    vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
    vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;
    vec3 p0 = vec3(a0.xy, h.x);
    vec3 p1 = vec3(a0.zw, h.y);
    vec3 p2 = vec3(a1.xy, h.z);
    vec3 p3 = vec3(a1.zw, h.w);
    vec4 norm = taylorInvSqrt(vec4(dot(p0, p0), dot(p1, p1), dot(p2, p2), dot(p3, p3)));
    p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
    vec4 m = max(0.6 - vec4(dot(x0, x0), dot(x1, x1), dot(x2, x2), dot(x3, x3)), 0.0);
    m = m * m;
    return 42.0 * dot(m * m, vec4(dot(p0, x0), dot(p1, x1), dot(p2, x2), dot(p3, x3)));
  }

  vec3 noise3(vec3 p) {
    return vec3(
      snoise(p),
      snoise(vec3(p.y - 19.1, p.z + 33.4, p.x + 47.2)),
      snoise(vec3(p.z + 74.2, p.x - 124.5, p.y + 99.4))
    );
  }

  // Curl of a noise field: a flow with no sources or sinks, so particles swirl instead of bunching up.
  vec3 curl(vec3 p) {
    const float e = 0.1;
    vec3 dx = vec3(e, 0.0, 0.0);
    vec3 dy = vec3(0.0, e, 0.0);
    vec3 dz = vec3(0.0, 0.0, e);
    vec3 x0 = noise3(p - dx), x1 = noise3(p + dx);
    vec3 y0 = noise3(p - dy), y1 = noise3(p + dy);
    vec3 z0 = noise3(p - dz), z1 = noise3(p + dz);
    return vec3(
      (y1.z - y0.z) - (z1.y - z0.y),
      (z1.x - z0.x) - (x1.z - x0.z),
      (x1.y - x0.y) - (y1.x - y0.x)
    ) / (2.0 * e);
  }

  void main() {
    vec3 p;
    float alpha;
    float drift = uTime * uCurlSpeed;

    if (aSeed.w < -0.5) {
      // Ambient dust: always there, drifting slowly around the room.
      p = aHome + curl(aHome * uCurlScale * 0.55 + vec3(aSeed.x * 9.0, drift, 0.0)) * 0.55;
      alpha = 0.22 + 0.4 * aSeed.y;
    } else {
      // Seam particles: hidden in a gap until uSpread releases them, each after its own delay.
      float delay = aSeed.x * 0.55;
      float t = clamp((uSpread - delay) / (1.0 - delay), 0.0, 1.0);
      float eased = 1.0 - pow(1.0 - t, 3.0);
      vec3 home = vec3(aHome.x, uGapY[int(aSeed.w + 0.5)] + aHome.y, aHome.z);
      p = home + aDir * (uReach * aSeed.y * eased);
      vec3 flow = curl(p * uCurlScale + vec3(aSeed.x * 7.0, drift, aSeed.y * 3.0));
      p += flow * uCurlStrength * eased * (0.55 + 0.9 * uBurst) * 0.4;
      alpha = smoothstep(0.0, 0.14, t) * (0.55 + 0.7 * uBurst);
    }

    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mv;
    gl_PointSize = uSize * aSeed.z * (1.0 + 0.35 * uBurst) * uPx / -mv.z;
    vColor = aColor;
    vAlpha = alpha * uOpacity;
  }
`;

const fragmentShader = /* glsl */ `
  varying vec3 vColor;
  varying float vAlpha;
  void main() {
    float d = length(gl_PointCoord - 0.5);
    float soft = smoothstep(0.5, 0.0, d);
    gl_FragColor = vec4(vColor * soft * soft * vAlpha, 1.0);
  }
`;

function buildGeometry(): THREE.BufferGeometry {
  const { count, violetShare, ambientShare } = HERO.particles;
  const random = seededRandom(20);
  const home = new Float32Array(count * 3);
  const dir = new Float32Array(count * 3);
  const seed = new Float32Array(count * 4);
  const color = new Float32Array(count * 3);
  const white = new THREE.Color(HERO.colors.text);
  const violet = new THREE.Color(HERO.colors.accent);
  const a = DIM.width / 2;
  const b = DIM.depth / 2;

  for (let i = 0; i < count; i++) {
    const ambient = random() < ambientShare;
    if (ambient) {
      home[i * 3] = (random() - 0.5) * 17;
      home[i * 3 + 1] = (random() - 0.5) * 9;
      home[i * 3 + 2] = (random() - 0.5) * 12;
      seed[i * 4 + 3] = -1;
    } else {
      // A point on the device outline (a superellipse is close enough to the rounded rectangle),
      // pulled a little way inside, so the stream starts in the gap itself.
      const angle = random() * Math.PI * 2;
      const cos = Math.cos(angle);
      const sin = Math.sin(angle);
      const edge = Math.pow(Math.pow(Math.abs(cos / a), 5) + Math.pow(Math.abs(sin / b), 5), -1 / 5);
      const inward = 1 - 0.4 * random() * random();
      home[i * 3] = cos * edge * inward;
      home[i * 3 + 1] = (random() - 0.5) * 0.08;
      home[i * 3 + 2] = sin * edge * inward;

      // Mostly outward, with some lift or drop and a sideways swirl.
      const swirl = (random() - 0.5) * 0.9;
      const dx = cos - sin * swirl;
      const dy = (random() - 0.5) * 1.1;
      const dz = sin + cos * swirl;
      const length = Math.hypot(dx, dy, dz);
      dir[i * 3] = dx / length;
      dir[i * 3 + 1] = dy / length;
      dir[i * 3 + 2] = dz / length;
      seed[i * 4 + 3] = Math.floor(random() * GAPS);
    }
    seed[i * 4] = random();
    seed[i * 4 + 1] = 0.1 + 0.9 * Math.pow(random(), 2.4);
    seed[i * 4 + 2] = 0.55 + 0.9 * random();

    const tint = random() < violetShare ? violet : white;
    color[i * 3] = tint.r;
    color[i * 3 + 1] = tint.g;
    color[i * 3 + 2] = tint.b;
  }

  const geometry = new THREE.BufferGeometry();
  // `position` is unused by the shader, but three.js needs it to know how many points to draw.
  geometry.setAttribute("position", new THREE.BufferAttribute(home, 3));
  geometry.setAttribute("aHome", new THREE.BufferAttribute(home, 3));
  geometry.setAttribute("aDir", new THREE.BufferAttribute(dir, 3));
  geometry.setAttribute("aSeed", new THREE.BufferAttribute(seed, 4));
  geometry.setAttribute("aColor", new THREE.BufferAttribute(color, 3));
  return geometry;
}

/**
 * About 20k GPU points moved by curl noise in the vertex shader (no per-frame CPU work). Mostly off-white,
 * about 10% violet, small, soft and dim. They stream out of the gaps between layers as `rig.particles`
 * rises, burst with `rig.burst`, drift slowly while exploded, and get pulled back into the seams.
 *
 * `gapYRef` holds the world height of each gap, updated by the scene every frame.
 */
export function Particles({
  rigRef,
  gapYRef,
  frozen,
}: {
  rigRef: RefObject<HeroRig>;
  gapYRef: RefObject<Float32Array>;
  frozen: boolean;
}) {
  const material = useRef<THREE.ShaderMaterial>(null);
  const geometry = useMemo(() => buildGeometry(), []);
  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uSpread: { value: 0 },
      uBurst: { value: 0 },
      uSize: { value: HERO.particles.size },
      uPx: { value: 15 },
      uReach: { value: HERO.particles.reach },
      uCurlStrength: { value: HERO.particles.curlStrength },
      uCurlScale: { value: HERO.particles.curlScale },
      uCurlSpeed: { value: HERO.particles.curlSpeed },
      uOpacity: { value: HERO.particles.opacity },
      uGapY: { value: new Float32Array(GAPS) },
    }),
    [],
  );

  useFrame(({ clock, viewport }) => {
    const m = material.current;
    if (!m) return;
    const rig = rigRef.current;
    m.uniforms.uTime.value = frozen ? 0 : clock.elapsedTime;
    m.uniforms.uSpread.value = rig.particles;
    m.uniforms.uBurst.value = rig.burst;
    // Point size is given in CSS pixels at the resting camera distance.
    m.uniforms.uPx.value = viewport.dpr * HERO.camera.assembled.dist;
    (m.uniforms.uGapY.value as Float32Array).set(gapYRef.current);
  });

  return (
    <points geometry={geometry} frustumCulled={false} layers={FX_LAYER}>
      <shaderMaterial
        ref={material}
        uniforms={uniforms}
        vertexShader={vertexShader}
        fragmentShader={fragmentShader}
        blending={THREE.AdditiveBlending}
        transparent
        depthWrite={false}
        toneMapped={false}
      />
    </points>
  );
}
