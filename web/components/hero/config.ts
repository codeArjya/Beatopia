/**
 * Every tunable number for the scroll hero lives here: timing, speed, particle count, colors, camera.
 * Timeline positions are fractions of the pinned scroll (0 = hero top, 1 = hero released).
 *
 * Quick tuning:
 *  - Slower / faster overall ........ `scrollVh` (how much scroll the hero takes) and `scrub` (catch-up lag)
 *  - When things happen ............. `timeline`
 *  - Particle amount and feel ....... `particles`
 *  - Colors ......................... `colors` (keep in step with app/globals.css)
 *
 * After changing colors, the device or the assembled camera pose, re-capture the still image
 * (scripts/hero-shots.mjs --still), since phones and reduced-motion visitors only ever see that image.
 */

/**
 * When the scroll-driven WebGL hero runs. Everyone else gets the still image with the same text, stacked.
 * This string must stay identical to the `cinema` custom variant in app/globals.css.
 */
export const HERO_CINEMA_QUERY =
  "(min-width: 721px) and (min-height: 521px) and (prefers-reduced-motion: no-preference)";

/** id of the search section below the hero: where "Start digging" and "Skip intro" lead. */
export const SEARCH_SECTION_ID = "search";

export const HERO = {
  /** Scroll distance the hero stays pinned for, in vh. Bigger = slower story. */
  scrollVh: 500,
  /** Seconds the animation takes to catch up with the scrollbar. 0 locks it to the scroll position. */
  scrub: 0.6,
  /** Lenis wheel smoothing while the pointer is over the hero (0..1; lower is floatier). */
  lerp: 0.11,

  colors: {
    background: "#0d0d0f",
    text: "#ededed",
    accent: "#8b5cf6",
    shell: "#1b1b20",
    shellEdge: "#101013",
    rubber: "#0c0c0f",
    board: "#1d1e24",
    traceIdle: "#34343f",
    waveUnplayed: "#4a4a57",
    /** One hue per pad row, back row first (the chip category hues). */
    padRows: ["#5fb3a8", "#6fa0e6", "#e083ae", "#b9cc6e"],
  },

  timeline: {
    /** "Scroll to take it apart" cue fades out. */
    cueOut: [0.02, 0.07],
    /** Headline block fades out before the tear-apart. */
    introOut: [0.1, 0.15],

    /** TEARS APART: each layer starts `stagger` after the one above it and takes `duration` to lift. */
    tear: { start: 0.15, stagger: 0.03, duration: 0.18, ease: "power3.inOut" },
    /** Camera drops from the hero angle to the side-on exploded view. */
    cameraOut: [0.15, 0.37],
    /** Board traces light up, then go dark again as it closes. */
    tracesOn: [0.18, 0.38],
    tracesOff: [0.76, 0.9],
    /** Particles stream out of the gaps, then get pulled back into the seams. */
    particlesOut: [0.15, 0.45],
    particlesIn: [0.75, 0.93],
    /** The burst: extra speed and brightness that peaks at `peak` and is gone by `end`. */
    burst: { start: 0.15, peak: 0.22, end: 0.42 },
    /** Chromatic aberration flashes: [start, peak, end]. */
    aberrationTear: [0.15, 0.2, 0.32],
    aberrationSnap: [0.84, 0.91, 0.96],

    /** EXPLODED: the camera turns around the stack. */
    orbit: [0.45, 0.75],
    /** One label at a time: [in, out] for pads, screen, speaker. */
    labels: [
      [0.46, 0.55],
      [0.555, 0.645],
      [0.65, 0.74],
    ],
    /** How long a label takes to fade in or out. */
    labelFade: 0.02,

    /** COMES BACK TOGETHER: layers snap home bottom-up, each with a small overshoot. */
    rejoin: { start: 0.75, stagger: 0.025, duration: 0.085, ease: "back.out(1.7)" },
    /** Camera returns to the resting 3/4 angle. */
    cameraHome: [0.75, 0.95],
    /** One violet pulse runs along the seam once it is closed. */
    pulse: [0.925, 0.975],

    /** SETTLE: headline and the "Start digging" button fade in. */
    settleIn: [0.95, 0.99],
  },

  /** How far each layer lifts when exploded (world units) and its small tilt (radians, x and z). Top to bottom. */
  layers: [
    { id: "topShell", lift: 3.7, tiltX: 0.1, tiltZ: -0.05 },
    { id: "pads", lift: 2.75, tiltX: -0.06, tiltZ: 0.05 },
    { id: "screen", lift: 2.05, tiltX: 0.08, tiltZ: 0.06 },
    { id: "board", lift: 1.45, tiltX: -0.05, tiltZ: -0.05 },
    { id: "speaker", lift: 0.5, tiltX: 0.05, tiltZ: 0.04 },
    { id: "bottomShell", lift: -0.35, tiltX: -0.03, tiltZ: 0.02 },
  ],
  /** How much of the overshoot (layers pushing past home) is shown. 0 hides it. */
  overshoot: 0.35,

  camera: {
    fov: 28,
    /** Where the device sits across the stage (0.5 = centred). The text owns the left side. */
    centerX: 0.67,
    /** Below this width/height ratio the camera pulls back so the device stays out of the text column. */
    fitAspect: 1.62,
    /** az = turn around the device (radians), el = height angle, dist = distance, lookY = look-at height. */
    assembled: { az: 0.62, el: 0.7, dist: 14.6, lookY: 0 },
    explodedStart: { az: 1.0, el: 0.42, dist: 18.6, lookY: 0 },
    /** How far the camera turns during the EXPLODED beat (radians). */
    orbitSweep: 3.6,
    /** Resting 3/4 angle. One full turn past the start, so the camera never unwinds. */
    settle: { az: 0.74 + Math.PI * 2, el: 0.62, dist: 14.2, lookY: 0 },
    /** The stack is taller than the device, so it shifts down by this much when exploded to stay centred. */
    explodedDrop: 1.67,
  },

  idle: {
    /** Slow turn while assembled: radians either way, and how fast. */
    swayAngle: 0.3,
    swaySpeed: 0.28,
    /** Floating bob: world units and speed. */
    bobHeight: 0.07,
    bobSpeed: 0.75,
    /** Seconds between pad hits of the little idle pattern. */
    padStep: 0.42,
  },

  particles: {
    count: 20000,
    /** Share of violet particles (the rest are off-white). */
    violetShare: 0.1,
    /** Share that just drifts around the room and never joins the burst. */
    ambientShare: 0.07,
    /** Point size in CSS pixels at the device's distance. */
    size: 2.1,
    /** Overall brightness. Keep it dim: these must stay under the bloom threshold. */
    opacity: 0.2,
    /** How far the burst throws particles (world units). */
    reach: 2.7,
    /** Curl-noise drift: strength, detail (higher = tighter swirls) and speed. */
    curlStrength: 0.85,
    curlScale: 0.42,
    curlSpeed: 0.07,
  },

  fx: {
    /** Bloom only catches the parts pushed bright on purpose: screen, traces, playhead, edge pulse. */
    bloomIntensity: 0.5,
    bloomThreshold: 0.5,
    bloomRadius: 0.7,
    /** How far past their base color the bright parts are pushed (this is what makes them bloom). */
    screenBoost: 1.9,
    playheadBoost: 3.0,
    traceBoost: 2.3,
    pulseBoost: 3.6,
    /** Peak chromatic aberration offset (screen fraction). */
    aberration: 0.0032,
    grain: 0.22,
    vignetteOffset: 0.28,
    vignetteDarkness: 0.58,
    /** Antialiasing samples for the effect chain (0 turns it off). */
    msaa: 4,
  },

  backdrop: {
    /**
     * Optional studio image behind the device (16:9, near-black). It is used only if the file exists in
     * public/ (app/page.tsx checks at build time); until then, and if it ever fails to load, the haze is
     * drawn in code. Either way the backdrop fades to the page background before it reaches the edges.
     */
    image: "/hero/backdrop.jpg",
    /** How strongly the backdrop shows over the flat page background (0..1). */
    opacity: 1,
    /** Code-drawn fallback: strength of the violet light behind the device, and of the white haze. */
    hazeViolet: 0.02,
    hazeWhite: 0.011,
  },

  /** Device pixel ratio cap. */
  maxDpr: 1.5,
} as const;

