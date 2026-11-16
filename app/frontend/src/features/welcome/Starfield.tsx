// Animated starfield behind the welcome page (v1.8). One <canvas>, no images.
// Stars are born at the centre of the screen and drift outwards, faster and bigger as they go, like travelling
// through space; a star that leaves the screen is born again at the centre, so the sky loops forever. They twinkle
// and shift a little with the mouse. The "Start" button can pull them in (setAttractor): a star that touches the
// button is absorbed with a small flash and is born again at the centre. With "reduce motion" switched on in the
// system, the stars are drawn once and stay still.
import * as React from "react";

export type AttractorRect = { x: number; y: number; width: number; height: number };
export type StarfieldHandle = {
  /** Pull the stars towards this element box (page coordinates), or release them with null. */
  setAttractor: (rect: AttractorRect | null) => void;
};

type Star = {
  x: number; // position in px (without the mouse parallax)
  y: number;
  vx: number;
  vy: number;
  z: number; // depth 0.25..1: speed, size, brightness and parallax
  r: number;
  phase: number;
  speed: number;
  age: number;
  color: string;
  sparkle: boolean;
};
type Comet = { x: number; y: number; vx: number; vy: number; life: number };
type Flash = { x: number; y: number; life: number; size: number };

const COLORS = ["#f6d98f", "#e9c477", "#fff3cf", "#d9ae5f", "#ffe6a6"];
const ATTRACT_RADIUS = 600; // px around the button
const ATTRACT_FORCE = 2600; // px/s² at full strength, near the button
const DRIFT_BASE = 6; // outward speed (px/s) at the centre...
const DRIFT_PER_PX = 0.2; // ...plus this much per px of distance from the centre
const PARALLAX = 16;

