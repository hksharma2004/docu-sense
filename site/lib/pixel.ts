// procedural pixel-art landscapes, drawn small and scaled up with
// `image-rendering: pixelated`. scenes are seeded, so they're stable across renders.

type RGB = [number, number, number];

type Palette = {
  sky: string[];
  clouds: string;
  cloudShade: string;
  far: [string, string];
  snow: string | null;
  trees: [string, string, string, string]; // base, shadow, lit, highlight
  ground: [string, string, string];
  water: [string, string, string] | null;
  rock: string;
};

export const SCENES = {
  alpine: { sky: ["#7FB3E0", "#BFDDF0", "#E9F2F2"], clouds: "#FBF6EC", cloudShade: "#D9DCE4", far: ["#8EA6C8", "#6E86AE"], snow: "#F4F1EA", trees: ["#2F5A3A", "#1F4229", "#4F8A3E", "#86B04A"], ground: ["#6F9C3F", "#8DB650", "#5A8233"], water: null, rock: "#9A8B78" },
  lake: { sky: ["#9CC6E6", "#D6E9F2", "#F3EFE3"], clouds: "#FFFDF6", cloudShade: "#DCE3EA", far: ["#A5B9CF", "#8BA1BC"], snow: "#F6F3EC", trees: ["#3D6B45", "#2B5234", "#6B9A4A", "#9DC062"], ground: ["#E7D7B0", "#D9C596", "#CDB784"], water: ["#5FA3C8", "#7DB8D6", "#A9D2E4"], rock: "#B9A88A" },
  hills: { sky: ["#A9CFE9", "#DCEBF1", "#F2F1E6"], clouds: "#FFFFFF", cloudShade: "#DDE5EC", far: ["#9DB89A", "#86A587"], snow: null, trees: ["#3F6E35", "#2E5628", "#5F9140", "#A3C65A"], ground: ["#8DBA4F", "#A6CB5F", "#77A443"], water: null, rock: "#A69676" },
  dusk: { sky: ["#F2B48A", "#F6D3A8", "#F7E8C9"], clouds: "#FFF1DE", cloudShade: "#EAC3A2", far: ["#B98FA0", "#9C7489"], snow: "#F7E6DA", trees: ["#3C3E52", "#2B2C3E", "#5B5D6E", "#7E7A86"], ground: ["#4B5A4C", "#5E6E57", "#3E4C40"], water: ["#C99A9E", "#E0B7A8", "#F1D0B6"], rock: "#8B7E86" },
  lake2: { sky: ["#8FBEE1", "#CFE4F0", "#EEF0EA"], clouds: "#FFFCF4", cloudShade: "#D8E0E8", far: ["#9AB0C9", "#7F98B6"], snow: "#F3F1EC", trees: ["#336241", "#24492F", "#5C8F45", "#90B958"], ground: ["#E2D3AE", "#D6C291", "#C8B27F"], water: ["#4F96BF", "#6FAED0", "#9BC9E0"], rock: "#A79879" },
} satisfies Record<string, Palette>;

export type SceneName = keyof typeof SCENES;

const BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]];

