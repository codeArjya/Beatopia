"use client";

import { ContactShadows, Environment, Lightformer } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { Bloom, ChromaticAberration, EffectComposer, Noise, Vignette } from "@react-three/postprocessing";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import Lenis from "lenis";
import { BlendFunction, type ChromaticAberrationEffect } from "postprocessing";
import { useEffect, useRef, useState, type RefObject } from "react";
import * as THREE from "three";

import { Backdrop } from "./Backdrop";
import { HERO, LABEL_LAYERS, LAYER, SEARCH_SECTION_ID, createRig, type HeroRig } from "./config";
import { FX_LAYER, GAPS, Particles } from "./Particles";
import { Board } from "./parts/Board";
import { BottomShell } from "./parts/BottomShell";
import { BOTTOM_Y, DIM, TOP_Y } from "./parts/dims";
import { Pads } from "./parts/Pads";
import { Screen } from "./parts/Screen";
import { Speaker } from "./parts/Speaker";
import { TopShell } from "./parts/TopShell";

/** Resting height of each layer group (top to bottom). Shells, pads and screen are modelled in place. */
const BASE_Y = [0, 0, 0, 0.05, -0.05, 0] as const;
/** Resting height of the gap under each of the first five layers, where particles hide. */
const GAP_Y = [0.3, 0.2, 0.11, 0, -0.16] as const;
/** What each leader line points at, in its layer's own space: centre plus half-size across x and z. */
const ANCHORS = [
  { x: 0, y: TOP_Y + 0.055, z: DIM.pad.centerZ, hx: 1.33, hz: 1.33 },
  { x: 0, y: TOP_Y, z: DIM.screen.centerZ, hx: DIM.screen.width / 2, hz: DIM.screen.depth / 2 },
  { x: 0, y: 0, z: DIM.pad.centerZ - 0.1, hx: 1.07, hz: 1.07 },
] as const;
const CORNERS = [
  [-1, -1],
  [1, -1],
  [-1, 1],
  [1, 1],
] as const;
/** Space between a label and the start of its leader line, in px. */
const LINE_GAP = 18;

/** The DOM pieces the scene positions every frame (leader lines follow the moving parts). */
type HeroDom = {
  labels: HTMLElement[];
  lines: HTMLElement[];
  dots: HTMLElement[];
  /** Per label: where its line starts (px from the stage's left edge) and the label's height. */
  metrics: { startX: number; height: number }[];
};

export type HeroSamplerProps = {
  /** The hero <section>: scroll trigger, and the root for every `data-hero-*` lookup. */
  sectionRef: RefObject<HTMLElement | null>;
  /** Filled with the Lenis instance while the hero is live, so the shell can glide to the search. */
  lenisRef: RefObject<Lenis | null>;
  /** Studio image behind the device, or null for the code-drawn haze. */
  backdropSrc: string | null;
};

function supportsWebGL2(): boolean {
  try {
    return document.createElement("canvas").getContext("webgl2") !== null;
  } catch {
    return false;
  }
}

/**
 * The scroll timeline: one scrubbed GSAP timeline, 0..1 across the pinned scroll, driving both the 3D rig
 * and the HTML text. Every number comes from HERO.timeline.
 */