export const Starfield = React.forwardRef<StarfieldHandle, { className?: string }>(function Starfield(
  { className },
  ref,
) {
  const canvasRef = React.useRef<HTMLCanvasElement>(null);
  const attractor = React.useRef<AttractorRect | null>(null);
  const targetStrength = React.useRef(0);

  React.useImperativeHandle(ref, () => ({
    setAttractor: (rect) => {
      if (rect) attractor.current = rect;
      targetStrength.current = rect ? 1 : 0;
    },
  }));

  React.useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let width = 0,
      height = 0,
      stars: Star[] = [],
      frame = 0,
      strength = 0,
      last = performance.now(),
      nextComet = last + 4000 + Math.random() * 5000;
    const comets: Comet[] = [];
    const flashes: Flash[] = [];
    const mouse = { x: 0, y: 0, sx: 0, sy: 0 }; // -1..1 from the centre, smoothed in sx/sy
    const centre = () => ({ x: width / 2, y: height * 0.46 });

    function newStar(anywhere: boolean): Star {
      const z = 0.25 + Math.random() ** 1.6 * 0.75;
      const s: Star = {
        x: 0,
        y: 0,
        vx: 0,
        vy: 0,
        z,
        r: 0.55 + z * 1.5 + (Math.random() < 0.05 ? 0.9 : 0),
        phase: Math.random() * Math.PI * 2,
        speed: 0.6 + Math.random() * 1.8,
        age: anywhere ? 10 : 0,
        color: COLORS[(Math.random() * COLORS.length) | 0],
        sparkle: Math.random() < 0.09,
      };
      place(s, anywhere ? "anywhere" : "centre");
      return s;
    }

    /** "centre": born at the centre (it left the screen); "ray": absorbed by the button, born again somewhere on a
     *  ray from the centre so the sky never empties; "anywhere": first fill of the screen. */
    function place(s: Star, where: "anywhere" | "centre" | "ray") {
      const c = centre();
      if (where === "anywhere") {
        s.x = Math.random() * width;
        s.y = Math.random() * height;
      } else if (where === "ray") {
        const a = Math.random() * Math.PI * 2,
          d = 40 + Math.random() * Math.hypot(width, height) * 0.38;
        s.x = c.x + Math.cos(a) * d;
        s.y = c.y + Math.sin(a) * d;
        s.age = 0;
      } else {
        const a = Math.random() * Math.PI * 2,
          d = Math.random() * 24;
        s.x = c.x + Math.cos(a) * d;
        s.y = c.y + Math.sin(a) * d;
        s.age = 0;
      }
      const dx = s.x - c.x,
        dy = s.y - c.y,
        dist = Math.hypot(dx, dy) || 1;
      const v = (DRIFT_BASE + dist * DRIFT_PER_PX) * s.z;
      s.vx = (dx / dist) * v;
      s.vy = (dy / dist) * v;
    }

    function resize() {
      const rect = canvas!.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = rect.width;
      height = rect.height;
      canvas!.width = Math.round(width * dpr);
      canvas!.height = Math.round(height * dpr);
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
      const count = Math.max(110, Math.min(420, Math.round((width * height) / 4000)));
      stars = Array.from({ length: count }, () => newStar(true));
      if (reduceMotion) draw(performance.now(), 0);
    }

    function onMove(e: PointerEvent) {
      mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
      mouse.y = (e.clientY / window.innerHeight) * 2 - 1;
    }

    function drawSparkle(x: number, y: number, size: number) {
      ctx!.beginPath();
      ctx!.moveTo(x, y - size);
      ctx!.quadraticCurveTo(x, y, x + size, y);
      ctx!.quadraticCurveTo(x, y, x, y + size);
      ctx!.quadraticCurveTo(x, y, x - size, y);
      ctx!.quadraticCurveTo(x, y, x, y - size);
      ctx!.fill();
    }

    function draw(now: number, dt: number) {
      ctx!.clearRect(0, 0, width, height);
      const t = now / 1000;
      const c = centre();
      const maxDist = Math.hypot(width, height) / 2;

      mouse.sx += (mouse.x - mouse.sx) * Math.min(1, dt * 3);
      mouse.sy += (mouse.y - mouse.sy) * Math.min(1, dt * 3);
      const goal = targetStrength.current;
      strength += (goal - strength) * Math.min(1, dt * (goal > strength ? 8 : 4));

      // the button box, in canvas coordinates
      const box = canvas!.getBoundingClientRect();
      const a = attractor.current;
      const bx = a ? a.x - box.left + a.width / 2 : 0,
        by = a ? a.y - box.top + a.height / 2 : 0;

      for (const s of stars) {
        s.age += dt;
        const ox = -mouse.sx * PARALLAX * s.z,
          oy = -mouse.sy * PARALLAX * s.z;
        let x = s.x + ox,
          y = s.y + oy,
          glow = 0;

        if (!reduceMotion) {
          let pulled = false;
          const grown = Math.min(1, Math.max(0, (s.age - 0.6) / 1.6));
          if (a && strength > 0.02 && grown > 0) {
            const dx = bx - x,
              dy = by - y,
              d = Math.hypot(dx, dy) || 1;
            if (d < ATTRACT_RADIUS) {
              const f = (1 - d / ATTRACT_RADIUS) ** 0.8 * strength * grown;
              const force = ATTRACT_FORCE * (0.35 + 0.65 * f);
              s.vx += (dx / d) * force * f * dt;
              s.vy += (dy / d) * force * f * dt;
              const damp = Math.max(0, 1 - dt * 2.2 * f); // less orbiting: the star dives into the button
              s.vx *= damp;
              s.vy *= damp;
              glow = f;
              pulled = f > 0.02;
            }
          }
          if (!pulled) {
            // back to the slow outward drift, from wherever the star is now
            const dx = s.x - c.x,
              dy = s.y - c.y,
              dist = Math.hypot(dx, dy) || 1,
              v = (DRIFT_BASE + dist * DRIFT_PER_PX) * s.z;
            const k = Math.min(1, dt * 1.4);
            s.vx += ((dx / dist) * v - s.vx) * k;
            s.vy += ((dy / dist) * v - s.vy) * k;
          }
          s.x += s.vx * dt;
          s.y += s.vy * dt;
          x = s.x + ox;
          y = s.y + oy;

          // absorbed by the button: a flash, and the star is born again at the centre
          if (a && strength > 0.05) {
            const hx = a.width / 2 + 4,
              hy = a.height / 2 + 4;
            const ex = (x - bx) / hx,
              ey = (y - by) / hy;
            if (ex * ex + ey * ey < 1) {
              flashes.push({ x, y, life: 1, size: 3 + s.r * 2 });
              place(s, "ray");
              continue;
            }
          }
          // left the screen: born again at the centre
          if (x < -30 || x > width + 30 || y < -30 || y > height + 30) {
            place(s, "centre");
            continue;
          }
        }

        const dist = Math.hypot(s.x - c.x, s.y - c.y);
        const born = Math.min(1, s.age / 1.5) * Math.min(1, dist / 70); // fade in near the centre
        const grow = 0.55 + 0.75 * Math.min(1, dist / maxDist);
        const twinkle = reduceMotion ? 0.8 : 0.55 + 0.45 * Math.sin(t * s.speed + s.phase);
        const alpha = Math.min(1, ((0.4 + 0.6 * s.z) * twinkle + glow * 0.7) * born);
        if (alpha < 0.01) continue;
        const radius = s.r * grow * (1 + glow * 0.7);

        ctx!.fillStyle = s.color;
        if (s.sparkle) {
          ctx!.globalAlpha = alpha * 0.32;
          ctx!.beginPath();
          ctx!.arc(x, y, radius * 3.2, 0, Math.PI * 2);
          ctx!.fill();
          ctx!.globalAlpha = alpha;
          drawSparkle(x, y, radius * (2.6 + 0.8 * twinkle));
        } else {
          ctx!.globalAlpha = alpha;
          ctx!.beginPath();
          ctx!.arc(x, y, radius, 0, Math.PI * 2);
          ctx!.fill();
          if (glow > 0.15 || s.r * grow > 1.5) {
            ctx!.globalAlpha = alpha * 0.18;
            ctx!.beginPath();
            ctx!.arc(x, y, radius * 3, 0, Math.PI * 2);
            ctx!.fill();
          }
        }
      }

      // absorption flashes
      for (let i = flashes.length - 1; i >= 0; i--) {
        const f = flashes[i];
        f.life -= dt * 2.6;
        if (f.life <= 0) {
          flashes.splice(i, 1);
          continue;
        }
        const r = f.size * (1 + (1 - f.life) * 3);
        const g = ctx!.createRadialGradient(f.x, f.y, 0, f.x, f.y, r);
        g.addColorStop(0, `rgba(255, 244, 205, ${0.95 * f.life})`);
        g.addColorStop(0.4, `rgba(244, 210, 127, ${0.55 * f.life})`);
        g.addColorStop(1, "rgba(244, 210, 127, 0)");
        ctx!.globalAlpha = 1;
        ctx!.fillStyle = g;
        ctx!.beginPath();
        ctx!.arc(f.x, f.y, r, 0, Math.PI * 2);
        ctx!.fill();
      }

      // a shooting star now and then
      if (!reduceMotion) {
        if (now > nextComet) {
          nextComet = now + 6000 + Math.random() * 8000;
          const fromLeft = Math.random() < 0.5;
          comets.push({
            x: fromLeft ? Math.random() * width * 0.5 : width * (0.5 + Math.random() * 0.5),
            y: Math.random() * height * 0.35,
            vx: (fromLeft ? 1 : -1) * (520 + Math.random() * 240),
            vy: 200 + Math.random() * 140,
            life: 1,
          });
        }
        for (let i = comets.length - 1; i >= 0; i--) {
          const k = comets[i];
          k.x += k.vx * dt;
          k.y += k.vy * dt;
          k.life -= dt * 0.9;
          if (k.life <= 0) {
            comets.splice(i, 1);
            continue;
          }
          const len = 0.16;
          const grad = ctx!.createLinearGradient(k.x, k.y, k.x - k.vx * len, k.y - k.vy * len);
          grad.addColorStop(0, `rgba(255, 236, 180, ${0.85 * k.life})`);
          grad.addColorStop(1, "rgba(255, 236, 180, 0)");
          ctx!.globalAlpha = 1;
          ctx!.strokeStyle = grad;
          ctx!.lineWidth = 1.6;
          ctx!.lineCap = "round";
          ctx!.beginPath();
          ctx!.moveTo(k.x, k.y);
          ctx!.lineTo(k.x - k.vx * len, k.y - k.vy * len);
          ctx!.stroke();
        }
      }
      ctx!.globalAlpha = 1;
    }

    function loop(now: number) {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      draw(now, dt);
      frame = requestAnimationFrame(loop);
    }

    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    if (!reduceMotion) {
      window.addEventListener("pointermove", onMove, { passive: true });
      frame = requestAnimationFrame(loop);
    }
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("pointermove", onMove);
    };
  }, []);

  return <canvas ref={canvasRef} aria-hidden className={className} />;
});