function rng(seed: number) {
  return () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const hex = (h: string): RGB => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
const mix = (a: RGB, b: RGB, t: number): RGB => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
function hash(x: number, y: number, s: number) {
  let h = (x * 374761393 + y * 668265263 + s * 1442695041) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

export function paintScene(canvas: HTMLCanvasElement, name: SceneName, seed: number) {
  const P: Palette = SCENES[name];
  const el = canvas.parentElement;
  if (!el) return;
  const px = window.innerWidth < 700 ? 4 : 5;
  const W = Math.max(40, Math.ceil(el.clientWidth / px));
  const H = Math.max(40, Math.ceil(el.clientHeight / px));
  canvas.width = W; canvas.height = H;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const img = ctx.createImageData(W, H), d = img.data, r = rng(seed);
  const set = (x: number, y: number, c: RGB) => {
    x = Math.round(x); y = Math.round(y);
    if (x < 0 || y < 0 || x >= W || y >= H) return;
    const i = (y * W + x) * 4; d[i] = c[0]; d[i + 1] = c[1]; d[i + 2] = c[2]; d[i + 3] = 255;
  };
  const Q = 7;
  const q = (v: number, x: number, y: number) => Math.max(0, Math.min(255, Math.round((v + (BAYER[y & 3][x & 3] / 16 - 0.5) * Q) / Q) * Q));
  const sky = P.sky.map(hex), horizon = Math.floor(H * (P.water ? 0.6 : 0.64));

  // sky: smooth gradient with a fine ordered dither
  for (let y = 0; y < H; y++) {
    const t = Math.min(1, y / horizon) * (sky.length - 1), b = Math.min(sky.length - 2, Math.floor(t)), c = mix(sky[b], sky[b + 1], t - b);
    for (let x = 0; x < W; x++) set(x, y, [q(c[0], x, y), q(c[1], x, y), q(c[2], x, y)]);
  }

  // clouds: stacked puffs with flat shaded bottoms
  const cc = hex(P.clouds), cs = hex(P.cloudShade);
  for (let k = 0; k < Math.ceil(W / 42); k++) {
    const cx = (k + 0.2 + r() * 0.6) * 42, cy = H * (0.07 + r() * 0.2), n = 4 + Math.floor(r() * 4);
    const puffs: [number, number, number][] = [];
    for (let j = 0; j < n; j++) puffs.push([cx + (j - n / 2) * (3 + r() * 3), cy - Math.sin((j / (n - 1)) * Math.PI) * (2 + r() * 3), 2.5 + r() * 4]);
    const bottom = cy + 3;
    for (const [x0, y0, pr] of puffs)
      for (let y = -pr; y <= pr; y++)
        for (let x = -pr * 1.5; x <= pr * 1.5; x++) {
          const yy = y0 + y;
          if (yy > bottom) continue;
          if ((x * x) / 2.25 + y * y <= pr * pr) set(x0 + x, yy, yy > bottom - 2 || (y > pr * 0.4 && x > 0) ? cs : cc);
        }
  }

  // far mountains: lit and shadow faces, snow caps on the high peaks
  const far = P.far.map(hex) as [RGB, RGB], snow = P.snow ? hex(P.snow) : null;
  const ridge = (base: number, amp: number, f: number, ph: number) => (x: number) =>
    base - amp * Math.max(0, Math.sin(x * f + ph) * 0.6 + Math.sin(x * f * 2.1 + ph * 1.7) * 0.28 + Math.sin(x * f * 4.7 + ph * 0.3) * 0.12 + 0.25);
  const fr = ridge(horizon - H * 0.04, H * (P.snow ? 0.34 : 0.14), 5.5 / W, r() * 9);
  let peakY = Infinity;
  for (let x = 0; x < W; x++) peakY = Math.min(peakY, fr(x));
  for (let x = 0; x < W; x++) {
    const top = Math.round(fr(x)), lit = fr(x + 1) > fr(x - 1);
    for (let y = top; y < horizon + 2; y++) {
      let c = lit ? far[0] : far[1];
      if (snow && y < top + 2 + Math.floor(hash(x, 0, seed) * 3) + (top - peakY < H * 0.08 ? 4 : 0) && top < peakY + H * 0.16) c = lit ? snow : mix(snow, far[1], 0.35);
      else if (hash(x, y, seed) > 0.93) c = mix(c, far[1], 0.6);
      set(x, y, c);
    }
  }

  // atmospheric haze above the horizon
  const hazeTop = horizon - Math.floor(H * 0.05), haze = sky[sky.length - 1];
  for (let y = hazeTop; y < horizon + 2; y++)
    for (let x = 0; x < W; x++) {
      const t = 0.25 * (1 - (horizon - y) / (H * 0.05));
      if (t <= 0) continue;
      const i = (y * W + x) * 4;
      d[i] += (haze[0] - d[i]) * t; d[i + 1] += (haze[1] - d[i + 1]) * t; d[i + 2] += (haze[2] - d[i + 2]) * t;
    }

  // ground or lake + beach
  const gr = P.ground.map(hex);
  if (P.water) {
    const wa = P.water.map(hex), shore = Math.floor(H * 0.8);
    for (let y = horizon; y < shore; y++) {
      const depth = (y - horizon) / (shore - horizon);
      for (let x = 0; x < W; x++) {
        let c = mix(wa[0], wa[1], depth * 0.6);
        const h = hash(Math.floor(x / (3 + Math.floor(hash(y, 1, seed) * 5))), y, seed);
        if (h > 0.86) c = wa[2]; else if (h < 0.08) c = mix(wa[0], [30, 60, 90], 0.15);
        set(x, y, c);
      }
    }
    for (let y = shore; y < H; y++)
      for (let x = 0; x < W; x++) {
        const h = hash(x, y, seed + 3);
        set(x, y, y === shore ? mix(gr[0], [255, 255, 255], 0.35) : h > 0.85 ? gr[2] : h > 0.6 ? gr[1] : gr[0]);
      }
  } else {
    for (let y = horizon; y < H; y++) {
      const t = (y - horizon) / (H - horizon);
      for (let x = 0; x < W; x++) {
        const h = hash(x, y, seed + 3);
        let c = mix(gr[1], gr[0], t);
        if (h > 0.9) c = gr[2]; else if (h < 0.06) c = mix(c, [255, 255, 220], 0.25);
        set(x, y, c);
      }
    }
  }

  // pine tree: tiered branches, lit from the left, faded by distance
  const tr = P.trees.map(hex);
  const pine = (x0: number, base: number, h: number, fade: number) => {
    const w = Math.max(2, h * 0.36), tier = Math.max(3, Math.floor(h / 4.5));
    const cols = tr.map((c) => mix(c, far[0], fade));
    for (let y = 0; y < h; y++) {
      const lv = (y + 1) / h, step = (y % tier) / tier, half = Math.round(w * Math.min(1, lv * 0.85 + step * 0.25 * lv));
      for (let x = -half; x <= half; x++) {
        let c = cols[0];
        if (x < -half * 0.15) c = cols[2];
        if (x < -half * 0.55 && hash(x0 + x, y, seed) > 0.45) c = cols[3];
        if (x > half * 0.35) c = cols[1];
        if (step < 0.2 && x > -half * 0.6) c = cols[1];
        set(x0 + x, base - h + y, c);
      }
    }
    set(x0, base, mix(cols[1], [60, 40, 30], 0.5));
  };

  // forest bands, back to front: [baseline, fade, scale, spacing]
  const bands: [number, number, number, number][] = P.water
    ? [[horizon, 0.75, 0.5, 2.2], [horizon + 1, 0.45, 0.85, 4]]
    : [[horizon, 0.6, 0.45, 2], [horizon + Math.floor(H * 0.08), 0.3, 0.8, 3.2], [horizon + Math.floor(H * 0.2), 0.1, 1.2, 6]];
  for (const [base, fade, scale, gap] of bands)
    for (let x = -4; x < W + 4; x += gap + r() * gap) {
      if (P.water && x > W * 0.3 && x < W * 0.7 && fade < 0.6) continue;
      pine(Math.round(x), base + Math.floor(r() * 2), Math.floor((7 + r() * 9) * scale * (H / 90)), fade);
    }

  // foreground hero trees and rocks
  if (!P.water) {
    for (let k = 0; k < Math.ceil(W / 45); k++) pine(Math.floor(r() * W), H - 1, Math.floor(H * (0.32 + r() * 0.2)), 0);
    const rc = hex(P.rock);
    for (let k = 0; k < Math.ceil(W / 70); k++) {
      const x0 = Math.floor(r() * W), y0 = H - 1 - Math.floor(r() * H * 0.08), s = 3 + Math.floor(r() * 4);
      for (let y = -s; y <= 0; y++)
        for (let x = -s * 1.5; x <= s * 1.5; x++)
          if ((x * x) / 2.25 + y * y <= s * s)
            set(x0 + x, y0 + y, y < -s * 0.4 && x < s * 0.3 ? mix(rc, [255, 255, 255], 0.35) : x > s * 0.6 ? mix(rc, [0, 0, 0], 0.15) : rc);
    }
  }

  ctx.putImageData(img, 0, 0);
}