function buildTimeline(rig: HeroRig, root: HTMLElement): gsap.core.Timeline {
  const T = HERO.timeline;
  const C = HERO.camera;
  const q = gsap.utils.selector(root);
  const tl = gsap.timeline({ paused: true, defaults: { ease: "none" } });
  const span = (range: readonly [number, number]) => range[1] - range[0];
  const intro = q("[data-hero-intro]");

  // 0 to 15%: ASSEMBLED. Only the text moves: the scroll cue leaves, then the headline.
  tl.to(q("[data-hero-cue]"), { opacity: 0, duration: span(T.cueOut) }, T.cueOut[0]);
  tl.to(intro, { opacity: 0, y: -18, duration: span(T.introOut), ease: "power1.in" }, T.introOut[0]);
  tl.to(rig, { idle: 0, duration: 0.07, ease: "sine.inOut" }, T.tear.start - 0.05);

  // 15 to 45%: TEARS APART. Layers lift top-first, the camera drops to the side, particles and traces wake.
  HERO.layers.forEach((_, i) => {
    tl.to(
      rig.layers[i],
      { lift: 1, duration: T.tear.duration, ease: T.tear.ease },
      T.tear.start + Math.min(i, 4) * T.tear.stagger,
    );
  });
  tl.to(rig, { spreadY: 1, duration: span(T.cameraOut), ease: "power2.inOut" }, T.cameraOut[0]);
  tl.to(rig.cam, { ...C.explodedStart, duration: span(T.cameraOut), ease: "power2.inOut" }, T.cameraOut[0]);
  tl.to(rig, { traces: 1, duration: span(T.tracesOn), ease: "power1.inOut" }, T.tracesOn[0]);
  tl.to(rig, { particles: 1, duration: span(T.particlesOut), ease: "expo.out" }, T.particlesOut[0]);
  tl.to(rig, { burst: 1, duration: T.burst.peak - T.burst.start, ease: "power2.out" }, T.burst.start);
  tl.to(rig, { burst: 0, duration: T.burst.end - T.burst.peak, ease: "power2.inOut" }, T.burst.peak);
  tl.to(rig, { aberration: 1, duration: T.aberrationTear[1] - T.aberrationTear[0] }, T.aberrationTear[0]);
  tl.to(rig, { aberration: 0, duration: T.aberrationTear[2] - T.aberrationTear[1] }, T.aberrationTear[1]);

  // 45 to 75%: EXPLODED. The camera turns around the stack; labels and leader lines show one at a time.
  tl.to(
    rig.cam,
    { az: C.explodedStart.az + C.orbitSweep, duration: span(T.orbit), ease: "sine.inOut" },
    T.orbit[0],
  );
  q("[data-hero-label]").forEach((label, j) => {
    const [from, to] = T.labels[j];
    const fade = T.labelFade;
    tl.to(label, { opacity: 1, duration: fade }, from);
    tl.to(rig.lines[j], { draw: 1, duration: fade * 2, ease: "power2.out" }, from + fade * 0.5);
    tl.to(rig.lines[j], { draw: 0, duration: fade, ease: "power1.in" }, to - fade);
    tl.to(label, { opacity: 0, duration: fade }, to - fade);
  });

  // 75 to 95%: COMES BACK TOGETHER. Layers snap home bottom-first with an overshoot, particles get pulled in.
  HERO.layers.forEach((_, i) => {
    tl.to(
      rig.layers[i],
      { lift: 0, duration: T.rejoin.duration, ease: T.rejoin.ease },
      T.rejoin.start + Math.max(0, 4 - i) * T.rejoin.stagger,
    );
  });
  tl.to(rig, { spreadY: 0, duration: span(T.cameraHome), ease: "power2.inOut" }, T.cameraHome[0]);
  tl.to(rig.cam, { ...C.settle, duration: span(T.cameraHome), ease: "power2.inOut" }, T.cameraHome[0]);
  tl.to(rig, { traces: 0, duration: span(T.tracesOff), ease: "power1.inOut" }, T.tracesOff[0]);
  tl.to(rig, { particles: 0, duration: span(T.particlesIn), ease: "power2.in" }, T.particlesIn[0]);
  tl.to(rig, { aberration: 1, duration: T.aberrationSnap[1] - T.aberrationSnap[0] }, T.aberrationSnap[0]);
  tl.to(rig, { aberration: 0, duration: T.aberrationSnap[2] - T.aberrationSnap[1] }, T.aberrationSnap[1]);

  // Closed: one violet pulse runs along the seam.
  const pulse = span(T.pulse);
  tl.to(rig.pulse, { head: 1, duration: pulse, ease: "power1.inOut" }, T.pulse[0]);
  tl.to(rig.pulse, { glow: 1, duration: pulse * 0.25, ease: "power2.out" }, T.pulse[0]);
  tl.to(rig.pulse, { glow: 0, duration: pulse * 0.45, ease: "power2.in" }, T.pulse[0] + pulse * 0.55);

  // 95 to 100%: SETTLE. The headline returns with the "Start digging" button.
  tl.to(intro, { opacity: 1, y: 0, duration: span(T.settleIn), ease: "power1.out" }, T.settleIn[0]);
  tl.to(q("[data-hero-cta]"), { autoAlpha: 1, duration: span(T.settleIn) }, T.settleIn[0]);
  tl.to(q("[data-hero-skip]"), { autoAlpha: 0, duration: span(T.settleIn) * 0.5 }, T.settleIn[0]);

  // Make the timeline exactly 1 long, so its positions read as fractions of the scroll.
  tl.set({}, {}, 1);
  return tl;
}