export type HeroLayerId = (typeof HERO.layers)[number]["id"];

/** Index of each layer in `HERO.layers` (top to bottom). */
export const LAYER = { topShell: 0, pads: 1, screen: 2, board: 3, speaker: 4, bottomShell: 5 } as const;

/** Which layer each label's leader line points at, in label order. */
export const LABEL_LAYERS = [LAYER.pads, LAYER.screen, LAYER.speaker] as const;

/**
 * Animation state. The GSAP scroll timeline writes it; the 3D scene reads it every frame.
 * Plain numbers on purpose, so one scrubbed timeline drives DOM and WebGL together.
 */
export type HeroRig = {
  /** 0 = home, 1 = fully lifted. Top to bottom, same order as `HERO.layers`. */
  layers: { lift: number }[];
  cam: { az: number; el: number; dist: number; lookY: number };
  /** 0..1: how exploded the stack is overall (drives the downward shift and the shadow). */
  spreadY: number;
  /** 0..1: weight of the idle sway and bob. */
  idle: number;
  /** 0..1: board trace glow. */
  traces: number;
  /** 0..1: how far particles have left the seams. */
  particles: number;
  /** 0..1: burst energy. */
  burst: number;
  /** 0..1: chromatic aberration amount. */
  aberration: number;
  /** Edge pulse: `head` is its position around the seam (0..1), `glow` its brightness. */
  pulse: { head: number; glow: number };
  /** 0..1 per label: how much of its leader line is drawn. */
  lines: { draw: number }[];
};

export function createRig(): HeroRig {
  const { assembled } = HERO.camera;
  return {
    layers: HERO.layers.map(() => ({ lift: 0 })),
    cam: { ...assembled },
    spreadY: 0,
    idle: 1,
    traces: 0,
    particles: 0,
    burst: 0,
    aberration: 0,
    pulse: { head: 0, glow: 0 },
    lines: LABEL_LAYERS.map(() => ({ draw: 0 })),
  };
}