type Scratch = { point: THREE.Vector3; offsets: number[]; lastSize: string; fit: number; frames: number };

/** Everything inside the canvas: lights, the six layers, particles, shadow. Reads the rig every frame. */
function Scene({
  rigRef,
  domRef,
  frozen,
  backdropSrc,
  onFirstFrames,
}: {
  rigRef: RefObject<HeroRig>;
  domRef: RefObject<HeroDom | null>;
  frozen: boolean;
  backdropSrc: string | null;
  onFirstFrames: () => void;
}) {
  const device = useRef<THREE.Group>(null);
  const lights = useRef<THREE.Group>(null);
  const shadow = useRef<THREE.Group>(null);
  const layers = useRef<(THREE.Group | null)[]>([]);
  const gapY = useRef(new Float32Array(GAPS));
  const scratch = useRef<Scratch | null>(null);

  useFrame((state) => {
    const rig = rigRef.current;
    const dev = device.current;
    if (!dev) return;
    scratch.current ??= { point: new THREE.Vector3(), offsets: [0, 0, 0, 0, 0, 0], lastSize: "", fit: 1, frames: 0 };
    const s = scratch.current;
    const camera = state.camera as THREE.PerspectiveCamera;
    const { width, height } = state.size;

    // The effect composer turns the renderer's auto-clear off. The contact shadow draws into its own target
    // before the composer runs and relies on that clear; without it the shadow smears into a dark rectangle.
    if (!state.gl.autoClear) state.gl.autoClear = true;
    const time = frozen ? 0 : state.clock.elapsedTime;

    // The device sits right of centre (the text owns the left), and narrow windows pull the camera back.
    const sizeKey = `${width}x${height}`;
    if (s.lastSize !== sizeKey) {
      s.lastSize = sizeKey;
      s.fit = Math.max(1, HERO.camera.fitAspect / (width / height));
      camera.layers.enable(FX_LAYER);
      camera.setViewOffset(width, height, -(HERO.camera.centerX - 0.5) * width, 0, width, height);
    }

    // Layers: lift along Y with a small tilt. Past home (the snap-back overshoot) they push in a little.
    for (let i = 0; i < HERO.layers.length; i++) {
      const group = layers.current[i];
      if (!group) continue;
      const layer = HERO.layers[i];
      const raw = rig.layers[i].lift;
      const k = raw >= 0 ? raw : raw * HERO.overshoot;
      s.offsets[i] = layer.lift * k;
      group.position.y = BASE_Y[i] + s.offsets[i];
      group.rotation.x = layer.tiltX * k;
      group.rotation.z = layer.tiltZ * k;
    }

    // Device: floats and turns slowly while assembled; shifts down when exploded so the stack stays centred.
    dev.position.y =
      -HERO.camera.explodedDrop * rig.spreadY + Math.sin(time * HERO.idle.bobSpeed) * HERO.idle.bobHeight * rig.idle;
    dev.rotation.y = Math.sin(time * HERO.idle.swaySpeed) * HERO.idle.swayAngle * rig.idle;
    dev.updateMatrixWorld();
    for (let g = 0; g < GAPS; g++) {
      gapY.current[g] = dev.position.y + GAP_Y[g] + (s.offsets[g] + s.offsets[g + 1]) / 2;
    }
    if (shadow.current) {
      shadow.current.position.y = dev.position.y + BOTTOM_Y + s.offsets[LAYER.bottomShell] - 0.62;
    }

    // Camera on a sphere around the device. The lights ride with it: key from the top left, rim from behind.
    const { az, el, dist, lookY } = rig.cam;
    const distance = dist * s.fit;
    const flat = Math.cos(el) * distance;
    camera.position.set(Math.sin(az) * flat, Math.sin(el) * distance + lookY, Math.cos(az) * flat);
    camera.lookAt(0, lookY, 0);
    camera.updateMatrixWorld();
    if (lights.current) lights.current.rotation.y = az;
    state.scene.environmentRotation.y = az;

    // Leader lines: each label sits level with its part, and a thin line runs from the label to the part.
    const dom = domRef.current;
    if (dom) {
      for (let j = 0; j < LABEL_LAYERS.length; j++) {
        const group = layers.current[LABEL_LAYERS[j]];
        const label = dom.labels[j];
        const line = dom.lines[j];
        const dot = dom.dots[j];
        const metrics = dom.metrics[j];
        if (!group || !label || !line || !dot || !metrics) continue;
        const draw = rig.lines[j].draw;
        const anchor = ANCHORS[j];

        let leftEdge = Infinity;
        for (const [sx, sz] of CORNERS) {
          s.point.set(anchor.x + sx * anchor.hx, anchor.y, anchor.z + sz * anchor.hz);
          s.point.applyMatrix4(group.matrixWorld).project(camera);
          leftEdge = Math.min(leftEdge, (s.point.x * 0.5 + 0.5) * width);
        }
        s.point.set(anchor.x, anchor.y, anchor.z).applyMatrix4(group.matrixWorld).project(camera);
        const centerX = (s.point.x * 0.5 + 0.5) * width;
        const y = Math.min(
          height - metrics.height / 2 - 24,
          Math.max(metrics.height / 2 + 24, (1 - (s.point.y * 0.5 + 0.5)) * height),
        );
        // The line ends just inside the part's left edge.
        const endX = leftEdge + (centerX - leftEdge) * 0.22;
        const length = Math.max(0, endX - metrics.startX) * draw;

        const labelTransform = `translate3d(0,${(y - metrics.height / 2).toFixed(1)}px,0)`;
        if (label.style.transform !== labelTransform) label.style.transform = labelTransform;
        const lineTransform = `translate3d(${metrics.startX.toFixed(1)}px,${y.toFixed(1)}px,0) scaleX(${length.toFixed(1)})`;
        if (line.style.transform !== lineTransform) line.style.transform = lineTransform;
        const dotTransform = `translate3d(${endX.toFixed(1)}px,${y.toFixed(1)}px,0)`;
        if (dot.style.transform !== dotTransform) dot.style.transform = dotTransform;
        const dotOpacity = Math.min(1, Math.max(0, (draw - 0.75) * 4)).toFixed(2);
        if (dot.style.opacity !== dotOpacity) dot.style.opacity = dotOpacity;
      }
    }

    // Shaders compile on the first frames; reveal the canvas only once it has really drawn.
    if (++s.frames === 3) onFirstFrames();
  });

  const accent = HERO.colors.accent;
  return (
    <>
      <color attach="background" args={[HERO.colors.background]} />
      <Backdrop src={backdropSrc} />

      <ambientLight intensity={0.16} />
      <group ref={lights}>
        <directionalLight position={[-6, 8.5, 5]} intensity={2.5} color="#ffffff" />
        <directionalLight position={[6, 2.5, 6]} intensity={0.3} color="#dfe3ff" />
        {/* Low and behind, so it catches edges without washing the top faces violet. */}
        <directionalLight position={[2.5, 0.9, -8]} intensity={2.2} color={accent} />
      </group>
      {/* A small code-built studio for the glossy parts to reflect: a softbox top left, a violet strip behind. */}
      <Environment resolution={128} frames={1} environmentIntensity={0.55}>
        <Lightformer form="rect" intensity={3.2} color="#ffffff" position={[-5, 6.5, 4]} scale={[7, 7, 1]} />
        <Lightformer form="rect" intensity={0.5} color="#dfe3ff" position={[7, 1, 4]} scale={[3, 6, 1]} />
        <Lightformer form="rect" intensity={1.1} color={accent} position={[2, 0.8, -8]} scale={[9, 1.6, 1]} />
      </Environment>

      <group ref={device}>
        <TopShell
          ref={(group) => {
            layers.current[LAYER.topShell] = group;
          }}
        />
        <Pads
          ref={(group) => {
            layers.current[LAYER.pads] = group;
          }}
          rigRef={rigRef}
          frozen={frozen}
        />
        <Screen
          ref={(group) => {
            layers.current[LAYER.screen] = group;
          }}
          frozen={frozen}
        />
        <Board
          ref={(group) => {
            layers.current[LAYER.board] = group;
          }}
          rigRef={rigRef}
          frozen={frozen}
        />
        <Speaker
          ref={(group) => {
            layers.current[LAYER.speaker] = group;
          }}
        />
        <BottomShell
          ref={(group) => {
            layers.current[LAYER.bottomShell] = group;
          }}
          rigRef={rigRef}
        />
      </group>

      <Particles rigRef={rigRef} gapYRef={gapY} frozen={frozen} />

      <group ref={shadow}>
        <ContactShadows scale={13} far={7} blur={2.6} opacity={0.8} resolution={256} color="#000000" />
      </group>
    </>
  );
}

/** Subtle bloom on the bright parts, a short chromatic aberration on the two big moments, grain, vignette. */
function Effects({ rigRef, frozen }: { rigRef: RefObject<HeroRig>; frozen: boolean }) {
  const aberration = useRef<ChromaticAberrationEffect>(null);

  useFrame(() => {
    const amount = rigRef.current.aberration * HERO.fx.aberration;
    aberration.current?.offset.set(amount, amount * 0.55);
  });

  return (
    <EffectComposer multisampling={HERO.fx.msaa} enableNormalPass={false}>
      <Bloom
        mipmapBlur
        intensity={HERO.fx.bloomIntensity}
        luminanceThreshold={HERO.fx.bloomThreshold}
        luminanceSmoothing={0.18}
        radius={HERO.fx.bloomRadius}
      />
      <ChromaticAberration ref={aberration} radialModulation modulationOffset={0.2} />
      <Noise premultiply blendFunction={BlendFunction.SCREEN} opacity={frozen ? 0 : HERO.fx.grain} />
      <Vignette offset={HERO.fx.vignetteOffset} darkness={HERO.fx.vignetteDarkness} />
    </EffectComposer>
  );
}

/**
 * The scroll-driven 3D hero: canvas, scene and timeline. Loaded lazily by HeroSection, and only where the
 * pinned WebGL story runs (not on phones, not with reduced motion). All text is HTML in HeroSection; this
 * component animates it through `data-hero-*` hooks and draws the device behind it.
 *
 * Without WebGL the canvas is skipped and the timeline still drives the text over the still image.
 */
export default function HeroSampler({ sectionRef, lenisRef, backdropSrc }: HeroSamplerProps) {
  const rigRef = useRef<HeroRig | null>(null);
  if (rigRef.current === null) rigRef.current = createRig();
  const domRef = useRef<HeroDom | null>(null);
  const [webgl] = useState(supportsWebGL2);
  // `?hero-still` freezes time and grain, for capturing the still image (scripts/hero-shots.mjs).
  const [frozen] = useState(() => new URLSearchParams(window.location.search).has("hero-still"));
  const [inView, setInView] = useState(true);
  const [drawn, setDrawn] = useState(false);

  // Scroll timeline + smooth scroll.
  useEffect(() => {
    const root = sectionRef.current;
    const rig = rigRef.current;
    if (!root || !rig) return;
    const stage = root.querySelector<HTMLElement>("[data-hero-stage]");
    if (!stage) return;
    gsap.registerPlugin(ScrollTrigger);

    const context = gsap.context(() => {
      ScrollTrigger.create({
        trigger: root,
        // The stage pins under the sticky header, so the story starts when the hero reaches that line.
        start: () => `top ${parseFloat(getComputedStyle(stage).top) || 0}px`,
        end: "bottom bottom",
        scrub: HERO.scrub,
        animation: buildTimeline(rig, root),
      });
      // Leaving: the stage dims as the search page rises under it.
      gsap.to(stage, {
        opacity: 0.3,
        ease: "none",
        scrollTrigger: { trigger: root, start: "bottom bottom", end: "bottom 25%", scrub: true },
      });
    }, root);

    // Smooth wheel scrolling for the hero only: the search page, sheets and dialogs keep native scrolling.
    const lenis = new Lenis({
      lerp: HERO.lerp,
      autoRaf: false,
      prevent: (node) => node.id === SEARCH_SECTION_ID || node.getAttribute("role") === "dialog",
    });
    lenis.on("scroll", ScrollTrigger.update);
    const tick = (time: number) => lenis.raf(time * 1000);
    gsap.ticker.add(tick);
    lenisRef.current = lenis;

    return () => {
      lenisRef.current = null;
      gsap.ticker.remove(tick);
      lenis.destroy();
      context.revert();
      Object.assign(rig, createRig());
    };
  }, [sectionRef, lenisRef]);

  // Leader-line DOM: collect the elements, and re-measure the labels whenever their size changes.
  useEffect(() => {
    const root = sectionRef.current;
    const stage = root?.querySelector<HTMLElement>("[data-hero-stage]");
    if (!root || !stage) return;
    const dom: HeroDom = {
      labels: Array.from(root.querySelectorAll<HTMLElement>("[data-hero-label]")),
      lines: Array.from(root.querySelectorAll<HTMLElement>("[data-hero-line]")),
      dots: Array.from(root.querySelectorAll<HTMLElement>("[data-hero-dot]")),
      metrics: [],
    };
    const measure = () => {
      const stageLeft = stage.getBoundingClientRect().left;
      dom.metrics = dom.labels.map((label) => {
        const rect = label.getBoundingClientRect();
        return { startX: rect.right - stageLeft + LINE_GAP, height: rect.height };
      });
    };
    measure();
    domRef.current = dom;
    const observer = new ResizeObserver(measure);
    observer.observe(stage);
    dom.labels.forEach((label) => observer.observe(label));

    return () => {
      observer.disconnect();
      domRef.current = null;
      for (const element of [...dom.labels, ...dom.lines, ...dom.dots]) {
        element.style.transform = "";
        element.style.opacity = "";
      }
    };
  }, [sectionRef]);

  // Stop rendering while the hero is off screen.
  useEffect(() => {
    const root = sectionRef.current;
    if (!root) return;
    // The top strip is excluded: once only a sliver is left under the sticky header, the hero counts as gone.
    const observer = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting), {
      rootMargin: "-72px 0px 0px 0px",
    });
    observer.observe(root);
    return () => observer.disconnect();
  }, [sectionRef]);

  if (!webgl) return null;
  return (
    <div
      className="absolute inset-0 transition-opacity duration-700 ease-out"
      style={{ opacity: drawn ? 1 : 0 }}
      data-hero-canvas={drawn ? "ready" : "loading"}
    >
      <Canvas
        flat
        dpr={[1, HERO.maxDpr]}
        frameloop={inView ? "always" : "never"}
        gl={{ antialias: false, alpha: false, stencil: false, powerPreference: "high-performance" }}
        camera={{ fov: HERO.camera.fov, near: 1, far: 80, position: [8, 9, 10] }}
        // The contact shadow renders the scene into its own target; it needs a transparent clear there.
        onCreated={({ gl }) => gl.setClearAlpha(0)}
        style={{ pointerEvents: "none" }}
        aria-hidden
      >
        <Scene
          rigRef={rigRef as RefObject<HeroRig>}
          domRef={domRef}
          frozen={frozen}
          backdropSrc={backdropSrc}
          onFirstFrames={() => setDrawn(true)}
        />
        <Effects rigRef={rigRef as RefObject<HeroRig>} frozen={frozen} />
      </Canvas>
    </div>
  );
}
